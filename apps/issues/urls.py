from django.urls import path
from .views import IssueCreateView, SuggestionCreateView

urlpatterns = [
    path('report/', IssueCreateView.as_view(), name='issue-create'),
    path('suggest/', SuggestionCreateView.as_view(), name='suggestion-create'),
]
