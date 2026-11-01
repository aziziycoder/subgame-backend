from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.db.models import Q
from .models import Game, Slider
from .serializers import GameSerializer, SliderSerializer


class GameListView(generics.ListAPIView):
    serializer_class = GameSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None  # Return all for catalog filtering or provide custom

    def get_queryset(self):
        qs = Game.objects.all().order_by('-release_year', 'title')
        genre = self.request.query_params.get('genre')
        search = self.request.query_params.get('search')
        status_filter = self.request.query_params.get('status')

        if genre and genre != 'Barchasi':
            qs = qs.filter(genres__icontains=genre)
        if status_filter and status_filter != 'Barchasi':
            qs = qs.filter(subtitle_status=status_filter)
        if search:
            qs = qs.filter(
                Q(title__icontains=search) |
                Q(developer__icontains=search) |
                Q(short_description__icontains=search)
            )
        return qs


class GameDetailView(generics.RetrieveAPIView):
    serializer_class = GameSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_object(self):
        slug_or_id = self.kwargs['slug']
        return Game.objects.filter(Q(slug=slug_or_id) | Q(id=slug_or_id)).first()


class SliderListView(generics.ListAPIView):
    serializer_class = SliderSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    queryset = Slider.objects.filter(is_active=True).order_by('order')



class AdminGameCreateUpdateView(generics.CreateAPIView, generics.UpdateAPIView, generics.DestroyAPIView):
    serializer_class = GameSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'id'
    queryset = Game.objects.all()

    def check_permissions(self, request):
        super().check_permissions(request)
        if not request.user.is_admin:
            self.permission_denied(request, message='Faqat Admin o‘zgartira oladi.')
