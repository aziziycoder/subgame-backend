from datetime import date

from django.core.management.base import BaseCommand, CommandError

from apps.users.daily_report import ReportError, collect, render, send, yesterday


class Command(BaseCommand):
    help = "O'tgan kun (Toshkent vaqti) statistikasini Telegram bot orqali yuboradi"

    def add_arguments(self, parser):
        parser.add_argument('--date', help='Hisobot kuni, YYYY-MM-DD (standart: kecha)')
        parser.add_argument('--dry-run', action='store_true', help="Yubormasdan matnni chiqaradi")

    def handle(self, *args, **options):
        if options['date']:
            try:
                day = date.fromisoformat(options['date'])
            except ValueError:
                raise CommandError("--date YYYY-MM-DD ko'rinishida bo'lishi kerak")
        else:
            day = yesterday()

        text = render(collect(day))
        if options['dry_run']:
            self.stdout.write(text)
            return
        try:
            send(text)
        except ReportError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f'{day.isoformat()} hisoboti yuborildi'))
