from rest_framework import serializers
from .models import Order


class OrderSerializer(serializers.ModelSerializer):
    orderId = serializers.CharField(source='order_id', read_only=True)
    userId = serializers.CharField(source='user_id', read_only=True)
    userEmail = serializers.CharField(source='user_email', read_only=True)
    gameId = serializers.CharField(source='game_id', read_only=True)
    gameTitle = serializers.CharField(source='game_title', read_only=True)
    gameSlug = serializers.CharField(source='game_slug', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Order
        fields = [
            'orderId', 'userId', 'userEmail', 'gameId', 'gameTitle',
            'gameSlug', 'amount', 'currency', 'status', 'createdAt'
        ]
