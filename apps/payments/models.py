from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.games.models import Game


class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('prepared', 'Tayyorlandi'),
        ('paid', 'To‘langan'),
        ('cancelled', 'Bekor qilingan'),
    )

    order_id = models.CharField(max_length=120, primary_key=True)  # {userId}__{gameSlug}
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='orders')
    
    user_email = models.EmailField()
    game_title = models.CharField(max_length=255)
    game_slug = models.CharField(max_length=120)
    
    amount = models.IntegerField(default=15000)
    currency = models.CharField(max_length=10, default='UZS')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    payment_provider = models.CharField(max_length=50, default='click')
    click_trans_id = models.CharField(max_length=100, blank=True, default='')
    click_paydoc_id = models.CharField(max_length=100, blank=True, default='')
    paid_amount = models.IntegerField(default=0)
    error_note = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subgame_orders'
        ordering = ['-created_at']

    def __str__(self):
        return f"Order {self.order_id} ({self.status}) - {self.amount} {self.currency}"
