import requests as http_requests
from django.conf import settings
from django.utils import timezone
from rest_framework import status, views, permissions
from rest_framework.response import Response
from django.db.models import Count, Prefetch, Q
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .models import User
from .permissions import IsAdmin
from .serializers import UserSerializer, GoogleAuthSerializer


def _identity_from_id_token(token):
    """Returns verified claims, or None. Audience is always checked: without it
    a token issued for any other Google client or Firebase project would pass."""
    transport = google_requests.Request()
    verifiers = (
        (id_token.verify_oauth2_token, settings.GOOGLE_CLIENT_ID),
        # Transition only: remove once no site bundle signs in through Firebase Auth.
        (id_token.verify_firebase_token, settings.FIREBASE_PROJECT_ID),
    )
    for verify, audience in verifiers:
        try:
            return verify(token, transport, audience=audience)
        except Exception:
            continue
    return None


def _identity_from_access_token(token):
    """Validates a Google Identity Services access token issued to our own client."""
    try:
        token_info = http_requests.get(
            'https://oauth2.googleapis.com/tokeninfo',
            params={'access_token': token},
            timeout=10,
        )
        if token_info.status_code != 200:
            return None
        claims = token_info.json()
        if claims.get('aud') != settings.GOOGLE_CLIENT_ID:
            return None

        profile = http_requests.get(
            'https://openidconnect.googleapis.com/v1/userinfo',
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        if profile.status_code == 200:
            claims = {**profile.json(), **claims}
        return claims
    except (http_requests.RequestException, ValueError):
        return None


class GoogleAuthView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        access_token = serializer.validated_data.get('access_token')
        if access_token:
            id_info = _identity_from_access_token(access_token)
        else:
            id_info = _identity_from_id_token(serializer.validated_data['id_token'])

        if not id_info:
            return Response({'error': 'Google token tasdiqlanmadi.'}, status=status.HTTP_401_UNAUTHORIZED)

        email = id_info.get('email', '').lower()
        if not email:
            return Response({'error': 'Google hisobida email topilmadi.'}, status=status.HTTP_400_BAD_REQUEST)

        if str(id_info.get('email_verified', '')).lower() != 'true':
            return Response({'error': 'Google hisobidagi email tasdiqlanmagan.'}, status=status.HTTP_401_UNAUTHORIZED)

        display_name = id_info.get('name', '') or email.split('@')[0]
        photo_url = id_info.get('picture', '')
        google_sub = id_info.get('user_id') or id_info.get('sub', '')

        # Check or create user
        user = User.objects.filter(email=email).first()
        is_master = email in [e.lower() for e in settings.ADMIN_EMAILS]

        if not user:
            role = 'admin' if is_master else 'user'
            # Use google sub or generate uid
            user_id = google_sub[:28] if len(google_sub) >= 28 else google_sub
            user = User.objects.create(
                id=user_id,
                email=email,
                display_name=display_name,
                photo_url=photo_url,
                role=role,
                is_staff=is_master,
                last_login_at=timezone.now(),
            )
        else:
            user.display_name = display_name or user.display_name
            user.photo_url = photo_url or user.photo_url
            if is_master:
                user.role = 'admin'
                user.is_staff = True
            user.last_login_at = timezone.now()
            user.save(update_fields=['display_name', 'photo_url', 'role', 'is_staff', 'last_login_at'])

        # Generate JWT
        refresh = RefreshToken.for_user(user)

        return Response({
            'user': UserSerializer(user).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })


class CurrentUserView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class AdminUsersListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)

        users = User.objects.all().order_by('-created_at')
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)


