import hashlib
import secrets
import string
import urllib.parse
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import views, status, permissions
from rest_framework.response import Response

from apps.games.models import Game
from apps.licenses.models import License
from .models import Order
from .serializers import OrderSerializer

ORDER_ID_ALPHABET = string.ascii_uppercase + string.digits
ORDER_ID_LENGTH = 20


def click_price(game):
    """Price in so'm with the same precedence as the site, or None when the game is free."""
    for value in (game.subtitle_price, game.price):
        digits = ''.join(c for c in (value or '') if c.isdigit())
        if digits and int(digits) > 0:
            return int(digits)
    return 15000 if game.is_paid else None


def generate_order_id():
    """Random id sent to Click as merchant_trans_id; it carries no user or game data."""
    return ''.join(secrets.choice(ORDER_ID_ALPHABET) for _ in range(ORDER_ID_LENGTH))


class CreateOrderView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        game_id = request.data.get('gameId') or request.data.get('gameSlug')
        target_user = request.user

        game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=game_id).first()
        if not game:
            return Response({'error': 'O‘yin topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        if not settings.CLICK_SERVICE_ID or not settings.CLICK_MERCHANT_ID:
            return Response({'error': 'Click to‘lovi hozircha sozlanmagan.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        if License.objects.filter(user=target_user, game=game, status='active').exists():
            return Response({'error': 'Bu o‘yin uchun sizda faol litsenziya bor.'}, status=status.HTTP_409_CONFLICT)

        # The price always comes from the game record, never from the client.
        amount = click_price(game)
        if amount is None:
            return Response({'error': 'Bu o‘yin bepul, to‘lov talab qilinmaydi.'}, status=status.HTTP_400_BAD_REQUEST)

        # Retrying a checkout keeps its unpaid order. Orders in the old {user}__{slug} format are left alone.
        existing_order = Order.objects.filter(user=target_user, game=game).exclude(status='paid').exclude(
            order_id__contains='__'
        ).order_by('-created_at').first()
        order_id = existing_order.order_id if existing_order else generate_order_id()

        order, _ = Order.objects.update_or_create(
            order_id=order_id,
            defaults={
                'user': target_user,
                'game': game,
                'user_email': target_user.email,
                'game_title': game.title,
                'game_slug': game.slug,
                'amount': amount,
                'currency': 'UZS',
                'status': 'pending',
                'payment_provider': 'click'
            }
        )

        return_url = f"https://subgame.uz/games/{game.slug}?payment=success&orderId={order_id}"
        click_url = (
            f"https://my.click.uz/services/pay?"
            f"service_id={settings.CLICK_SERVICE_ID}&"
            f"merchant_id={settings.CLICK_MERCHANT_ID}&"
            f"amount={amount}&"
            f"transaction_param={order_id}&"
            f"return_url={urllib.parse.quote(return_url)}"
        )

        return Response({
            'orderId': order.order_id,
            'amount': amount,
            'clickUrl': click_url,
            'isSandbox': False
        })


class AdminOrderListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
        return Response(OrderSerializer(Order.objects.all(), many=True).data)


class ClickWebhookView(views.APIView):
    """
    Official Click Merchant Webhook
    Handles Action 0 (Prepare) and Action 1 (Complete)
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        click_trans_id = str(data.get('click_trans_id', ''))
        service_id = str(data.get('service_id', ''))
        click_paydoc_id = str(data.get('click_paydoc_id', ''))
        merchant_trans_id = str(data.get('merchant_trans_id', ''))
        try:
            amount = float(data.get('amount', 0))
            action = int(data.get('action', -1))
            error = int(data.get('error', 0))
        except (TypeError, ValueError):
            return Response({'error': -8, 'error_note': 'Error in request from click'}, status=status.HTTP_200_OK)
        if action == -1:
            if request.path.rstrip('/').endswith('prepare'):
                action = 0
            elif request.path.rstrip('/').endswith('complete'):
                action = 1
        error_note = str(data.get('error_note', ''))
        sign_time = str(data.get('sign_time', ''))
        sign_string = str(data.get('sign_string', '')).lower()
        merchant_prepare_id = str(data.get('merchant_prepare_id', ''))

        # 1. Signature Verification
        secret = settings.CLICK_SECRET_KEY
        if not secret:
            return Response({'error': -1, 'error_note': 'SIGN CHECK FAILED!'}, status=status.HTTP_200_OK)

        raw_amt_str = str(data.get('amount', ''))
        if action == 0:
            expected_sign = hashlib.md5(
                f"{click_trans_id}{service_id}{secret}{merchant_trans_id}{raw_amt_str}{action}{sign_time}".encode('utf-8')
            ).hexdigest().lower()
        else:
            expected_sign = hashlib.md5(
                f"{click_trans_id}{service_id}{secret}{merchant_trans_id}{merchant_prepare_id}{raw_amt_str}{action}{sign_time}".encode('utf-8')
            ).hexdigest().lower()

        if sign_string != expected_sign:
            return Response({'error': -1, 'error_note': 'SIGN CHECK FAILED!'}, status=status.HTTP_200_OK)

        # 2. Find Order. Matching is exact, so an altered id fails at Prepare, before any money moves.
        order = Order.objects.filter(order_id=merchant_trans_id).first()

        if not order:
            return Response({'error': -5, 'error_note': 'User or Order does not exist'}, status=status.HTTP_200_OK)

        if int(amount) != order.amount:
            return Response({'error': -2, 'error_note': 'Incorrect parameter amount'}, status=status.HTTP_200_OK)

        # 3. Action 0: PREPARE
        if action == 0:
            if order.status == 'paid':
                return Response({'error': -4, 'error_note': 'Already paid'}, status=status.HTTP_200_OK)

            order.status = 'prepared'
            order.click_trans_id = click_trans_id
            order.click_paydoc_id = click_paydoc_id
            order.save(update_fields=['status', 'click_trans_id', 'click_paydoc_id', 'updated_at'])

            return Response({
                'click_trans_id': int(click_trans_id) if click_trans_id.isdigit() else click_trans_id,
                'merchant_trans_id': merchant_trans_id,
                'merchant_prepare_id': merchant_trans_id,
                'error': 0,
                'error_note': 'Success'
            }, status=status.HTTP_200_OK)

        # 4. Action 1: COMPLETE
        if action == 1:
            if order.status == 'paid':
                # A retry of the completed transaction must not fail; anything else is a second payment.
                if order.click_trans_id != click_trans_id:
                    return Response({'error': -4, 'error_note': 'Already paid'}, status=status.HTTP_200_OK)
                return Response({
                    'click_trans_id': int(click_trans_id) if click_trans_id.isdigit() else click_trans_id,
                    'merchant_trans_id': merchant_trans_id,
                    'merchant_confirm_id': click_trans_id,
                    'error': 0,
                    'error_note': 'Success'
                }, status=status.HTTP_200_OK)

            if error < 0:
                order.status = 'cancelled'
                order.error_note = error_note
                order.save(update_fields=['status', 'error_note', 'updated_at'])
                return Response({'error': -9, 'error_note': 'Transaction cancelled'}, status=status.HTTP_200_OK)

            with transaction.atomic():
                order.status = 'paid'
                order.paid_amount = int(amount)
                order.click_trans_id = click_trans_id
                order.click_paydoc_id = click_paydoc_id
                order.save(update_fields=['status', 'paid_amount', 'click_trans_id', 'click_paydoc_id', 'updated_at'])

                # Automatically grant or update license!
                # Imported licenses may have another id format, and user+game is unique.
                existing_license = License.objects.filter(user=order.user, game=order.game).first()
                license_id = existing_license.id if existing_license else f"{order.user.id}_{order.game.id}"
                License.objects.update_or_create(
                    id=license_id,
                    defaults={
                        'user': order.user,
                        'game': order.game,
                        'user_email': order.user.email,
                        'user_name': order.user.display_name,
                        'user_photo': order.user.photo_url,
                        'game_title': order.game.title,
                        'game_slug': order.game.slug,
                        'status': 'active',
                        'payment_provider': 'click',
                        'payment_ref': click_trans_id,
                        'paid_amount': int(amount),
                    }
                )

            return Response({
                'click_trans_id': int(click_trans_id) if click_trans_id.isdigit() else click_trans_id,
                'merchant_trans_id': merchant_trans_id,
                'merchant_confirm_id': click_trans_id,
                'error': 0,
                'error_note': 'Success'
            }, status=status.HTTP_200_OK)

        return Response({'error': -3, 'error_note': 'Action not found'}, status=status.HTTP_200_OK)
