from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    isAdmin = serializers.BooleanField(source='is_admin', read_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'display_name', 'photo_url', 'role', 'isAdmin', 'created_at', 'last_login_at']
        read_only_fields = ['id', 'email', 'role', 'isAdmin', 'created_at', 'last_login_at']


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=True)
