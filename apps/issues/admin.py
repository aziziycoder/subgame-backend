from django.contrib import admin
from .models import Issue, GameSuggestion, TranslationRequest, TranslationVote


@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    list_display = ('game_title', 'issue_type', 'user_contact', 'created_at')
    search_fields = ('game_title', 'description', 'user_contact')
    list_filter = ('issue_type', 'created_at')


@admin.register(GameSuggestion)
class GameSuggestionAdmin(admin.ModelAdmin):
    list_display = ('game_title', 'platform', 'user_email', 'created_at')
    search_fields = ('game_title', 'user_email')


class TranslationVoteInline(admin.TabularInline):
    model = TranslationVote
    extra = 0
    raw_id_fields = ('user',)


@admin.register(TranslationRequest)
class TranslationRequestAdmin(admin.ModelAdmin):
    list_display = ('title', 'steam_app_id', 'status', 'game', 'created_at')
    search_fields = ('title', 'steam_app_id')
    list_filter = ('status',)
    raw_id_fields = ('created_by', 'game')
    inlines = [TranslationVoteInline]
