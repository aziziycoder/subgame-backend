from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='has_dubbing',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_status',
            field=models.CharField(
                choices=[('Tayyor', 'Tayyor'), ('Jarayonda', 'Jarayonda'), ('Tez kunda', 'Tez kunda'), ('Rejada', 'Rejada')],
                default='Tayyor',
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_language',
            field=models.CharField(default='O‘zbekcha (Lotin)', max_length=50),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_version',
            field=models.CharField(default='v1.0.0', max_length=50),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_last_updated',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_size',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_download_url',
            field=models.URLField(blank=True, default='', max_length=1000),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_price',
            field=models.CharField(default='Bepul', max_length=100),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_type',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        migrations.AddField(
            model_name='game',
            name='dubbing_format',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
