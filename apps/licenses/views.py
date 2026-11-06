import re
import secrets
from datetime import timedelta
from django.db import transaction
from django.db.models import Count, Max, Q
from django.utils import timezone
from rest_framework import views, status, permissions
from rest_framework.response import Response

from apps.games.models import Game
from .models import License, DeviceSession
from .serializers import LicenseSerializer, DeviceSessionSerializer
from apps.users.permissions import IsAdmin


# SHA-256 hex digest produced by the launcher; rejects placeholders such as LOCAL_HWID.
HWID_PATTERN = re.compile(r'^[A-F0-9]{64}$')


class MyLicensesView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Revoked licenses are included so the site can show their state; clients check `status`.
        licenses = License.objects.filter(user=request.user)
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

        if not HWID_PATTERN.match(str(hwid)):
            return Response({'error': 'Qurilma identifikatori noto‘g‘ri.'}, status=status.HTTP_400_BAD_REQUEST)

        # Allow admin bypass
        if request.user.is_admin:
            return Response({'success': True, 'message': 'Admin VIP ruxsati.'})

        with transaction.atomic():
            license_obj = License.objects.select_for_update().filter(
                Q(game_id=game_id) | Q(game__slug=game_id),
                user=request.user,
                status='active',
            ).first()

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
                    'boundDeviceName': device_name,
                    'license': LicenseSerializer(license_obj).data,
                })

        # 2. If already bound -> verify matching HWID
        if license_obj.hwid == hwid:
            return Response({
                'success': True,
                'message': 'Litsenziya tasdiqlandi.',
                'boundDeviceName': license_obj.bound_device_name,
                'license': LicenseSerializer(license_obj).data,
            })

        # 3. Mismatch -> Blocked!
        return Response({
            'error': f'Ushbu o‘yin litsenziyasi boshqa kompyuterga ({license_obj.bound_device_name or "boshqa PC"}) bog‘langan.',
            'isBoundToAnotherDevice': True,
            'boundDeviceName': license_obj.bound_device_name,
        }, status=status.HTTP_403_FORBIDDEN)


