from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0002_dubbing_fields'),
        ('licenses', '0004_firebase_cutover'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='license',
            name='edition',
            field=models.CharField(default='subtitle', max_length=20),
        ),
        migrations.AlterUniqueTogether(
            name='license',
            unique_together={('user', 'game', 'edition')},
        ),
    ]
