from django.contrib import admin
from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'display_name', 'role', 'is_staff', 'created_at', 'last_login_at')
    search_fields = ('email', 'display_name', 'id')
    list_filter = ('role', 'is_staff', 'is_active')
    ordering = ('-created_at',)