class GameLicenseStatsView(views.APIView):
    """Public per-game license counters, keyed by both game id and slug."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        rows = License.objects.filter(status='active').values('game_id', 'game_slug').annotate(
            total=Count('id'),
            bound=Count('id', filter=Q(hwid__isnull=False) & ~Q(hwid='')),
        )
        stats = {}
        for row in rows:
            for key in {row['game_id'], row['game_slug']}:
                if not key:
                    continue
                entry = stats.setdefault(key, {'total': 0, 'bound': 0})
                entry['total'] += row['total']
                entry['bound'] += row['bound']
        return Response(stats)


# Device Session (6-digit Pairing Code) for Web <-> Launcher
class CreateDeviceSessionView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        device_id = request.data.get('deviceId', '')
        device_name = request.data.get('deviceName', '')
        hwid = request.data.get('hwid', '')

        # Generate unique 6-digit code
        for _ in range(10):
            code = f"{secrets.randbelow(900000) + 100000}"
            if not DeviceSession.objects.filter(session_id=code, status='pending').exists():
                break

        session = DeviceSession.objects.create(
            session_id=code,
            poll_token=secrets.token_urlsafe(32),
            device_id=device_id,
            device_name=device_name,
            hwid=hwid,
            status='pending',
            expires_at=timezone.now() + timedelta(minutes=10)
        )

        return Response({
            'sessionId': session.session_id,
            'code': session.session_id,
            'pollToken': session.poll_token,
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

    def post(self, request, session_id):
        session = DeviceSession.objects.filter(session_id=session_id).first()
        poll_token = str(request.data.get('pollToken', ''))
        if not session or not session.poll_token or not secrets.compare_digest(session.poll_token, poll_token):
            return Response({'status': 'not_found'}, status=status.HTTP_404_NOT_FOUND)

        if session.status == 'pending' and session.expires_at < timezone.now():
            return Response({'status': 'expired'})

        if session.status == 'approved' and session.user:
            # Tokens are handed out exactly once.
            claimed = DeviceSession.objects.filter(session_id=session_id, status='approved').update(status='consumed')
            if not claimed:
                return Response({'status': 'consumed'})

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
LICENSES_PAGE_SIZE = 50
LICENSES_MAX_PAGE_SIZE = 500
BOUND_Q = Q(hwid__isnull=False) & ~Q(hwid='')
LICENSE_SORTS = {
    'newest': ('-created_at', 'id'),
    'oldest': ('created_at', 'id'),
    'recently_bound': ('-bound_at', '-created_at', 'id'),
}


def _positive_int(value, default, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 1:
        return default
    return min(number, maximum) if maximum else number


def _filtered_licenses(params):
    licenses = License.objects.all()
    search = (params.get('search') or '').strip()
    if search:
        licenses = licenses.filter(
            Q(user_email__icontains=search) | Q(user_name__icontains=search) | Q(user__id__icontains=search)
            | Q(game_title__icontains=search) | Q(hwid__icontains=search)
            | Q(bound_device_name__icontains=search) | Q(id__icontains=search)
            | Q(payment_ref__icontains=search)
        )
    game = params.get('game')
    if game and game != 'all':
        licenses = licenses.filter(Q(game_id=game) | Q(game_slug=game))
    license_status = params.get('status')
    if license_status in ('active', 'revoked'):
        licenses = licenses.filter(status=license_status)
    device = params.get('device')
    if device == 'bound':
        licenses = licenses.filter(BOUND_Q)
    elif device == 'unbound':
        licenses = licenses.exclude(BOUND_Q)
    provider = params.get('provider')
    if provider and provider != 'all':
        licenses = licenses.filter(payment_provider=provider)
    return licenses


class AdminLicenseListView(views.APIView):
    """One page of licenses; every filter runs in the database."""
    permission_classes = [IsAdmin]

    def get(self, request):
        params = request.query_params
        page_size = _positive_int(params.get('page_size'), LICENSES_PAGE_SIZE, LICENSES_MAX_PAGE_SIZE)
        page = _positive_int(params.get('page'), 1)
        licenses = _filtered_licenses(params)

        total = licenses.count()
        total_pages = max(1, -(-total // page_size))
        page = min(page, total_pages)
        offset = (page - 1) * page_size
        order = LICENSE_SORTS.get(params.get('sort'), LICENSE_SORTS['newest'])
        rows = licenses.order_by(*order)[offset:offset + page_size]

        return Response({
            'licenses': LicenseSerializer(rows, many=True).data,
            'pagination': {'page': page, 'pageSize': page_size, 'total': total, 'totalPages': total_pages},
        })


class AdminLicenseSummaryView(views.APIView):
    """Totals and per-game counts for the licenses section, without the licenses themselves."""
    permission_classes = [IsAdmin]

    def get(self, request):
        totals = License.objects.aggregate(
            total=Count('pk'),
            active=Count('pk', filter=Q(status='active')),
            revoked=Count('pk', filter=Q(status='revoked')),
            bound=Count('pk', filter=BOUND_Q),
        )
        totals['uniqueUsers'] = License.objects.values('user_id').distinct().count()

        rows = (
            License.objects.values('game_id')
            .annotate(
                total=Count('pk'),
                active=Count('pk', filter=Q(status='active')),
                bound=Count('pk', filter=BOUND_Q),
                lastClaimedAt=Max('created_at'),
            )
            .order_by('-total', 'game_id')
        )
        games = {g['id']: g for g in Game.objects.values('id', 'title', 'slug', 'cover', 'card_image', 'genres')}
        groups = []
        for row in rows:
            info = games.get(row['game_id'], {})
            groups.append({
                'gameId': row['game_id'],
                'gameTitle': info.get('title') or row['game_id'],
                'gameSlug': info.get('slug') or row['game_id'],
                'coverImage': info.get('card_image') or info.get('cover') or '',
                'genres': info.get('genres') or [],
                'totalLicenses': row['total'],
                'activeLicenses': row['active'],
                'boundDevicesCount': row['bound'],
                'percentage': round(row['total'] * 100 / totals['total']) if totals['total'] else 0,
                'lastClaimedAt': row['lastClaimedAt'],
            })

        providers = [
            row['payment_provider'] or 'none'
            for row in License.objects.values('payment_provider').distinct().order_by('payment_provider')
        ]
        # Revoked licenses that nobody paid for; the admin may delete them in bulk.
        unpaid_revoked = list(
            License.objects.filter(status='revoked', paid_amount=0).exclude(payment_provider='click')
            .values_list('id', flat=True)
        )

        return Response({
            'stats': {
                'totalLicenses': totals['total'],
                'activeLicenses': totals['active'],
                'revokedLicenses': totals['revoked'],
                'totalBoundDevices': totals['bound'],
                'totalUniqueUsers': totals['uniqueUsers'],
                'totalGamesClaimed': len(groups),
            },
            'groups': groups,
            'providers': sorted(set(providers)),
            'unpaidRevokedIds': unpaid_revoked,
        })


class AdminLicenseManageView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
        licenses = License.objects.all().order_by('-created_at')
        return Response(LicenseSerializer(licenses, many=True).data)

    def post(self, request):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)

        user_id = request.data.get('userId')
        game_id = request.data.get('gameId')
        game_title = request.data.get('gameTitle', '')
        game_slug = request.data.get('gameSlug', '')
        payment_provider = request.data.get('paymentProvider', 'admin_grant')
        paid_amount = request.data.get('paidAmount', 0)
        user_email = request.data.get('userEmail', '')
        user_name = request.data.get('userName', '')
        user_photo = request.data.get('userPhoto', '')
        admin_note = request.data.get('adminNote', '')
        granted_by = request.data.get('grantedBy', '')

        if not user_id or not game_id:
            return Response({'error': 'userId va gameId talab qilinadi.'}, status=status.HTTP_400_BAD_REQUEST)

        from apps.users.models import User
        # 1. Resolve user
        user = User.objects.filter(id=user_id).first()
        if not user and user_email:
            user = User.objects.filter(email=user_email.lower()).first()
        if not user:
            user = User.objects.create(
                id=user_id,
                email=user_email.lower() if user_email else f"{user_id}@subgame.uz",
                display_name=user_name or (user_email.split('@')[0] if user_email else 'Foydalanuvchi'),
                photo_url=user_photo or '',
                role='user'
            )

        # 2. Resolve game
        game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=game_slug or game_id).first()
        if not game:
            game = Game.objects.create(
                id=game_id,
                slug=game_slug or game_id,
                title=game_title or game_id,
                cover='https://subgame.uz/favicon.ico'
            )

        license_id = f"{user.id}_{game.id}"
        lic = License.objects.filter(id=license_id).first() or License.objects.filter(user=user, game=game).first()

        if not lic:
            lic = License.objects.create(
                id=license_id,
                user=user,
                game=game,
                user_email=user.email,
                user_name=user.display_name,
                user_photo=user.photo_url,
                game_title=game_title or game.title,
                game_slug=game_slug or game.slug,
                status='active',
                payment_provider=payment_provider,
                paid_amount=paid_amount or 0,
                admin_note=admin_note,
                granted_by=granted_by
            )
        elif lic.status == 'active':
            return Response(
                {'error': f'Ushbu foydalanuvchida "{lic.game_title}" o‘yini uchun allaqachon faol litsenziya mavjud!'},
                status=status.HTTP_409_CONFLICT
            )
        else:
            lic.status = 'active'
            lic.payment_provider = payment_provider
            lic.paid_amount = paid_amount or 0
            lic.admin_note = admin_note
            lic.granted_by = granted_by
            lic.save()

        return Response({
            'success': True,
            'message': 'Litsenziya muvaffaqiyatli saqlandi.',
            'license': LicenseSerializer(lic).data
        })

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
