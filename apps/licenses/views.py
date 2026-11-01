import random
from datetime import timedelta
from django.utils import timezone
from rest_framework import views, status, permissions
from rest_framework.response import Response

from apps.games.models import Game
from .models import License, DeviceSession
from .serializers import LicenseSerializer, DeviceSessionSerializer


class MyLicensesView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        licenses = License.objects.filter(user=request.user, status='active')
        serializer = LicenseSerializer(licenses, many=True)
        # Return as dictionary key-value {gameId: license} for instant frontend/launcher lookup
        license_map = {lic['gameId']: lic for lic in serializer.data}
        return Response(license_map)


class ClaimFreeLicenseView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        game_id = request.data.get('gameId') or request.data.get('gameSlug')
        if not game_id:
            return Response({'error': 'gameId kiritilmadi.'}, status=status.HTTP_400_BAD_REQUEST)

        game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=game_id).first()
        if not game:
            return Response({'error': 'O‘yin topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        # SECURITY: Strictly block claiming paid games for non-admins!
        if game.is_paid and not request.user.is_admin:
            return Response(
                {'error': 'Ushbu o‘yin pullik. Litsenziya faqat to‘lov muvaffaqiyatli amalga oshirilganda avtomatik beriladi.'},
                status=status.HTTP_403_FORBIDDEN
            )

        license_id = f"{request.user.id}_{game.id}"
        license_obj, created = License.objects.get_or_create(
            id=license_id,
            defaults={
                'user': request.user,
                'game': game,
                'user_email': request.user.email,
                'user_name': request.user.display_name,
                'user_photo': request.user.photo_url,
                'game_title': game.title,
                'game_slug': game.slug,
                'status': 'active',
                'payment_provider': 'free',
            }
        )

        if not created and license_obj.status != 'active':
            license_obj.status = 'active'
            license_obj.save(update_fields=['status', 'updated_at'])

        return Response({
            'success': True,
            'message': 'Litsenziya muvaffaqiyatli biriktirildi.',
            'license': LicenseSerializer(license_obj).data
        })


class BindHwidView(views.APIView):
    """
    Launcher 1-PC DRM Binding:
    Binds the license to the machine's unique HWID.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        game_id = request.data.get('gameId')
        hwid = request.data.get('hwid')
        device_name = request.data.get('deviceName', '')

        if not game_id or not hwid:
            return Response({'error': 'gameId va hwid kiritilishi shart.'}, status=status.HTTP_400_BAD_REQUEST)

        # Allow admin bypass
        if request.user.is_admin:
            return Response({'success': True, 'message': 'Admin VIP ruxsati.'})

        license_id = f"{request.user.id}_{game_id}"
        license_obj = License.objects.filter(id=license_id, status='active').first()
        if not license_obj:
            # Try searching by game slug
            license_obj = License.objects.filter(user=request.user, game__slug=game_id, status='active').first()

        if not license_obj:
            return Response({'error': 'Ushbu o‘yin uchun faol litsenziya topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        # 1. If not yet bound -> bind to this machine
        if not license_obj.hwid:
            license_obj.hwid = hwid
            license_obj.bound_at = timezone.now()
            license_obj.bound_device_name = device_name
            license_obj.save(update_fields=['hwid', 'bound_at', 'bound_device_name', 'updated_at'])
            return Response({
                'success': True,
                'message': 'Litsenziya ushbu kompyuterga muvaffaqiyatli bog‘landi.',
                'boundDeviceName': device_name
            })

        # 2. If already bound -> verify matching HWID
        if license_obj.hwid == hwid:
            return Response({
                'success': True,
                'message': 'Litsenziya tasdiqlandi.',
                'boundDeviceName': license_obj.bound_device_name
            })

        # 3. Mismatch -> Blocked!
        return Response({
            'error': f'Ushbu o‘yin litsenziyasi boshqa kompyuterga ({license_obj.bound_device_name or "boshqa PC"}) bog‘langan.',
            'isBoundToAnotherDevice': True
        }, status=status.HTTP_403_FORBIDDEN)


# Device Session (6-digit Pairing Code) for Web <-> Launcher
class CreateDeviceSessionView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        device_id = request.data.get('deviceId', '')
        device_name = request.data.get('deviceName', '')
        hwid = request.data.get('hwid', '')

        # Generate unique 6-digit code
        for _ in range(10):
            code = f"{random.randint(100000, 999999)}"
            if not DeviceSession.objects.filter(session_id=code, status='pending').exists():
                break

        session = DeviceSession.objects.create(
            session_id=code,
            device_id=device_id,
            device_name=device_name,
            hwid=hwid,
            status='pending',
            expires_at=timezone.now() + timedelta(minutes=10)
        )

        return Response({
            'sessionId': session.session_id,
            'code': session.session_id,
            'expiresAt': session.expires_at.isoformat()
        })


class ApproveDeviceSessionView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = request.data.get('code') or request.data.get('sessionId')
        session = DeviceSession.objects.filter(session_id=code, status='pending').first()

        if not session or session.expires_at < timezone.now():
            return Response({'error': 'Kod noto‘g‘ri yoki muddati o‘tgan.'}, status=status.HTTP_400_BAD_REQUEST)

        session.status = 'approved'
        session.user = request.user
        session.save(update_fields=['status', 'user'])

        return Response({'success': True, 'message': 'Qurilma hisobingizga muvaffaqiyatli ulandi!'})


class PollDeviceSessionView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, session_id):
        session = DeviceSession.objects.filter(session_id=session_id).first()
        if not session:
            return Response({'status': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        if session.status == 'approved' and session.user:
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(session.user)
            from apps.users.serializers import UserSerializer
            return Response({
                'status': 'approved',
                'user': UserSerializer(session.user).data,
                'tokens': {
                    'access': str(refresh.access_token),
                    'refresh': str(refresh)
                }
            })

        return Response({'status': session.status})


# Admin License Management
class AdminLicenseManageView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
        licenses = License.objects.all().order_by('-created_at')
        return Response(LicenseSerializer(licenses, many=True).data)

    def delete(self, request, license_id):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
        lic = License.objects.filter(id=license_id).first()
        if not lic:
            return Response({'error': 'Litsenziya topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
        lic.delete()
        return Response({'success': True, 'message': 'Litsenziya o‘chirildi.'})

    def patch(self, request, license_id):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
        lic = License.objects.filter(id=license_id).first()
        if not lic:
            return Response({'error': 'Litsenziya topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        action = request.data.get('action')
        if action == 'reset_hwid':
            lic.hwid = None
            lic.bound_at = None
            lic.bound_device_name = None
            lic.save(update_fields=['hwid', 'bound_at', 'bound_device_name', 'updated_at'])
            return Response({'success': True, 'message': 'HWID qayta tiklandi.'})

        if action == 'toggle_status':
            lic.status = 'revoked' if lic.status == 'active' else 'active'
            lic.save(update_fields=['status', 'updated_at'])
            return Response({'success': True, 'status': lic.status})

        return Response({'error': 'Noto‘g‘ri amal.'}, status=status.HTTP_400_BAD_REQUEST)
