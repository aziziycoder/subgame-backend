"""Aggregated numbers for the admin dashboard. Everything is counted in the
database; no list of users, licenses or orders is sent to the browser."""
from datetime import datetime, time, timedelta

from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import views
from rest_framework.response import Response

from apps.games.models import Game
from apps.licenses.models import License
from apps.payments.models import Order

from .models import User
from .permissions import IsAdmin

SERIES_DAYS = 30
TOP_GAMES = 10
RECENT_ITEMS = 12

BOUND_Q = Q(hwid__isnull=False) & ~Q(hwid='')
ADMIN_Q = Q(role='admin') | Q(is_superuser=True)
CLICK_PAID_Q = Q(status='paid', payment_provider='click') & ~Q(click_trans_id='')


def _local_midnight(now):
    local = timezone.localtime(now)
    return timezone.make_aware(datetime.combine(local.date(), time.min), timezone.get_current_timezone())


def _windowed(queryset, field, today, week, month):
    return queryset.aggregate(
        total=Count('pk'),
        today=Count('pk', filter=Q(**{f'{field}__gte': today})),
        last7=Count('pk', filter=Q(**{f'{field}__gte': week})),
        last30=Count('pk', filter=Q(**{f'{field}__gte': month})),
    )


def _daily(queryset, field, since, value=None):
    rows = (
        queryset.filter(**{f'{field}__gte': since})
        .annotate(day=TruncDate(field, tzinfo=timezone.get_current_timezone()))
        .values('day')
        .annotate(n=value or Count('pk'))
    )
    return {row['day']: row['n'] or 0 for row in rows}


def _iso(value):
    return value.isoformat() if value else None


