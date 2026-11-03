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


def complete_payload(amount, sign_string=None):
    payload = {
        'click_trans_id': '1', 'service_id': '2', 'click_paydoc_id': '3',
        'merchant_trans_id': ORDER_ID, 'merchant_prepare_id': ORDER_ID,
        'amount': amount, 'action': 1, 'error': 0, 'error_note': '', 'sign_time': 't',
    }
    payload['sign_string'] = sign_string or hashlib.md5(
        f"12{SECRET}{ORDER_ID}{ORDER_ID}{amount}1t".encode('utf-8')
    ).hexdigest()
    return payload


@override_settings(CLICK_SECRET_KEY=SECRET)
class ClickWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='user@example.com', id='uid')
        self.game = Game.objects.create(id='stray', slug='stray', title='Stray', cover='https://x/y.jpg', subtitle_price='15 000 so‘m')
        Order.objects.create(
            order_id=ORDER_ID, user=self.user, game=self.game, user_email=self.user.email,
            game_title='Stray', game_slug='stray', amount=15000,
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


class AdminOrderListTests(APITestCase):
    def test_requires_admin(self):
        user = User.objects.create_user(email='user@example.com', id='uid')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        self.assertEqual(self.client.get('/api/v1/payments/admin/orders/').status_code, 403)
