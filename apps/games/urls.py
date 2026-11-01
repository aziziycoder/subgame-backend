from django.urls import path
from .views import GameListView, GameDetailView, SliderListView, AdminGameCreateUpdateView

urlpatterns = [
    path('', GameListView.as_view(), name='game-list'),
    path('sliders/', SliderListView.as_view(), name='slider-list'),
    path('<slug:slug>/', GameDetailView.as_view(), name='game-detail'),
    path('admin/manage/', AdminGameCreateUpdateView.as_view(), name='admin-game-create'),
    path('admin/manage/<str:id>/', AdminGameCreateUpdateView.as_view(), name='admin-game-update-delete'),
]
