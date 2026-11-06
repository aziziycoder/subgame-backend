from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    GoogleAuthView,
    CurrentUserView,
    AdminUsersListView,
    AdminUserDetailView,
    AdminUsersWithLicensesView,
)

from .dashboard import AdminDashboardStatsView

urlpatterns = [
    path('google/', GoogleAuthView.as_view(), name='auth-google'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('me/', CurrentUserView.as_view(), name='auth-me'),
    path('admin/users/', AdminUsersListView.as_view(), name='admin-users-list'),
    path('admin/users/<str:user_id>/role/', AdminUserDetailView.as_view(), name='admin-user-role'),
    path('admin/users-with-licenses/', AdminUsersWithLicensesView.as_view(), name='admin-users-with-licenses'),
    path('admin/dashboard-stats/', AdminDashboardStatsView.as_view(), name='admin-dashboard-stats'),
]

