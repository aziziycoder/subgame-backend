from django.db import IntegrityError, transaction
from django.db.models import Count
from rest_framework import generics, permissions, status, views
from rest_framework.response import Response

from apps.games.models import Game
from apps.users.permissions import IsAdmin
from . import steam
from .models import Issue, GameSuggestion, TranslationRequest, TranslationVote
from .serializers import IssueSerializer, GameSuggestionSerializer

REQUESTS_PAGE_SIZE = 20
MIN_SEARCH_LENGTH = 2
VALID_STATUSES = {value for value, _ in TranslationRequest.STATUS_CHOICES}


class IssueCreateView(generics.CreateAPIView):
    serializer_class = IssueSerializer
    permission_classes = [permissions.AllowAny]


class SuggestionCreateView(generics.CreateAPIView):
    serializer_class = GameSuggestionSerializer
    permission_classes = [permissions.AllowAny]


def site_games_by_steam_id():
    """Site games keyed by the Steam app ids in their store links."""
    games = {}
    for game in Game.objects.only('id', 'slug', 'title', 'subtitle_status', 'official_store_links'):
        for app_id in steam.steam_app_ids_of(game):
            games[app_id] = game
    return games


def game_summary(game):
    if not game:
        return None
    return {'slug': game.slug, 'title': game.title, 'subtitleStatus': game.subtitle_status}


def serialize_request(item, *, votes, has_voted, rank=None, include_admin=False):
    data = {
        'id': item.id,
        'steamAppId': item.steam_app_id,
        'title': item.title,
        'imageUrl': item.image_url,
        'status': item.status,
        'votes': votes,
        'hasVoted': has_voted,
        'rank': rank,
        'game': game_summary(item.game),
        'createdAt': item.created_at.isoformat(),
    }
    if include_admin:
        data['adminNote'] = item.admin_note
    return data


def voted_request_ids(user, request_ids):
    if not user.is_authenticated:
        return set()
    return set(
        TranslationVote.objects.filter(user=user, request_id__in=request_ids).values_list('request_id', flat=True)
    )


def vote_count(item):
    return TranslationVote.objects.filter(request=item).count()


