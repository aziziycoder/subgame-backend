from datetime import timedelta
from unittest import mock

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.games.models import Game
from apps.licenses.models import License
from apps.payments.models import Order

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


USERS_URL = '/api/v1/auth/admin/users-with-licenses/'
DASHBOARD_URL = '/api/v1/auth/admin/dashboard-stats/'


def bearer(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class AdminUsersPaginationTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='boss@example.com', id='adminuid', role='admin')
        self.game = Game.objects.create(id='stray', slug='stray', title='Stray', cover='https://x/y.jpg')
        base = timezone.now()
        for i in range(120):
            user = User.objects.create_user(
                email=f'user{i:03d}@example.com', id=f'uid{i:03d}', display_name=f'Player {i}',
                last_login_at=base - timedelta(minutes=i),
            )
            if i % 10 == 0:
                License.objects.create(
                    id=f'{user.id}_stray', user=user, game=self.game, user_email=user.email,
                    game_title='Stray', game_slug='stray', hwid='A' * 64 if i % 20 == 0 else None,
                )
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.admin))

    def test_returns_fifty_users_per_page_with_totals(self):
        data = self.client.get(USERS_URL).data
        self.assertEqual(len(data['users']), 50)
        self.assertEqual(data['pagination'], {'page': 1, 'pageSize': 50, 'total': 121, 'totalPages': 3})
        self.assertEqual(data['stats']['totalUsers'], 121)
        self.assertEqual(data['stats']['totalLicenses'], 12)
        self.assertEqual(data['stats']['totalBoundDevices'], 6)

    def test_last_page_holds_the_remainder(self):
        self.assertEqual(len(self.client.get(USERS_URL, {'page': 3}).data['users']), 21)
        self.assertEqual(self.client.get(USERS_URL, {'page': 99}).data['pagination']['page'], 3)

    def test_search_covers_users_beyond_the_first_page(self):
        data = self.client.get(USERS_URL, {'search': 'user115'}).data
        self.assertEqual([u['email'] for u in data['users']], ['user115@example.com'])
        self.assertEqual(data['pagination']['total'], 1)

    def test_filters_run_on_the_server(self):
        devices = self.client.get(USERS_URL, {'filter': 'with_devices'}).data
        self.assertEqual(devices['pagination']['total'], 6)
        self.assertTrue(all(u['boundDevicesCount'] == 1 for u in devices['users']))
        admins = self.client.get(USERS_URL, {'filter': 'admin'}).data
        self.assertEqual([u['email'] for u in admins['users']], ['boss@example.com'])
        self.assertEqual(admins['filterCounts'], {'all': 121, 'admin': 1, 'user': 120, 'with_devices': 6})

    def test_licenses_are_attached_without_a_query_per_user(self):
        with CaptureQueriesContext(connection) as ctx:
            data = self.client.get(USERS_URL, {'page_size': 120}).data
        self.assertEqual(len(data['users']), 120)
        self.assertLess(len(ctx.captured_queries), 15)
        with_license = next(u for u in data['users'] if u['email'] == 'user010@example.com')
        self.assertEqual(with_license['claimedGamesCount'], 1)
        self.assertEqual(with_license['licenses'][0]['gameSlug'], 'stray')

    def test_non_admin_is_refused(self):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(User.objects.get(id='uid001')))
        self.assertEqual(self.client.get(USERS_URL).status_code, 403)
        self.assertEqual(self.client.get(DASHBOARD_URL).status_code, 403)


