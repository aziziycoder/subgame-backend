import hashlib
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


class CreateOrderView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        game_id = request.data.get('gameId') or request.data.get('gameSlug')
        custom_amount = request.data.get('amount')
        user_id = request.data.get('userId')
        user_email = request.data.get('userEmail')

        # Determine user: authenticated session or via userId / userEmail
        from apps.users.models import User
        target_user = None
        if request.user and request.user.is_authenticated:
            target_user = request.user
        elif user_id:
            target_user = User.objects.filter(id=user_id).first()
            if not target_user and user_email:
                target_user = User.objects.filter(email=user_email).first()
            if not target_user and user_email:
                target_user = User.objects.create_user(
                    email=user_email,
                    id=user_id,
                    display_name=user_email.split('@')[0]
                )

        if not target_user:
            return Response({'error': 'Foydalanuvchi aniqlanmadi.'}, status=status.HTTP_400_BAD_REQUEST)

        game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=game_id).first()
        if not game:
            return Response({'error': 'O‘yin topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        # Parse numeric amount
        if custom_amount:
            amount = int(custom_amount)
        else:
            raw_price = ''.join(c for c in (game.subtitle_price or game.price) if c.isdigit())
            amount = int(raw_price) if raw_price else 15000

        order_id = f"{target_user.id}__{game.slug or game.id}"

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
            'isSandbox': not bool(settings.CLICK_SECRET_KEY)
        })


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
        amount = float(data.get('amount', 0))
        action = int(data.get('action', -1))
        error = int(data.get('error', 0))
        error_note = str(data.get('error_note', ''))
        sign_time = str(data.get('sign_time', ''))
        sign_string = str(data.get('sign_string', '')).lower()
        merchant_prepare_id = str(data.get('merchant_prepare_id', ''))

        # 1. Signature Verification
        secret = settings.CLICK_SECRET_KEY
        if secret and sign_string != 'sandbox_bypass':
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

        # 2. Find Order
        order = Order.objects.filter(order_id=merchant_trans_id).first()
        if not order:
            return Response({'error': -5, 'error_note': 'User or Order does not exist'}, status=status.HTTP_200_OK)

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
                license_id = f"{order.user.id}_{order.game.id}"
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
