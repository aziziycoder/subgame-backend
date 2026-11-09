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


class TranslationRequest(models.Model):
    """A Steam game people want translated. One row per game; popularity comes from its votes."""

    STATUS_OPEN = 'open'
    STATUS_ACCEPTED = 'accepted'
    STATUS_REJECTED = 'rejected'
    STATUS_DONE = 'done'
    STATUS_CHOICES = (
        (STATUS_OPEN, 'Ovoz yig‘ilmoqda'),
        (STATUS_ACCEPTED, 'Tarjimaga olindi'),
        (STATUS_REJECTED, 'Rad etildi'),
        (STATUS_DONE, 'Tarjima qilindi'),
    )

    steam_app_id = models.PositiveIntegerField(unique=True)
    title = models.CharField(max_length=255)
    image_url = models.URLField(max_length=1000, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    game = models.ForeignKey(Game, on_delete=models.SET_NULL, null=True, blank=True, related_name='translation_requests')
    admin_note = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='translation_requests')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'subgame_translation_requests'
        ordering = ['-created_at']

    def __str__(self):
        return f"Translation request: {self.title} ({self.steam_app_id})"


class TranslationVote(models.Model):
    request = models.ForeignKey(TranslationRequest, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='translation_votes')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'subgame_translation_votes'
        constraints = [
            models.UniqueConstraint(fields=['request', 'user'], name='one_vote_per_user_per_request'),
        ]

    def __str__(self):
        return f"Vote: {self.user_id} -> {self.request_id}"
