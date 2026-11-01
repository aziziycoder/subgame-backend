from django.contrib import admin
from .models import License, DeviceSession


@admin.register(License)
class LicenseAdmin(admin.ModelAdmin):
    list_display = ('user_email', 'game_title', 'status', 'hwid', 'bound_device_name', 'paid_amount', 'created_at')
    search_fields = ('user_email', 'game_title', 'hwid', 'id')
    list_filter = ('status', 'payment_provider', 'created_at')
    actions = ['reset_hwid', 'activate_licenses', 'revoke_licenses']

    @admin.action(description="Tanlangan litsenziyalar HWID bog'lanishini tozalash")
    def reset_hwid(self, request, queryset):
        queryset.update(hwid=None, bound_at=None, bound_device_name=None)

    @admin.action(description="Litsenziyalarni faollashtirish (Active)")
    def activate_licenses(self, request, queryset):
        queryset.update(status='active')

    @admin.action(description="Litsenziyalarni to'xtatish (Revoke)")
    def revoke_licenses(self, request, queryset):
        queryset.update(status='revoked')


@admin.register(DeviceSession)
class DeviceSessionAdmin(admin.ModelAdmin):
    list_display = ('session_id', 'status', 'user', 'device_name', 'created_at', 'expires_at')
    list_filter = ('status', 'created_at')