class AdminDashboardStatsView(views.APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        now = timezone.now()
        today = _local_midnight(now)
        week = today - timedelta(days=6)
        month = today - timedelta(days=SERIES_DAYS - 1)

        # Users
        users = _windowed(User.objects.all(), 'created_at', today, week, month)
        users.update(User.objects.aggregate(
            admins=Count('pk', filter=ADMIN_Q),
            active7=Count('pk', filter=Q(last_login_at__gte=week)),
            active30=Count('pk', filter=Q(last_login_at__gte=month)),
        ))
        # Kept apart: joining licenses here would multiply the counts above.
        users['withLicense'] = License.objects.values('user_id').distinct().count()

        # Licenses
        licenses = _windowed(License.objects.all(), 'created_at', today, week, month)
        licenses.update(License.objects.aggregate(
            active=Count('pk', filter=Q(status='active')),
            revoked=Count('pk', filter=Q(status='revoked')),
            bound=Count('pk', filter=BOUND_Q),
            activeUnbound=Count('pk', filter=Q(status='active') & ~BOUND_Q),
        ))
        by_provider = (
            License.objects.values('payment_provider').annotate(n=Count('pk')).order_by('-n')
        )
        licenses['byProvider'] = [
            {'provider': row['payment_provider'] or 'none', 'count': row['n']} for row in by_provider
        ]

        # Devices (distinct HWIDs; one PC can hold several licenses)
        bound = License.objects.filter(BOUND_Q)
        devices = {
            'uniqueHwids': bound.values('hwid').distinct().count(),
            'boundLicenses': bound.count(),
            'boundLast7': bound.filter(bound_at__gte=week).count(),
            'boundLast30': bound.filter(bound_at__gte=month).count(),
        }

        # Orders and Click revenue. Only an order Click confirmed (it carries
        # Click's transaction id) counts as Click money; manual and other paid
        # orders are reported apart. Orders are dated by creation: imported
        # orders have no payment time, and a checkout is paid within minutes.
        paid = Order.objects.filter(CLICK_PAID_Q)
        other_paid = Order.objects.filter(status='paid').exclude(CLICK_PAID_Q)
        orders = Order.objects.aggregate(
            total=Count('pk'),
            paid=Count('pk', filter=CLICK_PAID_Q),
            otherPaid=Count('pk', filter=Q(status='paid') & ~CLICK_PAID_Q),
            pending=Count('pk', filter=Q(status__in=['pending', 'prepared'])),
            cancelled=Count('pk', filter=Q(status='cancelled')),
        )
        revenue = paid.aggregate(
            total=Sum('paid_amount'),
            today=Sum('paid_amount', filter=Q(created_at__gte=today)),
            last7=Sum('paid_amount', filter=Q(created_at__gte=week)),
            last30=Sum('paid_amount', filter=Q(created_at__gte=month)),
        )
        orders['revenue'] = {k: v or 0 for k, v in revenue.items()}
        orders['otherRevenue'] = other_paid.aggregate(total=Sum('paid_amount'))['total'] or 0
        orders['currency'] = 'UZS'

        # Games, ranked by licenses
        game_rows = (
            License.objects.values('game_id')
            .annotate(
                total=Count('pk'),
                active=Count('pk', filter=Q(status='active')),
                bound=Count('pk', filter=BOUND_Q),
                last30=Count('pk', filter=Q(created_at__gte=month)),
            )
            .order_by('-total', 'game_id')
        )
        revenue_by_game = {
            row['game_id']: row
            for row in paid.values('game_id').annotate(revenue=Sum('paid_amount'), paidOrders=Count('pk'))
        }
        game_info = {
            g['id']: g for g in Game.objects.values('id', 'title', 'slug', 'cover', 'card_image')
        }
        games_out = []
        for row in game_rows:
            info = game_info.get(row['game_id'], {})
            money = revenue_by_game.get(row['game_id'], {})
            games_out.append({
                'gameId': row['game_id'],
                'title': info.get('title') or row['game_id'],
                'slug': info.get('slug') or row['game_id'],
                'image': info.get('card_image') or info.get('cover') or '',
                'licenses': row['total'],
                'active': row['active'],
                'bound': row['bound'],
                'last30': row['last30'],
                'paidOrders': money.get('paidOrders', 0),
                'revenue': money.get('revenue') or 0,
            })
        catalog = Game.objects.aggregate(
            total=Count('pk'),
            ready=Count('pk', filter=Q(subtitle_status='Tayyor')),
        )

        # Daily series for the last 30 days (Tashkent days)
        signups = _daily(User.objects.all(), 'created_at', month)
        claims = _daily(License.objects.all(), 'created_at', month)
        paid_daily = _daily(paid, 'created_at', month, Sum('paid_amount'))
        series = []
        start = timezone.localtime(month).date()
        for i in range(SERIES_DAYS):
            day = start + timedelta(days=i)
            series.append({
                'date': day.isoformat(),
                'users': signups.get(day, 0),
                'licenses': claims.get(day, 0),
                'revenue': paid_daily.get(day, 0),
            })

        # Recent activity feed
        activity = []
        for u in User.objects.order_by('-created_at')[:RECENT_ITEMS]:
            activity.append({
                'type': 'signup', 'at': _iso(u.created_at),
                'user': u.display_name or u.email, 'email': u.email, 'detail': '',
            })
        for lic in License.objects.order_by('-created_at')[:RECENT_ITEMS]:
            activity.append({
                'type': 'license', 'at': _iso(lic.created_at),
                'user': lic.user_name or lic.user_email, 'email': lic.user_email,
                'detail': lic.game_title, 'provider': lic.payment_provider or 'none',
            })
        for lic in License.objects.filter(BOUND_Q, bound_at__isnull=False).order_by('-bound_at')[:RECENT_ITEMS]:
            activity.append({
                'type': 'bind', 'at': _iso(lic.bound_at),
                'user': lic.user_name or lic.user_email, 'email': lic.user_email,
                'detail': lic.game_title, 'device': lic.bound_device_name or '',
            })
        for order in paid.order_by('-created_at')[:RECENT_ITEMS]:
            activity.append({
                'type': 'payment', 'at': _iso(order.created_at),
                'user': order.user_email, 'email': order.user_email,
                'detail': order.game_title, 'amount': order.paid_amount,
            })
        activity.sort(key=lambda item: item['at'] or '', reverse=True)

        last_payment = paid.aggregate(at=Max('created_at'))['at']

        return Response({
            'generatedAt': _iso(now),
            'timezone': str(timezone.get_current_timezone()),
            'users': users,
            'licenses': licenses,
            'devices': devices,
            'orders': {**orders, 'lastPaidAt': _iso(last_payment)},
            'catalog': catalog,
            'games': games_out,
            'topGames': games_out[:TOP_GAMES],
            'series': series,
            'activity': activity[:RECENT_ITEMS * 2],
        })
