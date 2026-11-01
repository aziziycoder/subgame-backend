from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('licenses', '0002_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='license',
            name='user_photo',
            field=models.TextField(blank=True, default=''),
        ),
    ]
