from django.contrib import admin
from django.urls import path, include
from apps.payments.views import ClickWebhookView

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API v1
    path('api/v1/auth/', include('apps.users.urls')),
    path('api/v1/games/', include('apps.games.urls')),
    path('api/v1/licenses/', include('apps.licenses.urls')),
    path('api/v1/payments/', include('apps.payments.urls')),
    path('api/v1/issues/', include('apps.issues.urls')),
    
    # Backward compatible endpoints for existing Click Merchant URL config
    path('api/click', ClickWebhookView.as_view(), name='click-legacy'),
    path('api/click/', ClickWebhookView.as_view(), name='click-legacy-slash'),
    path('api/click/prepare', ClickWebhookView.as_view(), name='click-legacy-prepare'),
    path('api/click/complete', ClickWebhookView.as_view(), name='click-legacy-complete'),
]
