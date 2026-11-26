from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_order_paid_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='edition',
            field=models.CharField(default='subtitle', max_length=20),
        ),
    ]
