"""Undo the old Firestore import, which saved every order as paid.

An order counts as wrongly paid when Click never confirmed it (no Click
transaction id) and the Firestore export still had it unpaid. Without
--apply the command only reports; nothing is written.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Sum

from apps.licenses.models import License
from apps.payments.models import Order

UNPAID = ('pending', 'prepared', 'cancelled')


class Command(BaseCommand):
    help = "Firestore importida noto'g'ri 'paid' bo'lib qolgan buyurtmalarni asl holatiga qaytaradi."

    def add_arguments(self, parser):
        parser.add_argument('--export', default=str(Path(settings.BASE_DIR) / 'data' / 'firestore_full_export.json'))
        parser.add_argument('--apply', action='store_true', help="O'zgarishni bazaga yozish (aks holda faqat hisobot).")
        parser.add_argument(
            '--include-prepared', action='store_true',
            help="Click'da boshlangan, lekin Firestore'da yakunlanmagan (prepared) buyurtmalarni ham qaytarish.",
        )

    def handle(self, *args, **options):
        path = Path(options['export'])
        if not path.exists():
            raise CommandError(f'Eksport fayli topilmadi: {path}')
        exported = {
            o.get('orderId') or o.get('id'): o.get('status')
            for o in json.loads(path.read_text(encoding='utf-8')).get('orders', [])
        }

        paid = Order.objects.filter(status='paid', payment_provider='click')
        unconfirmed = [o for o in paid.filter(click_trans_id='') if exported.get(o.order_id) in UNPAID]
        prepared = [
            o for o in paid.exclude(click_trans_id='')
            if exported.get(o.order_id) == 'prepared'
        ]

        self._report("Click tasdiqlamagan, Firestore'da to'lanmagan", unconfirmed)
        self._report("Click'da boshlangan, Firestore'da yakunlanmagan (prepared)", prepared)

        targets = unconfirmed + (prepared if options['include_prepared'] else [])
        pairs = {(o.user_id, o.game_id) for o in targets}
        licensed = set(License.objects.filter(
            payment_provider='click',
            user_id__in={u for u, _ in pairs},
            game_id__in={g for _, g in pairs},
        ).values_list('user_id', 'game_id')) & pairs
        if licensed:
            self.stdout.write(self.style.WARNING(
                f"Diqqat: {len(licensed)} tasida foydalanuvchida shu o'yin uchun Click litsenziyasi bor "
                "(litsenziyalarga tegilmaydi):"
            ))
            for user_id, game_id in sorted(licensed):
                self.stdout.write(f'  {user_id} / {game_id}')

        before = Order.objects.filter(status='paid', payment_provider='click').exclude(
            click_trans_id='').aggregate(s=Sum('paid_amount'))['s'] or 0
        self.stdout.write(f"\nTasdiqlangan Click daromadi: {before} so'm")

        if not options['apply']:
            self.stdout.write(self.style.NOTICE(
                f"\nSinov rejimi: {len(targets)} ta buyurtma qaytariladi. Yozish uchun --apply qo'shing."
            ))
            return

        with transaction.atomic():
            for order in targets:
                order.status = exported[order.order_id]
                order.paid_amount = 0
                order.save(update_fields=['status', 'paid_amount', 'updated_at'])
        self.stdout.write(self.style.SUCCESS(f"{len(targets)} ta buyurtma asl holatiga qaytarildi."))

    def _report(self, title, orders):
        total = sum(o.paid_amount for o in orders)
        self.stdout.write(f"{title}: {len(orders)} ta, {total} so'm")
