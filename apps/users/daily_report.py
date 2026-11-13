"""Nightly Telegram report: what happened on one Tashkent day, plus totals up
to the end of that day. Counting rules (bound devices, Click vs manual money)
are shared with the admin dashboard so both always agree."""
from datetime import datetime, time, timedelta
from html import escape as _escape

import requests
from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.issues.models import GameSuggestion, Issue, TranslationRequest, TranslationVote
from apps.licenses.models import License
from apps.payments.models import Order

from .dashboard import BOUND_Q, CLICK_PAID_Q, _manual_payments, click_paid_orders
from .models import User

TELEGRAM_URL = 'https://api.telegram.org/bot{token}/sendMessage'
TELEGRAM_LIMIT = 4096
LIST_LIMIT = 10
TOP_REQUESTS = 5
PROVIDER_NAMES = {
    'click': 'Click', 'manual_paid': "Qo'lda (pullik)", 'payme': 'Payme',
    'free': 'Bepul', 'gift': "Sovg'a", 'other': 'Boshqa', 'none': "Ko'rsatilmagan", '': "Ko'rsatilmagan",
}


def escape(value):
    return _escape(str(value), quote=False)


class ReportError(Exception):
    """Report could not be sent; the message is safe to print (no token)."""


def day_bounds(day):
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), tz)
    return start, end


def yesterday():
    return timezone.localdate() - timedelta(days=1)


def collect(day):
    start, end = day_bounds(day)
    in_day = lambda field: Q(**{f'{field}__gte': start, f'{field}__lt': end})
    upto = lambda field: Q(**{f'{field}__lt': end})

    users = User.objects.aggregate(
        new=Count('pk', filter=in_day('created_at')),
        active=Count('pk', filter=in_day('last_login_at')),
        total=Count('pk', filter=upto('created_at')),
    )

    licenses_qs = License.objects.filter(in_day('created_at'))
    licenses = License.objects.aggregate(
        new=Count('pk', filter=in_day('created_at')),
        total=Count('pk', filter=upto('created_at')),
        active=Count('pk', filter=upto('created_at') & Q(status='active')),
    )
    licenses['byGame'] = list(
        licenses_qs.values('game_title').annotate(n=Count('pk')).order_by('-n', 'game_title')
    )
    licenses['byProvider'] = list(
        licenses_qs.values('payment_provider').annotate(n=Count('pk')).order_by('-n')
    )

    bound = License.objects.filter(BOUND_Q)
    bound_day = bound.filter(in_day('bound_at'))
    devices = {
        'boundLicenses': bound_day.count(),
        'devices': bound_day.values('hwid').distinct().count(),
        'totalDevices': bound.filter(upto('bound_at')).values('hwid').distinct().count(),
        'totalBound': bound.filter(upto('bound_at')).count(),
    }

    click = click_paid_orders()
    other_paid = Order.objects.filter(status='paid').exclude(CLICK_PAID_Q)
    click_day = click.filter(in_day('paid_on'))
    click_stats = click_day.aggregate(count=Count('pk'), amount=Sum('paid_amount'))
    click_stats['amount'] = click_stats['amount'] or 0
    click_stats['byGame'] = list(
        click_day.values('game_title').annotate(n=Count('pk'), amount=Sum('paid_amount')).order_by('-amount')
    )
    click_stats['total'] = click.filter(upto('paid_on')).aggregate(s=Sum('paid_amount'))['s'] or 0
    click_stats['totalCount'] = click.filter(upto('paid_on')).count()
    click_stats['pendingNew'] = Order.objects.filter(
        in_day('created_at'), status__in=['pending', 'prepared']
    ).count()

    manual = [m for m in _manual_payments(click, other_paid) if m['at'] < end]
    manual_day = [m for m in manual if m['at'] >= start]
    manual_stats = {
        'count': len(manual_day),
        'amount': sum(m['amount'] for m in manual_day),
        'items': sorted(manual_day, key=lambda m: m['at']),
        'total': sum(m['amount'] for m in manual),
        'totalCount': len(manual),
    }

    votes_day = TranslationVote.objects.filter(in_day('created_at'))
    translations = {
        'newRequests': list(
            TranslationRequest.objects.filter(in_day('created_at')).order_by('created_at').values_list('title', flat=True)
        ),
        'newVotes': votes_day.count(),
        'topToday': list(
            votes_day.values('request__title').annotate(n=Count('pk')).order_by('-n', 'request__title')[:TOP_REQUESTS]
        ),
        'topOverall': list(
            TranslationRequest.objects.filter(status=TranslationRequest.STATUS_OPEN, created_at__lt=end)
            .annotate(n=Count('votes', filter=Q(votes__created_at__lt=end)))
            .filter(n__gt=0).order_by('-n', 'title').values('title', 'n')[:TOP_REQUESTS]
        ),
        'totalRequests': TranslationRequest.objects.filter(upto('created_at')).count(),
        'totalVotes': TranslationVote.objects.filter(upto('created_at')).count(),
    }

    feedback = {
        'issues': Issue.objects.filter(in_day('created_at')).count(),
        'suggestions': GameSuggestion.objects.filter(in_day('created_at')).count(),
    }

    return {
        'day': day, 'users': users, 'licenses': licenses, 'devices': devices,
        'click': click_stats, 'manual': manual_stats, 'translations': translations,
        'feedback': feedback,
    }


def _n(value):
    return f'{value:,}'.replace(',', ' ')


def _som(value):
    return f"{_n(value)} so'm"


def _list(rows, line, limit=LIST_LIMIT):
    out = [line(row) for row in rows[:limit]]
    if len(rows) > limit:
        out.append(f'   … yana {len(rows) - limit} ta')
    return out


