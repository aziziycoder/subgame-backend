from unittest import mock

import requests
from django.core.cache import cache
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.games.models import Game
from apps.users.models import User

from .models import TranslationRequest, TranslationVote

SEARCH_URL = '/api/v1/issues/requests/search/'
LIST_URL = '/api/v1/issues/requests/'
VOTE_URL = '/api/v1/issues/requests/vote/'
STEAM_GET = 'apps.issues.steam.requests.get'


def bearer(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


def steam_response(payload):
    response = mock.Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    return response


def steam_details(app_id, name, kind='game'):
    return steam_response({str(app_id): {
        'success': True,
        'data': {'type': kind, 'name': name, 'header_image': f'https://cdn/{app_id}/header.jpg'},
    }})


class TranslationRequestTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.alice = User.objects.create_user(email='alice@example.com', id='alice')
        self.bob = User.objects.create_user(email='bob@example.com', id='bob')
        self.admin = User.objects.create_user(email='boss@example.com', id='boss', role='admin')
        Game.objects.create(
            id='hollow-knight', slug='hollow-knight', title='Hollow Knight', cover='https://x/hk.jpg',
            official_store_links=[{'name': 'Steam', 'url': 'https://store.steampowered.com/app/367520/Hollow_Knight/'}],
        )

    def vote(self, user, app_id):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(user))
        return self.client.post(VOTE_URL, {'steamAppId': app_id}, format='json')

    def test_search_marks_site_games_and_requests_and_drops_soundtracks_and_demos(self):
        TranslationRequest.objects.create(steam_app_id=1030300, title='Hollow Knight: Silksong')
        payload = {'items': [
            {'type': 'app', 'id': 367520, 'name': 'Hollow Knight', 'tiny_image': 'hk.jpg'},
            {'type': 'app', 'id': 1030300, 'name': 'Hollow Knight: Silksong', 'tiny_image': 'ss.jpg'},
            {'type': 'app', 'id': 598190, 'name': 'Hollow Knight - Official Soundtrack', 'tiny_image': 'ost.jpg'},
            {'type': 'app', 'id': 111, 'name': 'Scarlet Hollow', 'tiny_image': 'sh.jpg'},
            {'type': 'app', 'id': 112, 'name': 'Scarlet Hollow Demo', 'tiny_image': 'shd.jpg'},
        ]}
        with mock.patch(STEAM_GET, return_value=steam_response(payload)):
            response = self.client.get(SEARCH_URL, {'q': 'hollow'})

        self.assertEqual(response.status_code, 200)
        results = {item['steamAppId']: item for item in response.data['results']}
        self.assertEqual(set(results), {367520, 1030300, 111})
        self.assertEqual(results[367520]['siteGame']['slug'], 'hollow-knight')
        self.assertEqual(results[1030300]['request']['votes'], 0)
        self.assertIsNone(results[111]['request'])
        self.assertIsNone(results[111]['siteGame'])

    def test_search_reports_steam_outage(self):
        with mock.patch(STEAM_GET, side_effect=requests.ConnectionError):
            response = self.client.get(SEARCH_URL, {'q': 'hollow'})
        self.assertEqual(response.status_code, 503)

    def test_short_query_does_not_call_steam(self):
        with mock.patch(STEAM_GET) as get:
            response = self.client.get(SEARCH_URL, {'q': 'h'})
        self.assertEqual(response.data['results'], [])
        get.assert_not_called()

    def test_voting_needs_sign_in(self):
        response = self.client.post(VOTE_URL, {'steamAppId': 111}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_first_vote_creates_the_request_from_steam_and_each_user_counts_once(self):
        with mock.patch(STEAM_GET, return_value=steam_details(111, 'Scarlet Hollow')) as get:
            first = self.vote(self.alice, 111)
            again = self.vote(self.alice, 111)
            other = self.vote(self.bob, 111)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.data['title'], 'Scarlet Hollow')
        self.assertEqual(first.data['imageUrl'], 'https://cdn/111/header.jpg')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.data['votes'], 1)
        self.assertEqual(other.data['votes'], 2)
        self.assertEqual(TranslationRequest.objects.count(), 1)
        # Steam is asked only when the request is created.
        self.assertEqual(get.call_count, 1)

    def test_vote_for_something_that_is_not_a_game_is_refused(self):
        with mock.patch(STEAM_GET, return_value=steam_details(598190, 'HK Soundtrack', kind='music')):
            response = self.vote(self.alice, 598190)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TranslationRequest.objects.exists())

    def test_vote_for_a_game_already_on_the_site_is_refused(self):
        with mock.patch(STEAM_GET) as get:
            response = self.vote(self.alice, 367520)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data['game']['slug'], 'hollow-knight')
        get.assert_not_called()

    def test_closed_requests_take_no_votes(self):
        TranslationRequest.objects.create(steam_app_id=222, title='Rejected', status=TranslationRequest.STATUS_REJECTED)
        response = self.vote(self.alice, 222)
        self.assertEqual(response.status_code, 400)

    def test_list_is_ranked_by_votes_and_marks_my_votes(self):
        low = TranslationRequest.objects.create(steam_app_id=1, title='Low')
        top = TranslationRequest.objects.create(steam_app_id=2, title='Top')
        TranslationRequest.objects.create(steam_app_id=3, title='Gone', status=TranslationRequest.STATUS_REJECTED)
        TranslationVote.objects.create(request=low, user=self.bob)
        TranslationVote.objects.create(request=top, user=self.bob)
        TranslationVote.objects.create(request=top, user=self.alice)

        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.alice))
        response = self.client.get(LIST_URL)

        self.assertEqual(response.data['count'], 2)
        self.assertEqual([(r['title'], r['rank'], r['votes'], r['hasVoted']) for r in response.data['results']], [
            ('Top', 1, 2, True),
            ('Low', 2, 1, False),
        ])
        self.assertNotIn('adminNote', response.data['results'][0])

    def test_taking_back_the_last_vote_removes_an_open_request_but_not_an_accepted_one(self):
        open_request = TranslationRequest.objects.create(steam_app_id=1, title='Open')
        accepted = TranslationRequest.objects.create(steam_app_id=2, title='Accepted', status=TranslationRequest.STATUS_ACCEPTED)
        TranslationVote.objects.create(request=open_request, user=self.alice)
        TranslationVote.objects.create(request=accepted, user=self.alice)

        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.alice))
        removed = self.client.delete(f'/api/v1/issues/requests/{open_request.id}/vote/')
        kept = self.client.delete(f'/api/v1/issues/requests/{accepted.id}/vote/')

        self.assertTrue(removed.data['deleted'])
        self.assertFalse(TranslationRequest.objects.filter(pk=open_request.pk).exists())
        self.assertFalse(kept.data['deleted'])
        self.assertEqual(kept.data['request']['votes'], 0)

    def test_only_admins_can_change_a_request(self):
        item = TranslationRequest.objects.create(steam_app_id=1, title='Game')
        url = f'/api/v1/issues/admin/requests/{item.id}/'

        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.alice))
        self.assertEqual(self.client.patch(url, {'status': 'accepted'}, format='json').status_code, 403)

        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.admin))
        response = self.client.patch(url, {'status': 'done', 'gameSlug': 'hollow-knight', 'adminNote': 'ok'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['game']['slug'], 'hollow-knight')
        self.assertEqual(response.data['adminNote'], 'ok')
        self.assertEqual(self.client.patch(url, {'status': 'nope'}, format='json').status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(TranslationRequest.objects.exists())
