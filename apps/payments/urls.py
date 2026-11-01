from django.urls import path
from .views import CreateOrderView, ClickWebhookView

urlpatterns = [
    path('order/create/', CreateOrderView.as_view(), name='order-create'),
    path('click/', ClickWebhookView.as_view(), name='click-webhook'),
    path('click/prepare/', ClickWebhookView.as_view(), name='click-prepare'),
    path('click/complete/', ClickWebhookView.as_view(), name='click-complete'),
]
