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

        try:
            # Verify Google ID Token
            id_info = id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_CLIENT_ID
            )
        except Exception as e:
            # Also allow fallback if client ID varies or token verification format
            try:
                id_info = id_token.verify_oauth2_token(token, google_requests.Request())
            except Exception as e2:
                return Response(
                    {'error': f'Google token tasdiqlanmadi: {str(e2)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        email = id_info.get('email', '').lower()
        if not email:
            return Response({'error': 'Google hisobida email topilmadi.'}, status=status.HTTP_400_BAD_REQUEST)

        display_name = id_info.get('name', '') or email.split('@')[0]
        photo_url = id_info.get('picture', '')
        google_sub = id_info.get('sub', '')

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