class TranslationRequestListView(views.APIView):
    """The public ranking, most voted first. `status` is active (open + accepted), one status, or all."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        qs = TranslationRequest.objects.select_related('game').annotate(vote_total=Count('votes'))

        status_param = request.query_params.get('status', 'active')
        if status_param == 'active':
            qs = qs.filter(status__in=[TranslationRequest.STATUS_OPEN, TranslationRequest.STATUS_ACCEPTED])
        elif status_param in VALID_STATUSES:
            qs = qs.filter(status=status_param)
        elif status_param != 'all':
            return Response({'error': 'Noto‘g‘ri holat.'}, status=status.HTTP_400_BAD_REQUEST)

        search = request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(title__icontains=search)

        qs = qs.order_by('-vote_total', 'created_at', 'id')
        try:
            page = max(int(request.query_params.get('page', 1)), 1)
        except ValueError:
            page = 1
        offset = (page - 1) * REQUESTS_PAGE_SIZE
        count = qs.count()
        items = list(qs[offset:offset + REQUESTS_PAGE_SIZE])

        voted = voted_request_ids(request.user, [item.id for item in items])
        include_admin = bool(request.user.is_authenticated and request.user.is_admin)
        results = [
            serialize_request(
                item,
                votes=item.vote_total,
                has_voted=item.id in voted,
                # A position in a filtered list is not the game's place in the ranking.
                rank=None if search else offset + index + 1,
                include_admin=include_admin,
            )
            for index, item in enumerate(items)
        ]
        return Response({
            'count': count,
            'page': page,
            'pageSize': REQUESTS_PAGE_SIZE,
            'hasMore': offset + len(items) < count,
            'results': results,
        })


class SteamGameSearchView(views.APIView):
    """Steam search, with each result marked as already on the site, already requested, or new."""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if len(query) < MIN_SEARCH_LENGTH:
            return Response({'results': []})
        try:
            found = steam.search_games(query[:100])
        except steam.SteamUnavailable:
            return Response(
                {'error': 'Steam qidiruvi hozir javob bermayapti. Birozdan keyin qayta urinib ko‘ring.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        app_ids = [item['steamAppId'] for item in found]
        site_games = site_games_by_steam_id()
        requests_by_app = {
            item.steam_app_id: item
            for item in TranslationRequest.objects.filter(steam_app_id__in=app_ids)
            .select_related('game')
            .annotate(vote_total=Count('votes'))
        }
        voted = voted_request_ids(request.user, [item.id for item in requests_by_app.values()])

        results = []
        for item in found:
            existing = requests_by_app.get(item['steamAppId'])
            results.append({
                **item,
                'siteGame': game_summary(site_games.get(item['steamAppId'])),
                'request': serialize_request(
                    existing, votes=existing.vote_total, has_voted=existing.id in voted
                ) if existing else None,
            })
        return Response({'results': results})


class TranslationVoteView(views.APIView):
    """POST votes for a Steam game, creating its request on the first vote."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            app_id = int(request.data.get('steamAppId'))
            if app_id <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({'error': 'Steam ID noto‘g‘ri.'}, status=status.HTTP_400_BAD_REQUEST)

        site_game = site_games_by_steam_id().get(app_id)
        if site_game:
            return Response(
                {'error': 'Bu o‘yin saytda allaqachon bor.', 'game': game_summary(site_game)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item = TranslationRequest.objects.select_related('game').filter(steam_app_id=app_id).first()
        if item is None:
            try:
                details = steam.get_game(app_id)
            except steam.SteamUnavailable:
                return Response(
                    {'error': 'Steam hozir javob bermayapti. Birozdan keyin qayta urinib ko‘ring.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            if details is None:
                return Response({'error': 'Steam’da bunday o‘yin topilmadi.'}, status=status.HTTP_400_BAD_REQUEST)
            # Two first votes for the same game can arrive at the same moment.
            item, _ = TranslationRequest.objects.get_or_create(
                steam_app_id=app_id,
                defaults={'title': details['title'], 'image_url': details['imageUrl'], 'created_by': request.user},
            )
        elif item.status in (TranslationRequest.STATUS_REJECTED, TranslationRequest.STATUS_DONE):
            return Response({'error': 'Bu o‘yin uchun ovoz berish yopilgan.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                _, created = TranslationVote.objects.get_or_create(request=item, user=request.user)
        except IntegrityError:
            created = False

        return Response(
            serialize_request(item, votes=vote_count(item), has_voted=True),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TranslationUnvoteView(views.APIView):
    """DELETE takes the user's vote back. An open request left with no votes disappears."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        item = TranslationRequest.objects.select_related('game').filter(pk=pk).first()
        if item is None:
            return Response({'error': 'Taklif topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        TranslationVote.objects.filter(request=item, user=request.user).delete()
        votes = vote_count(item)
        if votes == 0 and item.status == TranslationRequest.STATUS_OPEN:
            item.delete()
            return Response({'deleted': True, 'request': None})
        return Response({'deleted': False, 'request': serialize_request(item, votes=votes, has_voted=False)})


class AdminTranslationRequestView(views.APIView):
    """PATCH status, linked game and note; DELETE removes the request with its votes."""

    permission_classes = [IsAdmin]

    def patch(self, request, pk):
        item = TranslationRequest.objects.select_related('game').filter(pk=pk).first()
        if item is None:
            return Response({'error': 'Taklif topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        update_fields = []
        if 'status' in request.data:
            if request.data['status'] not in VALID_STATUSES:
                return Response({'error': 'Noto‘g‘ri holat.'}, status=status.HTTP_400_BAD_REQUEST)
            item.status = request.data['status']
            update_fields.append('status')
        if 'gameSlug' in request.data:
            slug = request.data['gameSlug']
            if slug:
                game = Game.objects.filter(slug=slug).first()
                if game is None:
                    return Response({'error': 'Bunday o‘yin saytda yo‘q.'}, status=status.HTTP_400_BAD_REQUEST)
                item.game = game
            else:
                item.game = None
            update_fields.append('game')
        if 'adminNote' in request.data:
            item.admin_note = str(request.data['adminNote'] or '')
            update_fields.append('admin_note')

        if update_fields:
            item.save(update_fields=update_fields)
        return Response(serialize_request(item, votes=vote_count(item), has_voted=False, include_admin=True))

    def delete(self, request, pk):
        deleted, _ = TranslationRequest.objects.filter(pk=pk).delete()
        if not deleted:
            return Response({'error': 'Taklif topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
