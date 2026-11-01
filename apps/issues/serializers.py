from rest_framework import serializers
from .models import Issue, GameSuggestion


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Issue
        fields = '__all__'


class GameSuggestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameSuggestion
        fields = '__all__'
