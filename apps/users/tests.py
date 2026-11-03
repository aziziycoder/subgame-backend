from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from .models import User

GOOGLE_URL = '/api/v1/auth/google/'
ADMIN_EMAIL = 'azizbekgulomovweb@gmail.com'


def fake_response(status_code, payload):
    response = mock.Mock(status_code=status_code)
    response.json.return_value = payload
    return response


@override_settings(GOOGLE_CLIENT_ID='our-client')
class GoogleAuthTests(APITestCase):
    def test_unsigned_token_with_admin_email_is_rejected(self):
        # header.payload.signature with a forged admin email and no valid signature
        forged = (
            'eyJhbGciOiJSUzI1NiIsImtpZCI6IngifQ.'
            'eyJlbWFpbCI6ImF6aXpiZWtndWxvbW92d2ViQGdtYWlsLmNvbSIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJzdWIiOiIxIn0.'
            'c2lnbmF0dXJl'
        )
        with mock.patch('apps.users.views.google_requests.Request'), \
                mock.patch('apps.users.views.id_token.verify_oauth2_token', side_effect=ValueError), \
                mock.patch('apps.users.views.id_token.verify_firebase_token', side_effect=ValueError):
            response = self.client.post(GOOGLE_URL, {'id_token': forged}, format='json')
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('access', response.data)

    def test_id_token_verifiers_always_receive_an_audience(self):
        with mock.patch('apps.users.views.google_requests.Request'), \
                mock.patch('apps.users.views.id_token.verify_oauth2_token', side_effect=ValueError) as oauth, \
                mock.patch('apps.users.views.id_token.verify_firebase_token', side_effect=ValueError) as firebase:
            self.client.post(GOOGLE_URL, {'id_token': 'x'}, format='json')
        self.assertEqual(oauth.call_args.kwargs['audience'], 'our-client')
        self.assertTrue(firebase.call_args.kwargs['audience'])

    def test_access_token_for_another_client_is_rejected(self):
        with mock.patch('apps.users.views.http_requests.get', return_value=fake_response(200, {
            'aud': 'someone-elses-client', 'email': ADMIN_EMAIL, 'email_verified': 'true', 'sub': '1',
        })):
            response = self.client.post(GOOGLE_URL, {'access_token': 'x'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_unverified_email_is_rejected(self):
        with mock.patch('apps.users.views.http_requests.get', return_value=fake_response(200, {
            'aud': 'our-client', 'email': ADMIN_EMAIL, 'email_verified': 'false', 'sub': '1',
        })):
            response = self.client.post(GOOGLE_URL, {'access_token': 'x'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_existing_user_keeps_their_firebase_uid(self):
        User.objects.create_user(email='user@example.com', id='firebaseuid')
        responses = [
            fake_response(200, {'aud': 'our-client', 'email': 'user@example.com', 'email_verified': 'true', 'sub': '999'}),
            fake_response(200, {'name': 'User', 'picture': 'https://x/p.png', 'sub': '999'}),
        ]
        with mock.patch('apps.users.views.http_requests.get', side_effect=responses):
            response = self.client.post(GOOGLE_URL, {'access_token': 'x'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['user']['uid'], 'firebaseuid')
        self.assertIn('access', response.data)

    def test_request_without_any_token_is_invalid(self):
        self.assertEqual(self.client.post(GOOGLE_URL, {}, format='json').status_code, 400)