class AdminDashboardStatsTests(APITestCase):
    def setUp(self):
        now = timezone.now()
        self.admin = User.objects.create_user(email='boss@example.com', id='adminuid', role='admin')
        old = User.objects.create_user(email='old@example.com', id='olduid', created_at=now - timedelta(days=60))
        fresh = User.objects.create_user(email='new@example.com', id='newuid', created_at=now - timedelta(days=3))
        stray = Game.objects.create(id='stray', slug='stray', title='Stray', cover='https://x/s.jpg')
        cup = Game.objects.create(id='cuphead', slug='cuphead', title='Cuphead', cover='https://x/c.jpg')
        for user, game, hwid in ((old, stray, 'A' * 64), (fresh, stray, 'A' * 64), (fresh, cup, None)):
            License.objects.create(
                id=f'{user.id}_{game.id}', user=user, game=game, user_email=user.email,
                game_title=game.title, game_slug=game.slug, hwid=hwid,
                bound_at=now if hwid else None, payment_provider='click' if game is cup else 'free',
            )
        Order.objects.create(order_id='newuid__cuphead', user=fresh, game=cup, user_email=fresh.email,
                             game_title='Cuphead', game_slug='cuphead', status='paid', paid_amount=15000,
                             click_trans_id='3970608254')
        Order.objects.create(order_id='olduid__cuphead', user=old, game=cup, user_email=old.email,
                             game_title='Cuphead', game_slug='cuphead', status='pending')
        # Marked paid but never confirmed by Click (as the old import did)
        Order.objects.create(order_id='olduid__stray', user=old, game=stray, user_email=old.email,
                             game_title='Stray', game_slug='stray', status='paid', paid_amount=5000)
        Order.objects.create(order_id='newuid__stray', user=fresh, game=stray, user_email=fresh.email,
                             game_title='Stray', game_slug='stray', status='paid', paid_amount=7000,
                             payment_provider='manual_paid')
        # Granted by an admin in the panel with a price: no order exists for it
        License.objects.create(id='olduid_cuphead', user=old, game=cup, user_email=old.email,
                               game_title='Cuphead', game_slug='cuphead', payment_provider='manual_paid',
                               paid_amount=9000, granted_by='boss@example.com')
        rdr = Game.objects.create(id='rdr', slug='rdr', title='RDR', cover='https://x/r.jpg')
        License.objects.create(id='newuid_rdr', user=fresh, game=rdr, user_email=fresh.email,
                               game_title='RDR', game_slug='rdr', payment_provider='manual_paid', paid_amount=0)
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.admin))

    def test_counts_come_from_the_database(self):
        data = self.client.get(DASHBOARD_URL).data
        self.assertEqual(data['users']['total'], 3)
        self.assertEqual(data['users']['last7'], 2)
        self.assertEqual(data['users']['admins'], 1)
        self.assertEqual(data['users']['withLicense'], 2)
        self.assertEqual(data['licenses']['total'], 5)
        self.assertEqual(data['licenses']['bound'], 2)
        self.assertEqual(data['devices']['uniqueHwids'], 1)
        self.assertEqual(data['orders']['paid'], 1)
        self.assertEqual(data['orders']['pending'], 1)
        self.assertEqual(data['orders']['revenue']['total'], 15000)
        self.assertEqual(data['orders']['otherPaid'], 2)
        self.assertEqual(data['orders']['otherRevenue'], 12000)
        self.assertEqual([g['gameId'] for g in data['topGames']], ['cuphead', 'stray', 'rdr'])

    def test_manual_payments_are_added_once(self):
        orders = self.client.get(DASHBOARD_URL).data['orders']
        # 5000 unconfirmed order + 7000 manual order + 9000 admin-granted license;
        # the free license under the 7000 order is not counted again
        self.assertEqual(orders['manualRevenue']['total'], 21000)
        self.assertEqual(orders['manualFromOrders'], 2)
        self.assertEqual(orders['manualFromLicenses'], 1)
        self.assertEqual(orders['manualWithoutAmount'], 1)
        self.assertEqual(orders['revenue']['total'], 15000)
        self.assertEqual(orders['totalRevenue']['total'], 36000)
        cuphead = self.client.get(DASHBOARD_URL).data['topGames'][0]
        self.assertEqual((cuphead['clickRevenue'], cuphead['manualRevenue'], cuphead['revenue']), (15000, 9000, 24000))

    def test_daily_series_covers_thirty_days(self):
        data = self.client.get(DASHBOARD_URL).data
        self.assertEqual(len(data['series']), 30)
        self.assertEqual(sum(day['licenses'] for day in data['series']), 5)
        self.assertEqual(sum(day['clickRevenue'] for day in data['series']), 15000)
        self.assertEqual(sum(day['revenue'] for day in data['series']), 36000)
        self.assertTrue(data['activity'])

    def test_click_money_is_dated_by_payment_not_by_checkout(self):
        now = timezone.now()
        before = self.client.get(DASHBOARD_URL).data
        # Opened 20 days ago, paid today: it belongs to today, not to that old day.
        Order.objects.create(order_id='retried-checkout', user=User.objects.get(id='olduid'),
                             game=Game.objects.get(id='rdr'), user_email='old@example.com', game_title='RDR',
                             game_slug='rdr', status='paid', click_trans_id='T9', paid_amount=15000,
                             created_at=now - timedelta(days=20), paid_at=now)
        after = self.client.get(DASHBOARD_URL).data
        for window in ('today', 'last7'):
            self.assertEqual(after['orders']['revenue'][window] - before['orders']['revenue'][window], 15000)
        self.assertEqual(after['series'][-1]['clickRevenue'] - before['series'][-1]['clickRevenue'], 15000)
        # Nothing landed on the day the checkout was opened.
        self.assertEqual(after['series'][-21]['clickRevenue'], before['series'][-21]['clickRevenue'])