class AdminUserDetailView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, user_id):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)
        user = User.objects.filter(id=user_id).first()
        if not user:
            return Response({'error': 'Foydalanuvchi topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
        role = request.data.get('role')
        if role in ['admin', 'user']:
            user.role = role
            user.is_staff = (role == 'admin')
            user.save(update_fields=['role', 'is_staff'])
            return Response({'success': True, 'user': UserSerializer(user).data})
        return Response({'error': 'Noto‘g‘ri rol.'}, status=status.HTTP_400_BAD_REQUEST)


USERS_PAGE_SIZE = 50
USERS_MAX_PAGE_SIZE = 500
USER_FILTERS = ('all', 'admin', 'user', 'with_devices')


def _bound_q(prefix=''):
    return Q(**{f'{prefix}hwid__isnull': False}) & ~Q(**{f'{prefix}hwid': ''})


def _positive_int(value, default, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number < 1:
        return default
    return min(number, maximum) if maximum else number


class AdminUsersWithLicensesView(views.APIView):
    """One page of users with their licenses. Search and filter run in the
    database, so they cover every user, not only the page that is shown."""
    permission_classes = [IsAdmin]

    def get(self, request):
        from apps.licenses.models import License
        from apps.licenses.serializers import LicenseSerializer

        page_size = _positive_int(request.query_params.get('page_size'), USERS_PAGE_SIZE, USERS_MAX_PAGE_SIZE)
        page = _positive_int(request.query_params.get('page'), 1)
        search = (request.query_params.get('search') or '').strip()
        user_filter = request.query_params.get('filter') or 'all'
        if user_filter not in USER_FILTERS:
            user_filter = 'all'

        admin_q = Q(role='admin') | Q(is_superuser=True)
        users = User.objects.annotate(
            claimed_count=Count('licenses'),
            active_count=Count('licenses', filter=Q(licenses__status='active')),
            bound_count=Count('licenses', filter=_bound_q('licenses__')),
        )
        if search:
            users = users.filter(
                Q(email__icontains=search) | Q(display_name__icontains=search) | Q(id__icontains=search)
            )

        searched = users
        if user_filter == 'admin':
            users = users.filter(admin_q)
        elif user_filter == 'user':
            users = users.exclude(admin_q)
        elif user_filter == 'with_devices':
            users = users.filter(bound_count__gt=0)

        total = users.count()
        total_pages = max(1, -(-total // page_size))
        page = min(page, total_pages)
        offset = (page - 1) * page_size

        page_users = list(
            users.order_by('-last_login_at', '-created_at', 'id').prefetch_related(
                Prefetch('licenses', queryset=License.objects.order_by('-created_at'))
            )[offset:offset + page_size]
        )

        users_list = []
        for u in page_users:
            user_data = UserSerializer(u).data
            user_data.update({
                'licenses': LicenseSerializer(u.licenses.all(), many=True).data,
                'claimedGamesCount': u.claimed_count,
                'activeLicensesCount': u.active_count,
                'boundDevicesCount': u.bound_count,
            })
            users_list.append(user_data)

        searched_ids = searched.values('id')
        filter_counts = User.objects.filter(id__in=searched_ids).aggregate(
            all=Count('id'),
            admin=Count('id', filter=admin_q),
        )
        filter_counts['user'] = filter_counts['all'] - filter_counts['admin']
        filter_counts['with_devices'] = User.objects.filter(
            id__in=searched_ids, licenses__in=License.objects.filter(_bound_q())
        ).distinct().count()

        license_totals = License.objects.aggregate(total=Count('id'), bound=Count('id', filter=_bound_q()))
        stats = {
            'totalUsers': User.objects.count(),
            'totalAdmins': User.objects.filter(admin_q).count(),
            'totalLicenses': license_totals['total'],
            'totalBoundDevices': license_totals['bound'],
            'orphanedLicensesCount': 0,
            'rawLicensesCount': license_totals['total'],
        }

        return Response({
            'users': users_list,
            'stats': stats,
            'filterCounts': filter_counts,
            'pagination': {
                'page': page,
                'pageSize': page_size,
                'total': total,
                'totalPages': total_pages,
            },
        })
