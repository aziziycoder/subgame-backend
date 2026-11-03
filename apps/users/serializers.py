from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    uid = serializers.CharField(source='id', read_only=True)
    displayName = serializers.CharField(source='display_name', read_only=True)
    photoURL = serializers.CharField(source='photo_url', read_only=True)
    isAdmin = serializers.BooleanField(source='is_admin', read_only=True)
    lastLoginAt = serializers.DateTimeField(source='last_login_at', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'uid', 'email', 'display_name', 'displayName',
            'photo_url', 'photoURL', 'role', 'isAdmin',
            'created_at', 'createdAt', 'last_login_at', 'lastLoginAt'
        ]
        read_only_fields = ['id', 'email', 'role', 'isAdmin', 'created_at', 'last_login_at']


class GoogleAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=False)
    access_token = serializers.CharField(required=False)

    def validate(self, attrs):
        if not attrs.get('id_token') and not attrs.get('access_token'):
            raise serializers.ValidationError('id_token yoki access_token kiritilishi shart.')
        return attrs