class DailyReportTests(APITestCase):
    """manage.py send_daily_report: one Tashkent day, Telegram mocked."""

    DAY = '2026-03-10'

    def setUp(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from apps.issues.models import TranslationRequest, TranslationVote

        tz = ZoneInfo('Asia/Tashkent')
        at = lambda d, h: datetime(2026, 3, d, h, 0, tzinfo=tz)
        inside, before, after = at(10, 12), at(9, 23), at(11, 0)

        old = User.objects.create_user(email='old@example.com', id='old', created_at=before)
        fresh = User.objects.create_user(email='new@example.com', id='new', created_at=inside)
        User.objects.create_user(email='late@example.com', id='late', created_at=after)
        stray = Game.objects.create(id='stray', slug='stray', title='Stray')
        evil = Game.objects.create(id='evil', slug='evil', title='<Evil & Co>')

        def lic(user, game, created, **extra):
            License.objects.create(id=f'{user.id}_{game.id}', user=user, game=game, user_email=user.email,
                                   game_title=game.title, game_slug=game.slug, created_at=created, **extra)

        lic(fresh, stray, inside, payment_provider='click', paid_amount=15000, hwid='PC1', bound_at=inside)
        lic(fresh, evil, inside, hwid='PC1', bound_at=inside)
        lic(old, stray, before, hwid='PC2', bound_at=before)
        lic(old, evil, inside, payment_provider='manual_paid', paid_amount=20000, granted_by='admin')

        Order.objects.create(order_id='new__stray', user=fresh, game=stray, user_email=fresh.email,
                             game_title='Stray', game_slug='stray', status='paid', click_trans_id='T1',
                             paid_amount=15000, created_at=inside)
        Order.objects.create(order_id='old__stray', user=old, game=stray, user_email=old.email,
                             game_title='Stray', game_slug='stray', status='paid', click_trans_id='T0',
                             paid_amount=10000, created_at=before)
        Order.objects.create(order_id='late__stray', user=old, game=evil, user_email=old.email,
                             game_title='<Evil & Co>', game_slug='evil', status='pending', created_at=inside)
        self.inside, self.before, self.after = inside, before, after

        req = TranslationRequest.objects.create(steam_app_id=1, title='Hades <II>', created_at=inside)
        TranslationVote.objects.create(request=req, user=fresh, created_at=inside)
        TranslationVote.objects.create(request=req, user=old, created_at=inside)
        TranslationVote.objects.create(request=req, user=User.objects.get(id='late'), created_at=after)

    def run_command(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('send_daily_report', '--date', self.DAY, *args, stdout=out)
        return out.getvalue()

    def test_dry_run_counts_only_that_day_and_escapes_user_content(self):
        text = self.run_command('--dry-run')
        self.assertIn('10.03.2026', text)
        self.assertIn('• Yangi: <b>1</b>', text)  # one new user that day
        self.assertIn('• Yangi: <b>3</b>', text)  # three licenses that day
        self.assertIn('&lt;Evil &amp; Co&gt;: 2', text)
        self.assertNotIn('<Evil', text)
        self.assertIn("Bog'langan litsenziyalar: <b>2</b> (1 ta kompyuter)", text)
        self.assertIn("Click: <b>1</b> ta — 15 000 so'm", text)
        self.assertIn("Qo'lda kiritilgan: <b>1</b> ta — 20 000 so'm", text)
        self.assertIn("Kunlik tushum: 35 000 so'm", text)
        self.assertIn('Yakunlanmagan Click buyurtmalar: 1', text)
        self.assertIn('Yangi ovozlar: <b>2</b>', text)
        self.assertIn('1. Hades &lt;II&gt; — 2', text)
        self.assertIn('• Foydalanuvchilar: 2', text)  # the user created next day is not in the totals
        self.assertIn("Umumiy tushum: 45 000 so'm", text)

    def test_payment_counts_on_the_day_it_was_paid(self):
        old = User.objects.get(id='old')
        evil = Game.objects.get(id='evil')
        # Checkout opened the day before and paid on the report day; another opened that day, paid the next.
        Order.objects.create(order_id='paid-today', user=old, game=evil, user_email=old.email,
                             game_title='<Evil & Co>', game_slug='evil', status='paid', click_trans_id='T5',
                             paid_amount=15000, created_at=self.before, paid_at=self.inside)
        Order.objects.create(order_id='paid-tomorrow', user=old, game=Game.objects.get(id='stray'),
                             user_email=old.email, game_title='Stray', game_slug='stray', status='paid',
                             click_trans_id='T6', paid_amount=15000, created_at=self.inside, paid_at=self.after)
        text = self.run_command('--dry-run')
        self.assertIn("Click: <b>2</b> ta — 30 000 so'm", text)

    @override_settings(TELEGRAM_BOT_TOKEN='123:SECRET', TELEGRAM_REPORT_CHAT_ID='42')
    def test_sends_html_message_to_chat(self):
        with mock.patch('apps.users.daily_report.requests.post',
                        return_value=fake_response(200, {'ok': True})) as post:
            out = self.run_command()
        self.assertIn('yuborildi', out)
        url = post.call_args.args[0]
        body = post.call_args.kwargs['json']
        self.assertEqual(url, 'https://api.telegram.org/bot123:SECRET/sendMessage')
        self.assertEqual(body['chat_id'], '42')
        self.assertEqual(body['parse_mode'], 'HTML')
        self.assertIn('kunlik hisobot', body['text'])

    @override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_REPORT_CHAT_ID='42')
    def test_missing_settings_fail(self):
        from django.core.management.base import CommandError
        with mock.patch('apps.users.daily_report.requests.post') as post, \
                self.assertRaisesMessage(CommandError, 'TELEGRAM_BOT_TOKEN'):
            self.run_command()
        post.assert_not_called()

    @override_settings(TELEGRAM_BOT_TOKEN='123:SECRET', TELEGRAM_REPORT_CHAT_ID='42')
    def test_telegram_refusal_fails_without_leaking_token(self):
        import requests as http
        from django.core.management.base import CommandError
        refused = fake_response(400, {'ok': False, 'description': 'Bad Request: chat not found'})
        with mock.patch('apps.users.daily_report.requests.post', return_value=refused), \
                self.assertRaisesMessage(CommandError, 'chat not found'):
            self.run_command()
        boom = http.ConnectionError('https://api.telegram.org/bot123:SECRET/sendMessage failed')
        with mock.patch('apps.users.daily_report.requests.post', side_effect=boom), \
                self.assertRaises(CommandError) as ctx:
            self.run_command()
        self.assertNotIn('SECRET', str(ctx.exception))

    def test_bad_date_fails(self):
        from io import StringIO
        from django.core.management import call_command
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command('send_daily_report', '--date', '10.03.2026', '--dry-run', stdout=StringIO())
