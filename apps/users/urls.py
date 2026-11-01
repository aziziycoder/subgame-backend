from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import GoogleAuthView, CurrentUserView, AdminUsersListView

urlpatterns = [
    path('google/', GoogleAuthView.as_view(), name='auth-google'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('me/', CurrentUserView.as_view(), name='auth-me'),
    path('admin/users/', AdminUsersListView.as_view(), name='admin-users-list'),
]
