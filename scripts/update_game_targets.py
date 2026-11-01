import os
import sys
import json
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from apps.games.models import Game


def update_game_targets():
    export_file = BASE_DIR / 'data' / 'firestore_full_export.json'
    if not export_file.exists():
        print(f"Error: {export_file} not found!", flush=True)
        return

    with open(export_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    games_data = data.get('games', [])
    print(f"Updating Launcher Targets for {len(games_data)} games...", flush=True)

    updated_count = 0
    for g in games_data:
        game_id = g.get('id') or g.get('slug')
        slug = g.get('slug') or game_id
        if not game_id:
            continue

        game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=slug).first()
        if not game:
            print(f"  [!] Game not found in db: {game_id}", flush=True)
            continue

        target_file_name = g.get('targetFileName') or ''
        target_relative_dir = g.get('targetRelativeDir') or ''
        key_prefix = g.get('keyPrefix') or ''
        default_exe_name = g.get('defaultExeName') or game.default_exe_name

        game.target_file_name = target_file_name
        game.target_relative_dir = target_relative_dir
        game.key_prefix = key_prefix
        game.default_exe_name = default_exe_name
        game.save(update_fields=['target_file_name', 'target_relative_dir', 'key_prefix', 'default_exe_name'])

        print(f"  [OK] {game.title}: dir='{target_relative_dir}', file='{target_file_name}', key='{key_prefix}'", flush=True)
        updated_count += 1

    print(f"\nSuccessfully updated {updated_count} games in PostgreSQL!", flush=True)


if __name__ == '__main__':
    update_game_targets()
