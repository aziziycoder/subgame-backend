from django.urls import path
from .views import (
    AdminTranslationRequestView,
    IssueCreateView,
    SteamGameSearchView,
    SuggestionCreateView,
    TranslationRequestListView,
    TranslationUnvoteView,
    TranslationVoteView,
)

urlpatterns = [
    path('report/', IssueCreateView.as_view(), name='issue-create'),
    path('suggest/', SuggestionCreateView.as_view(), name='suggestion-create'),
    path('requests/', TranslationRequestListView.as_view(), name='translation-request-list'),
    path('requests/search/', SteamGameSearchView.as_view(), name='translation-request-search'),
    path('requests/vote/', TranslationVoteView.as_view(), name='translation-request-vote'),
    path('requests/<int:pk>/vote/', TranslationUnvoteView.as_view(), name='translation-request-unvote'),
    path('admin/requests/<int:pk>/', AdminTranslationRequestView.as_view(), name='translation-request-admin'),
]
