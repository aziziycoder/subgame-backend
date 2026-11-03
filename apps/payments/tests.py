import hashlib

from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from apps.games.models import Game
from apps.licenses.models import License
from apps.users.models import User
from .models import Order

SECRET = 'test-secret'
ORDER_ID = 'uid__stray'
PREPARE_ID = 12345


def complete_payload(amount, sign_string=None):
    payload = {
        'click_trans_id': '1', 'service_id': '2', 'click_paydoc_id': '3',
        'merchant_trans_id': ORDER_ID, 'merchant_prepare_id': PREPARE_ID,
        'amount': amount, 'action': 1, 'error': 0, 'error_note': '', 'sign_time': 't',
    }
    payload['sign_string'] = sign_string or hashlib.md5(
        f"12{SECRET}{ORDER_ID}{PREPARE_ID}{amount}1t".encode('utf-8')
    ).hexdigest()
    return payload


@override_settings(CLICK_SECRET_KEY=SECRET)
class ClickWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='user@example.com', id='uid')
        self.game = Game.objects.create(id='stray', slug='stray', title='Stray', cover='https://x/y.jpg', subtitle_price='15 000 so‘m')
        Order.objects.create(
            order_id=ORDER_ID, user=self.user, game=self.game, user_email=self.user.email,
            game_title='Stray', game_slug='stray', amount=15000, click_prepare_id=PREPARE_ID,
        )

    def post(self, payload):
        return self.client.post('/api/v1/payments/click/complete/', payload, format='json')

    def test_valid_payment_grants_license(self):
        response = self.post(complete_payload('15000'))
        self.assertEqual(response.data['error'], 0)
        self.assertTrue(License.objects.filter(user=self.user, game=self.game, status='active').exists())

    def test_sandbox_bypass_no_longer_skips_the_signature(self):
        response = self.post(complete_payload('15000', sign_string='sandbox_bypass'))
        self.assertEqual(response.data['error'], -1)
        self.assertFalse(License.objects.exists())

    def test_missing_secret_rejects_every_request(self):
        with override_settings(CLICK_SECRET_KEY=''):
            response = self.post(complete_payload('15000'))
        self.assertEqual(response.data['error'], -1)
        self.assertFalse(License.objects.exists())

    def test_underpayment_is_rejected(self):
        response = self.post(complete_payload('1'))
        self.assertEqual(response.data['error'], -2)
        self.assertFalse(License.objects.exists())


    def test_form_encoded_request_like_click_sends_is_accepted(self):
        response = self.client.post('/api/click/complete', complete_payload('15000'))
        self.assertEqual(response.data['error'], 0)

    def test_license_with_legacy_id_is_reactivated_not_duplicated(self):
        License.objects.create(
            id='old-format', user=self.user, game=self.game, user_email=self.user.email,
            game_title='Stray', game_slug='stray', status='revoked', hwid='A' * 64,
        )
        self.assertEqual(self.post(complete_payload('15000')).data['error'], 0)
        license_obj = License.objects.get(user=self.user, game=self.game)
        self.assertEqual(license_obj.id, 'old-format')
        self.assertEqual(license_obj.status, 'active')
        self.assertEqual(license_obj.hwid, 'A' * 64)

    def test_retry_of_same_transaction_succeeds_and_other_is_rejected(self):
        self.assertEqual(self.post(complete_payload('15000')).data['error'], 0)
        self.assertEqual(self.post(complete_payload('15000')).data['error'], 0)

        other = complete_payload('15000')
        other['click_trans_id'] = '9'
        other['sign_string'] = hashlib.md5(f"92{SECRET}{ORDER_ID}{PREPARE_ID}150001t".encode('utf-8')).hexdigest()
        self.assertEqual(self.post(other).data['error'], -4)

    def test_cancel_notice_cannot_undo_a_paid_order(self):
        self.post(complete_payload('15000'))
        cancel = complete_payload('15000')
        cancel['error'] = -5017
        cancel['click_trans_id'] = '9'
        cancel['sign_string'] = hashlib.md5(f"92{SECRET}{ORDER_ID}{PREPARE_ID}150001t".encode('utf-8')).hexdigest()
        self.post(cancel)
        self.assertEqual(Order.objects.get(order_id=ORDER_ID).status, 'paid')

    def test_order_for_another_game_is_never_matched(self):
        unknown = 'uid__other-game'
        payload = complete_payload('15000')
        payload['merchant_trans_id'] = payload['merchant_prepare_id'] = unknown
        payload['sign_string'] = hashlib.md5(f"12{SECRET}{unknown}{unknown}150001t".encode('utf-8')).hexdigest()
        self.assertEqual(self.post(payload).data['error'], -5)
        self.assertFalse(License.objects.exists())

    def test_truncated_or_empty_order_id_is_rejected(self):
        for altered in ('uid__st', ''):
            payload = complete_payload('15000')
            payload['merchant_trans_id'] = payload['merchant_prepare_id'] = altered
            payload['sign_string'] = hashlib.md5(f"12{SECRET}{altered}{altered}150001t".encode('utf-8')).hexdigest()
            self.assertEqual(self.post(payload).data['error'], -5)
        self.assertFalse(License.objects.exists())

    def prepare_payload(self):
        payload = {
            'click_trans_id': '5397953850', 'service_id': '2', 'click_paydoc_id': '3',
            'merchant_trans_id': ORDER_ID, 'amount': '15000.00', 'action': 0,
            'error': 0, 'error_note': '', 'sign_time': 't',
        }
        payload['sign_string'] = hashlib.md5(
            f"53979538502{SECRET}{ORDER_ID}15000.000t".encode('utf-8')
        ).hexdigest()
        return payload

    def test_prepare_and_complete_return_integer_ids_as_click_requires(self):
        Order.objects.filter(order_id=ORDER_ID).update(click_prepare_id=None)

        prepared = self.client.post('/api/click/prepare', self.prepare_payload()).data
        self.assertEqual(prepared['error'], 0)
        self.assertIsInstance(prepared['merchant_prepare_id'], int)
        self.assertLessEqual(prepared['merchant_prepare_id'], 2_147_483_647)

        prepare_id = prepared['merchant_prepare_id']
        complete = {
            'click_trans_id': '5397953850', 'service_id': '2', 'click_paydoc_id': '3',
            'merchant_trans_id': ORDER_ID, 'merchant_prepare_id': prepare_id, 'amount': '15000.00',
            'action': 1, 'error': 0, 'error_note': '', 'sign_time': 't',
        }
        complete['sign_string'] = hashlib.md5(
            f"53979538502{SECRET}{ORDER_ID}{prepare_id}15000.001t".encode('utf-8')
        ).hexdigest()
        completed = self.client.post('/api/click/complete', complete).data
        self.assertEqual(completed['error'], 0)
        self.assertIsInstance(completed['merchant_confirm_id'], int)
        self.assertTrue(License.objects.filter(user=self.user, game=self.game, status='active').exists())

        self.assertEqual(self.client.post('/api/click/complete', complete).data['error'], 0)

    def test_retried_prepare_keeps_the_same_prepare_id(self):
        first = self.client.post('/api/click/prepare', self.prepare_payload()).data
        second = self.client.post('/api/click/prepare', self.prepare_payload()).data
        self.assertEqual(first['merchant_prepare_id'], second['merchant_prepare_id'])

    def test_complete_with_unknown_prepare_id_is_rejected(self):
        payload = complete_payload('15000')
        payload['merchant_prepare_id'] = 999
        payload['sign_string'] = hashlib.md5(f"12{SECRET}{ORDER_ID}999150001t".encode('utf-8')).hexdigest()
        self.assertEqual(self.post(payload).data['error'], -6)
        self.assertFalse(License.objects.exists())

    def test_complete_after_cancellation_is_rejected(self):
        Order.objects.filter(order_id=ORDER_ID).update(status='cancelled')
        self.assertEqual(self.post(complete_payload('15000')).data['error'], -9)
        self.assertFalse(License.objects.exists())

    def test_malformed_amount_does_not_crash(self):
        self.assertEqual(self.post(complete_payload('abc')).data['error'], -8)


