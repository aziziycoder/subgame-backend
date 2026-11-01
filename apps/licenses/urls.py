from django.urls import path
from .views import (
    MyLicensesView,
    ClaimFreeLicenseView,
    BindHwidView,
    CreateDeviceSessionView,
    ApproveDeviceSessionView,
    PollDeviceSessionView,
    AdminLicenseManageView,
)

urlpatterns = [
    path('my/', MyLicensesView.as_view(), name='my-licenses'),
    path('claim-free/', ClaimFreeLicenseView.as_view(), name='claim-free-license'),
    path('bind-hwid/', BindHwidView.as_view(), name='bind-hwid'),
    
    # Device pairing
    path('device/create/', CreateDeviceSessionView.as_view(), name='device-create'),
    path('device/approve/', ApproveDeviceSessionView.as_view(), name='device-approve'),
    path('device/poll/<str:session_id>/', PollDeviceSessionView.as_view(), name='device-poll'),
    
    # Admin
    path('admin/', AdminLicenseManageView.as_view(), name='admin-licenses-list'),
    path('admin/<str:license_id>/', AdminLicenseManageView.as_view(), name='admin-license-action'),
]
