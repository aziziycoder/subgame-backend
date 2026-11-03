from django.urls import path
from .views import (
    GameListView,
    GameDetailView,
    SliderListView,
    AdminGameCreateUpdateView,
    AdminSliderListCreateView,
    AdminSliderDetailView,
    AdminFileUploadView,
)

urlpatterns = [
    path('', GameListView.as_view(), name='game-list'),
    path('sliders/', SliderListView.as_view(), name='slider-list'),
    path('<slug:slug>/', GameDetailView.as_view(), name='game-detail'),
    path('admin/sliders/', AdminSliderListCreateView.as_view(), name='admin-slider-list'),
    path('admin/sliders/<str:id>/', AdminSliderDetailView.as_view(), name='admin-slider-detail'),
    path('admin/upload/', AdminFileUploadView.as_view(), name='admin-file-upload'),
    path('admin/manage/', AdminGameCreateUpdateView.as_view(), name='admin-game-create'),
    path('admin/manage/<str:id>/', AdminGameCreateUpdateView.as_view(), name='admin-game-update-delete'),
]
