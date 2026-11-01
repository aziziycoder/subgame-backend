from django.contrib import admin
from .models import Issue, GameSuggestion


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('game_title', 'issue_type', 'user_contact', 'created_at')
    search_fields = ('game_title', 'description', 'user_contact')
    list_filter = ('issue_type', 'created_at')


@admin.register(GameSuggestion)
class GameSuggestionAdmin(admin.ModelAdmin):
    list_display = ('game_title', 'platform', 'user_email', 'created_at')
    search_fields = ('game_title', 'user_email')
