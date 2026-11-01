from django.db import models
from django.utils import timezone


class Game(models.Model):
    STATUS_CHOICES = (
        ('Tayyor', 'Tayyor'),
        ('Jarayonda', 'Jarayonda'),
        ('Tez kunda', 'Tez kunda'),
        ('Rejada', 'Rejada'),
    )

    id = models.CharField(max_length=100, primary_key=True)  # e.g. 'stray', 'outward-2'
    slug = models.SlugField(max_length=120, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    
    cover = models.URLField(max_length=1000)
    card_image = models.URLField(max_length=1000, blank=True, default='')
    hero_image = models.URLField(max_length=1000, blank=True, default='')
    
    gameplay_video_url = models.URLField(max_length=1000, blank=True, default='')
    torrent_url = models.URLField(max_length=1000, blank=True, default='')
    screenshots = models.JSONField(default=list, blank=True)
    
    short_description = models.TextField(blank=True, default='')
    full_description = models.TextField(blank=True, default='')
    
    release_year = models.IntegerField(default=2024)
    developer = models.CharField(max_length=255, blank=True, default='')
    publisher = models.CharField(max_length=255, blank=True, default='')
    genres = models.JSONField(default=list, blank=True)
    platforms = models.JSONField(default=list, blank=True)
    official_store_links = models.JSONField(default=list, blank=True)
    
    price = models.CharField(max_length=100, default='Tekin')
    price_note = models.TextField(blank=True, default='')
    
    # Subtitle data
    subtitle_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Tayyor')
    subtitle_language = models.CharField(max_length=50, default='O‘zbekcha (Lotin)')
    subtitle_version = models.CharField(max_length=50, default='v1.0.0')
    subtitle_last_updated = models.CharField(max_length=50, default='2026-10-28')
    subtitle_compatibility = models.CharField(max_length=255, blank=True, default='')
    subtitle_format = models.CharField(max_length=255, blank=True, default='')
    subtitle_size = models.CharField(max_length=50, blank=True, default='')
    subtitle_download_url = models.URLField(max_length=1000, blank=True, default='')
    subtitle_price = models.CharField(max_length=100, default='Bepul')
    subtitle_translation_type = models.CharField(max_length=255, blank=True, default='')
    
    # Guides & Specs
    installation_guide = models.JSONField(default=list, blank=True)
    known_issues = models.JSONField(default=list, blank=True)
    minimum_requirements = models.JSONField(default=dict, blank=True)
    recommended_requirements = models.JSONField(default=dict, blank=True)
    
    is_featured = models.BooleanField(default=False)
    tags = models.JSONField(default=list, blank=True)
    
    # Launcher specific parameters
    default_exe_name = models.CharField(max_length=255, blank=True, default='')
    target_file_name = models.CharField(max_length=255, blank=True, default='')
    target_relative_dir = models.CharField(max_length=255, blank=True, default='')
    key_prefix = models.CharField(max_length=50, blank=True, default='')
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subgame_games'
        ordering = ['-release_year', 'title']

    def __str__(self):
        return f"{self.title} ({self.release_year})"

    @property
    def is_paid(self):
        val = (self.subtitle_price or self.price or '').lower()
        if 'bepul' in val or 'tekin' in val or 'free' in val or 'tez kunda' in val:
            return False
        return True


class Slider(models.Model):
    id = models.CharField(max_length=100, primary_key=True)
    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=255)
    badge = models.CharField(max_length=100, blank=True, default='')
    headline_prefix = models.CharField(max_length=255, blank=True, default='')
    headline_highlight = models.CharField(max_length=255, blank=True, default='')
    headline_suffix = models.CharField(max_length=255, blank=True, default='')
    description = models.TextField(blank=True, default='')
    
    bg_image = models.URLField(max_length=1000)
    card_image = models.URLField(max_length=1000, blank=True, default='')
    card_tag = models.CharField(max_length=100, blank=True, default='')
    highlight_tag = models.CharField(max_length=100, blank=True, default='')
    version = models.CharField(max_length=50, default='v1.0.0')
    card_description = models.TextField(blank=True, default='')
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'subgame_sliders'
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title
