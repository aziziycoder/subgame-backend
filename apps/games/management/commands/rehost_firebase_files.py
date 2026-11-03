import os
from urllib.parse import unquote, urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.utils.text import get_valid_filename

from apps.games.models import Game, Slider

FIREBASE_HOSTS = ('firebasestorage.googleapis.com', 'firebasestorage.app', 'storage.googleapis.com')
GAME_FIELDS = ('cover', 'card_image', 'hero_image', 'torrent_url', 'subtitle_download_url')
SLIDER_FIELDS = ('bg_image', 'card_image')


def is_firebase_url(url):
    return isinstance(url, str) and any(host in url for host in FIREBASE_HOSTS)


class Command(BaseCommand):
    help = 'Copies files from Firebase Storage to local media and rewrites the stored URLs.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only list the files that would be copied.')

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.copied = {}
        self.failed = 0

        for game in Game.objects.all():
            self.process(game, GAME_FIELDS, game.slug)
            screenshots = [self.rehost(url, game.slug) for url in game.screenshots or []]
            if screenshots != (game.screenshots or []) and not self.dry_run:
                game.screenshots = screenshots
                game.save(update_fields=['screenshots', 'updated_at'])

        for slider in Slider.objects.all():
            self.process(slider, SLIDER_FIELDS, f'slider-{slider.slug}')

        self.stdout.write(f'Copied: {len(self.copied)}, failed: {self.failed}, dry run: {self.dry_run}')

    def process(self, obj, fields, folder):
        changed = []
        for field in fields:
            current = getattr(obj, field)
            updated = self.rehost(current, folder)
            if updated != current:
                setattr(obj, field, updated)
                changed.append(field)
        if changed and not self.dry_run:
            obj.save(update_fields=changed)

    def rehost(self, url, folder):
        if not is_firebase_url(url):
            return url
        if url in self.copied:
            return self.copied[url]

        if self.dry_run:
            self.stdout.write(f'Would copy: {url}')
            return url

        try:
            response = requests.get(url, timeout=300)
            response.raise_for_status()
        except requests.RequestException as err:
            # The old URL stays in place, so a failed file can be retried by running this again.
            self.failed += 1
            self.stderr.write(f'FAILED {url}: {err}')
            return url

        name = get_valid_filename(os.path.basename(unquote(urlparse(url).path))) or 'file'
        saved_path = default_storage.save(f'uploads/{get_valid_filename(folder)}/{name}', ContentFile(response.content))
        new_url = f"{settings.PUBLIC_API_URL.rstrip('/')}{settings.MEDIA_URL}{saved_path}"
        self.copied[url] = new_url
        self.stdout.write(f'{url} -> {new_url}')
        return new_url
