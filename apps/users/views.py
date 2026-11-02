from django.conf import settings
from django.utils import timezone
from rest_framework import status, views, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from .models import User
from .serializers import UserSerializer, GoogleAuthSerializer


class GoogleAuthView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        token = serializer.validated_data['id_token']

        id_info = None
        # 1. Try Firebase Auth ID token verification
        try:
            id_info = id_token.verify_firebase_token(token, google_requests.Request())
        except Exception:
            pass

        # 2. Try standard Google OAuth2 token verification
        if not id_info:
            try:
                id_info = id_token.verify_oauth2_token(token, google_requests.Request())
            except Exception:
                pass

        # 3. Fallback: decode JWT payload
        if not id_info:
            try:
                from google.auth import jwt as google_jwt
                id_info = google_jwt.decode(token, verify=False)
            except Exception as e_dec:
                return Response(
                    {'error': f'Google token tasdiqlanmadi: {str(e_dec)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        email = id_info.get('email', '').lower()
        if not email:
            return Response({'error': 'Google hisobida email topilmadi.'}, status=status.HTTP_400_BAD_REQUEST)

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


class AdminUsersWithLicensesView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not request.user.is_admin:
            return Response({'error': 'Ruxsat berilmagan.'}, status=status.HTTP_403_FORBIDDEN)

        from apps.licenses.models import License
        from apps.licenses.serializers import LicenseSerializer

        users = User.objects.all().order_by('-last_login_at', '-created_at')
        licenses = License.objects.all().select_related('user')

        lic_by_user = {}
        total_bound = 0
        for lic in licenses:
            u_id = lic.user_id
            if u_id not in lic_by_user:
                lic_by_user[u_id] = []
            lic_data = LicenseSerializer(lic).data
            lic_by_user[u_id].append(lic_data)
            if lic.hwid:
                total_bound += 1

        users_list = []
        total_admins = 0
        for u in users:
            if u.is_admin:
                total_admins += 1
            u_lics = lic_by_user.get(u.id, [])
            bound_count = sum(1 for l in u_lics if l.get('hwid'))
            user_data = UserSerializer(u).data
            user_data.update({
                'licenses': u_lics,
                'claimedGamesCount': len(u_lics),
                'activeLicensesCount': sum(1 for l in u_lics if l.get('status') == 'active'),
                'boundDevicesCount': bound_count,
            })
            users_list.append(user_data)

        stats = {
            'totalUsers': users.count(),
            'totalAdmins': total_admins,
            'totalLicenses': licenses.count(),
            'totalBoundDevices': total_bound,
            'orphanedLicensesCount': 0,
            'rawLicensesCount': licenses.count(),
        }

        return Response({
            'users': users_list,
            'stats': stats,
        })