@override_settings(CLICK_SERVICE_ID='s', CLICK_MERCHANT_ID='m')
class CreateOrderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='user@example.com', id='uid')
        Game.objects.create(id='stray', slug='stray', title='Stray', cover='https://x/y.jpg', subtitle_price='15 000 so‘m')

    def test_requires_authentication(self):
        response = self.client.post('/api/v1/payments/order/create/', {'gameId': 'stray', 'userId': 'uid'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_client_cannot_choose_the_amount(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.user).access_token}')
        response = self.client.post('/api/v1/payments/order/create/', {'gameId': 'stray', 'amount': 1}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['amount'], 15000)


    def auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.user).access_token}')

    def order(self, game_id='stray'):
        return self.client.post('/api/v1/payments/order/create/', {'gameId': game_id}, format='json')

    def test_price_field_is_used_when_subtitle_price_has_no_number(self):
        Game.objects.create(id='g2', slug='g2', title='G', cover='https://x/y.jpg', subtitle_price='Bepul', price='20 000 so‘m')
        self.auth()
        self.assertEqual(self.order('g2').data['amount'], 20000)

    def test_free_game_cannot_be_ordered(self):
        Game.objects.create(id='free', slug='free', title='F', cover='https://x/y.jpg', subtitle_price='Bepul', price='Tekin')
        self.auth()
        self.assertEqual(self.order('free').status_code, 400)

    def test_owner_of_an_active_license_is_not_charged_again(self):
        game = Game.objects.get(id='stray')
        License.objects.create(id='l', user=self.user, game=game, user_email=self.user.email, game_title='Stray', game_slug='stray')
        self.auth()
        self.assertEqual(self.order().status_code, 409)

    def test_order_id_is_random_and_has_no_user_or_game_data(self):
        self.auth()
        response = self.order()
        self.assertRegex(response.data['orderId'], r'^[A-Z0-9]{20}$')
        self.assertIn(f"transaction_param={response.data['orderId']}&", response.data['clickUrl'])

    def test_retrying_checkout_keeps_the_unpaid_order(self):
        self.auth()
        self.assertEqual(self.order().data['orderId'], self.order().data['orderId'])
        self.assertEqual(Order.objects.count(), 1)

    def test_buying_again_after_revocation_gets_a_new_order(self):
        self.auth()
        first = self.order().data['orderId']
        Order.objects.filter(order_id=first).update(status='paid')
        self.assertNotEqual(self.order().data['orderId'], first)
        self.assertEqual(Order.objects.get(order_id=first).status, 'paid')

    def test_old_format_order_is_not_reused(self):
        game = Game.objects.get(id='stray')
        Order.objects.create(
            order_id='uid__stray', user=self.user, game=game, user_email=self.user.email,
            game_title='Stray', game_slug='stray', amount=15000,
        )
        self.auth()
        self.assertRegex(self.order().data['orderId'], r'^[A-Z0-9]{20}$')

    def test_missing_click_settings_are_reported(self):
        self.auth()
        with override_settings(CLICK_SERVICE_ID=''):
            self.assertEqual(self.order().status_code, 503)


class AdminOrderListTests(APITestCase):
    def test_requires_admin(self):
        user = User.objects.create_user(email='user@example.com', id='uid')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        self.assertEqual(self.client.get('/api/v1/payments/admin/orders/').status_code, 403)
