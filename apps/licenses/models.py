import uuid
from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.games.models import Game


class License(models.Model):
    STATUS_CHOICES = (
        ('active', 'Faol'),
        ('revoked', 'To‘xtatilgan'),
    )

    id = models.CharField(max_length=255, primary_key=True)  # {user_id}_{game_id}
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='licenses')
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='licenses')
    
    # Snapshot metadata for high-speed queries without joins if needed
    user_email = models.EmailField(db_index=True)
    user_name = models.CharField(max_length=255, blank=True, default='')
    user_photo = models.TextField(blank=True, default='')
    game_title = models.CharField(max_length=255)
    game_slug = models.CharField(max_length=120, db_index=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    # 1-PC DRM Binding
    hwid = models.CharField(max_length=128, null=True, blank=True, db_index=True)
    bound_at = models.DateTimeField(null=True, blank=True)
    bound_device_name = models.CharField(max_length=100, null=True, blank=True)
    
    # Payment attribution
    payment_provider = models.CharField(max_length=50, blank=True, default='none')
    payment_ref = models.CharField(max_length=100, blank=True, default='')
    paid_amount = models.IntegerField(default=0)
    revoked_reason = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subgame_licenses'
        ordering = ['-created_at']
        unique_together = ('user', 'game')

    def __str__(self):
        return f"{self.user.email} - {self.game.title} ({self.status})"


class DeviceSession(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Kutilmoqda'),
        ('approved', 'Tasdiqlangan'),
        ('expired', 'Muddati o‘tgan'),
    )

    session_id = models.CharField(max_length=32, primary_key=True)  # 6-digit code or uuid
    device_id = models.CharField(max_length=128)
    device_name = models.CharField(max_length=128, blank=True, default='')
    hwid = models.CharField(max_length=128, blank=True, default='')
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='device_sessions')
    
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'subgame_device_sessions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.session_id} ({self.status})"
