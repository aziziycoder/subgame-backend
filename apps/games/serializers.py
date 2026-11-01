from rest_framework import serializers
from .models import Game, Slider


class GameSerializer(serializers.ModelSerializer):
    isPaid = serializers.BooleanField(source='is_paid', read_only=True)
    cardImage = serializers.CharField(source='card_image', required=False)
    heroImage = serializers.CharField(source='hero_image', required=False)
    gameplayVideoUrl = serializers.CharField(source='gameplay_video_url', required=False, allow_blank=True)
    torrentUrl = serializers.CharField(source='torrent_url', required=False, allow_blank=True)
    shortDescription = serializers.CharField(source='short_description', required=False, allow_blank=True)
    fullDescription = serializers.CharField(source='full_description', required=False, allow_blank=True)
    releaseYear = serializers.IntegerField(source='release_year')
    officialStoreLinks = serializers.JSONField(source='official_store_links', required=False)
    priceNote = serializers.CharField(source='price_note', required=False, allow_blank=True)
    subtitleStatus = serializers.CharField(source='subtitle_status')
    subtitleLanguage = serializers.CharField(source='subtitle_language', required=False)
    subtitleVersion = serializers.CharField(source='subtitle_version', required=False)
    subtitleLastUpdated = serializers.CharField(source='subtitle_last_updated', required=False)
    subtitleCompatibility = serializers.CharField(source='subtitle_compatibility', required=False, allow_blank=True)
    subtitleFormat = serializers.CharField(source='subtitle_format', required=False, allow_blank=True)
    subtitleSize = serializers.CharField(source='subtitle_size', required=False, allow_blank=True)
    subtitleDownloadUrl = serializers.CharField(source='subtitle_download_url', required=False, allow_blank=True)
    subtitlePrice = serializers.CharField(source='subtitle_price', required=False)
    subtitleTranslationType = serializers.CharField(source='subtitle_translation_type', required=False, allow_blank=True)
    installationGuide = serializers.JSONField(source='installation_guide', required=False)
    knownIssues = serializers.JSONField(source='known_issues', required=False)
    minimumRequirements = serializers.JSONField(source='minimum_requirements', required=False)
    recommendedRequirements = serializers.JSONField(source='recommended_requirements', required=False)
    isFeatured = serializers.BooleanField(source='is_featured', required=False)
    defaultExeName = serializers.CharField(source='default_exe_name', required=False, allow_blank=True)
    targetFileName = serializers.CharField(source='target_file_name', required=False, allow_blank=True)
    targetRelativeDir = serializers.CharField(source='target_relative_dir', required=False, allow_blank=True)
    keyPrefix = serializers.CharField(source='key_prefix', required=False, allow_blank=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)

    class Meta:
        model = Game
        fields = [
            'id', 'slug', 'title', 'cover', 'cardImage', 'heroImage',
            'gameplayVideoUrl', 'torrentUrl', 'screenshots',
            'shortDescription', 'fullDescription', 'releaseYear',
            'developer', 'publisher', 'genres', 'platforms',
            'officialStoreLinks', 'price', 'priceNote', 'isPaid',
            'subtitleStatus', 'subtitleLanguage', 'subtitleVersion',
            'subtitleLastUpdated', 'subtitleCompatibility', 'subtitleFormat',
            'subtitleSize', 'subtitleDownloadUrl', 'subtitlePrice',
            'subtitleTranslationType', 'installationGuide', 'knownIssues',
            'minimumRequirements', 'recommendedRequirements',
            'isFeatured', 'tags', 'defaultExeName', 'targetFileName',
            'targetRelativeDir', 'keyPrefix', 'createdAt', 'updatedAt'
        ]


class SliderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Slider
        fields = '__all__'
