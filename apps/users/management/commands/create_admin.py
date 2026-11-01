from django.core.management.base import BaseCommand
from apps.users.models import User


class Command(BaseCommand):
    help = 'Admin foydalanuvchini yaratadi'

    def handle(self, *args, **options):
        admin_email = 'azizbekgulomovweb@gmail.com'
        user, created = User.objects.get_or_create(
            email=admin_email,
            defaults={
                'id': 'admin_root',
                'display_name': 'Azizbek G‘ulomov (Bosh Admin)',
                'role': 'admin',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            user.set_password('Admin2026!SubGame')
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Bosh admin yaratildi: {admin_email} / Admin2026!SubGame"))
        else:
            user.role = 'admin'
            user.is_staff = True
            user.is_superuser = True
            user.set_password('Admin2026!SubGame')
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Bosh admin yangilandi: {admin_email} / Admin2026!SubGame"))
