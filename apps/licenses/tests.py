from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.games.models import Game
from apps.users.models import User
from .models import DeviceSession, License

HWID_A = 'A' * 64
HWID_B = 'B' * 64


class LicenseTestBase(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='user@example.com', id='firebaseuid')
        self.admin = User.objects.create_user(email='admin@example.com', id='adminuid', role='admin')
        self.game = Game.objects.create(id='hollow-knight', slug='hollow-knight', title='Hollow Knight', cover='https://x/y.jpg')
        self.license = License.objects.create(
            id='legacy-id-with-other-uid_hollow-knight', user=self.user, game=self.game,
            user_email=self.user.email, game_title=self.game.title, game_slug=self.game.slug,
        )

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')


class BindHwidTests(LicenseTestBase):
    def bind(self, hwid):
        return self.client.post('/api/v1/licenses/bind-hwid/', {'gameId': 'hollow-knight', 'hwid': hwid, 'deviceName': 'SG-1'}, format='json')

    def test_binds_even_when_license_id_does_not_match_user_id(self):
        self.auth(self.user)
        self.assertEqual(self.bind(HWID_A).status_code, 200)
        self.license.refresh_from_db()
        self.assertEqual(self.license.hwid, HWID_A)

    def test_other_machine_is_blocked(self):
        self.auth(self.user)
        self.bind(HWID_A)
        response = self.bind(HWID_B)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response.data['isBoundToAnotherDevice'])

    def test_placeholder_hwid_is_rejected(self):
        self.auth(self.user)
        self.assertEqual(self.bind('LOCAL_HWID').status_code, 400)
        self.license.refresh_from_db()
        self.assertIsNone(self.license.hwid)

    def test_admin_reset_lets_a_new_machine_bind(self):
        self.auth(self.user)
        self.bind(HWID_A)

        self.auth(self.admin)
        reset = self.client.patch(f'/api/v1/licenses/admin/{self.license.id}/', {'action': 'reset_hwid'}, format='json')
        self.assertEqual(reset.status_code, 200)

        self.auth(self.user)
        self.assertEqual(self.bind(HWID_B).status_code, 200)
        self.license.refresh_from_db()
        self.assertEqual(self.license.hwid, HWID_B)

    def test_reset_requires_admin(self):
        self.auth(self.user)
        response = self.client.patch(f'/api/v1/licenses/admin/{self.license.id}/', {'action': 'reset_hwid'}, format='json')
        self.assertEqual(response.status_code, 403)


class GrantLicenseTests(LicenseTestBase):
    def test_granting_an_active_license_reports_a_conflict(self):
        self.auth(self.admin)
        response = self.client.post('/api/v1/licenses/admin/', {'userId': self.user.id, 'gameId': self.game.id}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertIn('error', response.data)


class LicenseStatsTests(LicenseTestBase):
    def test_counts_are_public_and_grouped(self):
        self.license.hwid = HWID_A
        self.license.save()
        response = self.client.get('/api/v1/licenses/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['hollow-knight'], {'total': 1, 'bound': 1})


class DevicePairingTests(LicenseTestBase):
    def create_session(self):
        return self.client.post('/api/v1/licenses/device/create/', {}, format='json').data

    def poll(self, code, token):
        return self.client.post(f'/api/v1/licenses/device/poll/{code}/', {'pollToken': token}, format='json')

    def approve(self, code):
        self.auth(self.user)
        response = self.client.post('/api/v1/licenses/device/approve/', {'code': code}, format='json')
        self.client.credentials()
        return response

    def test_full_flow_returns_tokens_once(self):
        session = self.create_session()
        self.assertEqual(self.poll(session['code'], session['pollToken']).data['status'], 'pending')
        self.assertEqual(self.approve(session['code']).status_code, 200)

        first = self.poll(session['code'], session['pollToken'])
        self.assertEqual(first.data['status'], 'approved')
        self.assertIn('access', first.data['tokens'])

        second = self.poll(session['code'], session['pollToken'])
        self.assertEqual(second.data['status'], 'consumed')
        self.assertNotIn('tokens', second.data)

    def test_code_alone_does_not_yield_tokens(self):
        session = self.create_session()
        self.approve(session['code'])
        response = self.poll(session['code'], 'guessed')
        self.assertEqual(response.status_code, 404)
        self.assertNotIn('tokens', response.data)

    def test_expired_session_cannot_be_approved(self):
        session = self.create_session()
        DeviceSession.objects.filter(session_id=session['code']).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.approve(session['code']).status_code, 400)
        self.assertEqual(self.poll(session['code'], session['pollToken']).data['status'], 'expired')


class AdminLicenseListTests(LicenseTestBase):
    def setUp(self):
        super().setUp()
        self.other = Game.objects.create(id='stray', slug='stray', title='Stray', cover='https://x/s.jpg')
        for i in range(60):
            user = User.objects.create_user(email=f'p{i:02d}@example.com', id=f'p{i:02d}')
            License.objects.create(
                id=f'p{i:02d}_stray', user=user, game=self.other, user_email=user.email,
                game_title='Stray', game_slug='stray', hwid=HWID_A if i < 10 else None,
                status='revoked' if i >= 55 else 'active',
                payment_provider='click' if i == 59 else 'free',
            )
        self.auth(self.admin)

    def page(self, **params):
        return self.client.get('/api/v1/licenses/admin/list/', params).data

    def test_pages_by_fifty(self):
        data = self.page()
        self.assertEqual(len(data['licenses']), 50)
        self.assertEqual(data['pagination'], {'page': 1, 'pageSize': 50, 'total': 61, 'totalPages': 2})
        self.assertEqual(len(self.page(page=2)['licenses']), 11)

    def test_filters_run_on_the_server(self):
        self.assertEqual(self.page(game='hollow-knight')['pagination']['total'], 1)
        self.assertEqual(self.page(device='bound')['pagination']['total'], 10)
        self.assertEqual(self.page(status='revoked')['pagination']['total'], 5)
        self.assertEqual(self.page(provider='click')['pagination']['total'], 1)
        self.assertEqual([l['userEmail'] for l in self.page(search='p42@')['licenses']], ['p42@example.com'])

    def test_summary_counts_per_game_without_listing_licenses(self):
        data = self.client.get('/api/v1/licenses/admin/summary/').data
        self.assertEqual(data['stats']['totalLicenses'], 61)
        self.assertEqual(data['stats']['totalBoundDevices'], 10)
        self.assertEqual([g['gameId'] for g in data['groups']], ['stray', 'hollow-knight'])
        self.assertEqual(data['groups'][0]['totalLicenses'], 60)
        self.assertNotIn('licenses', data['groups'][0])
        self.assertEqual(len(data['unpaidRevokedIds']), 4)

    def test_non_admin_is_refused(self):
        self.auth(self.user)
        self.assertEqual(self.client.get('/api/v1/licenses/admin/list/').status_code, 403)
        self.assertEqual(self.client.get('/api/v1/licenses/admin/summary/').status_code, 403)
