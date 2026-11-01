from django.db import models
from django.utils import timezone
from apps.users.models import User
from apps.games.models import Game


class Issue(models.Model):
    game = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues')
    game_title = models.CharField(max_length=255)
    issue_type = models.CharField(max_length=100)
    game_version = models.CharField(max_length=50, blank=True, default='')
    description = models.TextField()
    user_contact = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'subgame_issues'
        ordering = ['-created_at']

    def __str__(self):
        return f"Issue: {self.game_title} - {self.issue_type}"


class GameSuggestion(models.Model):
    game_title = models.CharField(max_length=255)
    platform = models.CharField(max_length=100)
    steam_url = models.URLField(max_length=500, blank=True, default='')
    user_email = models.EmailField(blank=True, default='')
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'subgame_suggestions'
        ordering = ['-created_at']

    def __str__(self):
        return f"Suggestion: {self.game_title} ({self.platform})"
