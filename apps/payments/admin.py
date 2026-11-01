from django.contrib import admin
from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user_email', 'game_title', 'amount', 'currency', 'status', 'click_trans_id', 'created_at')
    search_fields = ('order_id', 'user_email', 'game_title', 'click_trans_id')
    list_filter = ('status', 'created_at')
