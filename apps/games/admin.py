from django.contrib import admin
from .models import Game, Slider, SubtitleVariant


class SubtitleVariantInline(admin.TabularInline):
    model = SubtitleVariant
    extra = 0
    fields = ('key', 'label', 'subtitle_version', 'subtitle_size', 'target_file_name', 'target_relative_dir', 'sort_order')


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('title', 'id', 'subtitle_status', 'subtitle_version', 'price', 'release_year', 'is_featured')
    search_fields = ('title', 'id', 'slug', 'developer')
    list_filter = ('subtitle_status', 'is_featured', 'release_year')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [SubtitleVariantInline]


@admin.register(Slider)
class SliderAdmin(admin.ModelAdmin):
    list_display = ('title', 'badge', 'order', 'is_active', 'created_at')
    list_editable = ('order', 'is_active')
    search_fields = ('title', 'slug')
