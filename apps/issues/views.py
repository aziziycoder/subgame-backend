from rest_framework import generics, permissions
from .models import Issue, GameSuggestion
from .serializers import IssueSerializer, GameSuggestionSerializer


class IssueCreateView(generics.CreateAPIView):
    serializer_class = IssueSerializer
    permission_classes = [permissions.AllowAny]


class SuggestionCreateView(generics.CreateAPIView):
    serializer_class = GameSuggestionSerializer
    permission_classes = [permissions.AllowAny]
