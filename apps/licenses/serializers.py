from rest_framework import serializers
from .models import License, DeviceSession


class LicenseSerializer(serializers.ModelSerializer):
    userId = serializers.CharField(source='user_id', read_only=True)
    userEmail = serializers.CharField(source='user_email', read_only=True)
    userName = serializers.CharField(source='user_name', read_only=True)
    userPhoto = serializers.CharField(source='user_photo', read_only=True)
    gameId = serializers.CharField(source='game_id', read_only=True)
    gameTitle = serializers.CharField(source='game_title', read_only=True)
    gameSlug = serializers.CharField(source='game_slug', read_only=True)
    boundAt = serializers.DateTimeField(source='bound_at', read_only=True)
    boundDeviceName = serializers.CharField(source='bound_device_name', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    paymentProvider = serializers.CharField(source='payment_provider', read_only=True)
    paymentRef = serializers.CharField(source='payment_ref', read_only=True)
    paidAmount = serializers.IntegerField(source='paid_amount', read_only=True)
    revokedReason = serializers.CharField(source='revoked_reason', read_only=True)
    adminNote = serializers.CharField(source='admin_note', read_only=True)
    grantedBy = serializers.CharField(source='granted_by', read_only=True)

    class Meta:
        model = License
        fields = [
            'id', 'userId', 'userEmail', 'userName', 'userPhoto',
            'gameId', 'gameTitle', 'gameSlug', 'status', 'hwid',
            'boundAt', 'boundDeviceName', 'payment_provider',
            'paid_amount', 'created_at', 'createdAt', 'updatedAt',
            'paymentProvider', 'paymentRef', 'paidAmount', 'revokedReason',
            'adminNote', 'grantedBy'
        ]


class DeviceSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceSession
        fields = '__all__'