def render(stats):
    u, lic, dev = stats['users'], stats['licenses'], stats['devices']
    click, manual, tr, fb = stats['click'], stats['manual'], stats['translations'], stats['feedback']
    day = stats['day']

    lines = [f'📊 <b>SubGame — kunlik hisobot</b>', f'🗓 {day:%d.%m.%Y} (Toshkent vaqti)', '']

    lines.append('👤 <b>Foydalanuvchilar</b>')
    lines.append(f'• Yangi: <b>{_n(u["new"])}</b>')
    lines.append(f'• Kirganlar: {_n(u["active"])}')
    lines.append('')

    lines.append('🎮 <b>Litsenziyalar</b>')
    lines.append(f'• Yangi: <b>{_n(lic["new"])}</b>')
    lines += _list(lic['byGame'], lambda r: f'   ▫️ {escape(r["game_title"] or "—")}: {_n(r["n"])}')
    if lic['byProvider']:
        providers = ', '.join(
            f'{escape(PROVIDER_NAMES.get(r["payment_provider"], r["payment_provider"]))} {_n(r["n"])}'
            for r in lic['byProvider']
        )
        lines.append(f'• Turi bo\'yicha: {providers}')
    lines.append('')

    lines.append('💻 <b>Qurilmalar</b>')
    lines.append(f'• Bog\'langan litsenziyalar: <b>{_n(dev["boundLicenses"])}</b> ({_n(dev["devices"])} ta kompyuter)')
    lines.append('')

    day_total = click['amount'] + manual['amount']
    lines.append('💰 <b>To\'lovlar</b>')
    lines.append(f'• Click: <b>{_n(click["count"])}</b> ta — {_som(click["amount"])}')
    lines += _list(
        click['byGame'], lambda r: f'   ▫️ {escape(r["game_title"] or "—")}: {_n(r["n"])} ta — {_som(r["amount"] or 0)}'
    )
    lines.append(f'• Qo\'lda kiritilgan: <b>{_n(manual["count"])}</b> ta — {_som(manual["amount"])}')
    lines += _list(
        manual['items'],
        lambda m: f'   ▫️ {escape(m["title"] or "—")} — {escape(m["user"] or "—")}: {_som(m["amount"])}',
    )
    if click['pendingNew']:
        lines.append(f'• Yakunlanmagan Click buyurtmalar: {_n(click["pendingNew"])}')
    lines.append(f'• <b>Kunlik tushum: {_som(day_total)}</b>')
    lines.append('')

    lines.append('🗳 <b>Tarjima so\'rovlari</b>')
    lines.append(f'• Yangi ovozlar: <b>{_n(tr["newVotes"])}</b>')
    if tr['newRequests']:
        lines.append(f'• Yangi o\'yinlar ({_n(len(tr["newRequests"]))}):')
        lines += _list(tr['newRequests'], lambda t: f'   ▫️ {escape(t)}')
    if tr['topToday']:
        lines.append('• Bugun eng ko\'p ovoz olganlar:')
        lines += [f'   {i}. {escape(r["request__title"])} — {_n(r["n"])}' for i, r in enumerate(tr['topToday'], 1)]
    if tr['topOverall']:
        lines.append('• Umumiy reyting (ochiq so\'rovlar):')
        lines += [f'   {i}. {escape(r["title"])} — {_n(r["n"])}' for i, r in enumerate(tr['topOverall'], 1)]
    lines.append('')

    if fb['issues'] or fb['suggestions']:
        lines.append('📝 <b>Murojaatlar</b>')
        lines.append(f'• Xatolik xabarlari: {_n(fb["issues"])}, o\'yin takliflari: {_n(fb["suggestions"])}')
        lines.append('')

    lines.append('📈 <b>Jami (kun oxiriga)</b>')
    lines.append(f'• Foydalanuvchilar: {_n(u["total"])}')
    lines.append(f'• Litsenziyalar: {_n(lic["total"])} (faol {_n(lic["active"])})')
    lines.append(f'• Kompyuterlar: {_n(dev["totalDevices"])} ({_n(dev["totalBound"])} ta bog\'langan litsenziya)')
    lines.append(f'• Click: {_n(click["totalCount"])} ta — {_som(click["total"])}')
    lines.append(f'• Qo\'lda: {_n(manual["totalCount"])} ta — {_som(manual["total"])}')
    lines.append(f'• <b>Umumiy tushum: {_som(click["total"] + manual["total"])}</b>')
    lines.append(f'• Tarjima so\'rovlari: {_n(tr["totalRequests"])} ta, {_n(tr["totalVotes"])} ovoz')

    text = '\n'.join(lines)
    if len(text) > TELEGRAM_LIMIT:
        text = text[:TELEGRAM_LIMIT - 20].rsplit('\n', 1)[0] + '\n…'
    return text


def send(text):
    token = (getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or '').strip()
    chat_id = (getattr(settings, 'TELEGRAM_REPORT_CHAT_ID', '') or '').strip()
    missing = [name for name, value in (('TELEGRAM_BOT_TOKEN', token), ('TELEGRAM_REPORT_CHAT_ID', chat_id)) if not value]
    if missing:
        raise ReportError(f"{', '.join(missing)} o'rnatilmagan (.env faylini tekshiring)")
    try:
        response = requests.post(
            TELEGRAM_URL.format(token=token),
            json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML', 'disable_web_page_preview': True},
            timeout=20,
        )
    except requests.RequestException as exc:
        # The exception text can contain the URL, and the URL contains the token.
        raise ReportError(f'Telegramga ulanib bo\'lmadi: {type(exc).__name__}') from None
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if response.status_code != 200 or not payload.get('ok'):
        description = str(payload.get('description') or response.text[:200]).replace(token, '***')
        raise ReportError(f'Telegram rad etdi (HTTP {response.status_code}): {description}')
    return payload
