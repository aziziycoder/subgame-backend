import os
import sys
import json
import re
import django

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.games.models import Game

def import_games():
    seed_file = 'd:/Frontend/Projects/Game-sub/src/data/initialGamesSeed.ts'
    if not os.path.exists(seed_file):
        print(f"File not found: {seed_file}")
        return

    with open(seed_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Match each object block
    blocks = content.split('\n  {\n    id:')
    print(f"Found {len(blocks) - 1} game blocks in seed file.")

    imported = 0
    for i in range(1, len(blocks)):
        block = 'id:' + blocks[i].split('\n  },')[0].split('\n  }')[0]

        def get_field(pattern, default=''):
            m = re.search(pattern, block)
            return m.group(1).strip() if m else default

        def get_int(pattern, default=2024):
            m = re.search(pattern, block)
            return int(m.group(1)) if m else default

        def get_json(pattern, default=None):
            m = re.search(pattern, block, re.DOTALL)
            if m:
                raw = m.group(1)
                # rough JSON conversion
                try:
                    # Replace single quotes with double quotes
                    json_str = re.sub(r"'([^']*)'", r'"\1"', raw)
                    json_str = re.sub(r'(\w+):', r'"\1":', json_str)
                    return json.loads(json_str)
                except:
                    pass
            return default if default is not None else []

        gid = get_field(r"id:\s*['\"]([^'\"]+)['\"]")
        slug = get_field(r"slug:\s*['\"]([^'\"]+)['\"]", gid)
        title = get_field(r"title:\s*['\"]([^'\"]+)['\"]")
        cover = get_field(r"cover:\s*['\"]([^'\"]+)['\"]")
        card_image = get_field(r"cardImage:\s*['\"]([^'\"]+)['\"]")
        hero_image = get_field(r"heroImage:\s*['\"]([^'\"]+)['\"]")
        gameplay_video = get_field(r"gameplayVideoUrl:\s*['\"]([^'\"]+)['\"]")
        torrent_url = get_field(r"torrentUrl:\s*['\"]([^'\"]+)['\"]")
        short_desc = get_field(r"shortDescription:\s*['\"]([^'\"]+)['\"]")
        full_desc = get_field(r"fullDescription:\s*['\"]([^'\"]+)['\"]")
        release_year = get_int(r"releaseYear:\s*(\d+)")
        developer = get_field(r"developer:\s*['\"]([^'\"]+)['\"]")
        publisher = get_field(r"publisher:\s*['\"]([^'\"]+)['\"]")
        price = get_field(r"price:\s*['\"]([^'\"]+)['\"]", "Tekin")
        price_note = get_field(r"priceNote:\s*['\"]([^'\"]+)['\"]")
        sub_status = get_field(r"subtitleStatus:\s*['\"]([^'\"]+)['\"]", "Tayyor")
        sub_lang = get_field(r"subtitleLanguage:\s*['\"]([^'\"]+)['\"]", "O‘zbekcha (Lotin)")
        sub_ver = get_field(r"subtitleVersion:\s*['\"]([^'\"]+)['\"]", "v1.0.0")
        sub_updated = get_field(r"subtitleLastUpdated:\s*['\"]([^'\"]+)['\"]", "2026-10-28")
        sub_compat = get_field(r"subtitleCompatibility:\s*['\"]([^'\"]+)['\"]")
        sub_format = get_field(r"subtitleFormat:\s*['\"]([^'\"]+)['\"]")
        sub_size = get_field(r"subtitleSize:\s*['\"]([^'\"]+)['\"]")
        sub_dl = get_field(r"subtitleDownloadUrl:\s*['\"]([^'\"]+)['\"]")
        sub_price = get_field(r"subtitlePrice:\s*['\"]([^'\"]+)['\"]", "Bepul")
        sub_type = get_field(r"subtitleTranslationType:\s*['\"]([^'\"]+)['\"]")
        exe_name = get_field(r"defaultExeName:\s*['\"]([^'\"]+)['\"]")
        target_file = get_field(r"targetFileName:\s*['\"]([^'\"]+)['\"]")
        target_dir = get_field(r"targetRelativeDir:\s*['\"]([^'\"]+)['\"]")
        key_prefix = get_field(r"keyPrefix:\s*['\"]([^'\"]+)['\"]")

        # Genres & Screenshots
        genres_matches = re.findall(r"genres:\s*\[(.*?)\]", block, re.DOTALL)
        genres = [g.strip().strip("'\"") for g in genres_matches[0].split(',')] if genres_matches else []

        ss_matches = re.findall(r"screenshots:\s*\[(.*?)\]", block, re.DOTALL)
        screenshots = [s.strip().strip("'\"") for s in ss_matches[0].split(',') if s.strip()] if ss_matches else []

        if gid and title:
            game_obj, created = Game.objects.update_or_create(
                id=gid,
                defaults={
                    'slug': slug,
                    'title': title,
                    'cover': cover,
                    'card_image': card_image,
                    'hero_image': hero_image,
                    'gameplay_video_url': gameplay_video,
                    'torrent_url': torrent_url,
                    'screenshots': screenshots,
                    'short_description': short_desc,
                    'full_description': full_desc,
                    'release_year': release_year,
                    'developer': developer,
                    'publisher': publisher,
                    'genres': genres,
                    'price': price,
                    'price_note': price_note,
                    'subtitle_status': sub_status,
                    'subtitle_language': sub_lang,
                    'subtitle_version': sub_ver,
                    'subtitle_last_updated': sub_updated,
                    'subtitle_compatibility': sub_compat,
                    'subtitle_format': sub_format,
                    'subtitle_size': sub_size,
                    'subtitle_download_url': sub_dl,
                    'subtitle_price': sub_price,
                    'subtitle_translation_type': sub_type,
                    'default_exe_name': exe_name,
                    'target_file_name': target_file,
                    'target_relative_dir': target_dir,
                    'key_prefix': key_prefix,
                }
            )
            print(f"[{'CREATED' if created else 'UPDATED'}] {title} ({gid})")
            imported += 1

    # Also add Stray
    stray_obj, created = Game.objects.update_or_create(
        id='stray',
        defaults={
            'slug': 'stray',
            'title': 'Stray',
            'cover': 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1332010/library_600x900.jpg',
            'card_image': 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1332010/header.jpg',
            'hero_image': 'https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1332010/ss_891e4fb442f4b005be7ff8ec0e3636f45a0b73df.1920x1080.jpg',
            'short_description': 'Adashgan, yolg‘iz va oilasidan ajralgan mushuk kiber-shaharning neon chiroqlari ostidagi qadimiy sirni ochishi va uyiga yo‘l topishi kerak.',
            'release_year': 2022,
            'developer': 'BlueTwelve Studio',
            'publisher': 'Annapurna Interactive',
            'genres': ['Sarguzasht', 'Kiberpank', 'Boshqotirma'],
            'price': '15 000 so‘m',
            'subtitle_price': '15 000 so‘m',
            'subtitle_status': 'Tayyor',
            'subtitle_version': 'v1.3.0',
            'default_exe_name': 'Stray-Win64-Shipping.exe',
            'target_file_name': 'pakchunk99-WindowsNoEditor_Uzbek_P.pak',
            'target_relative_dir': 'Hk_project/Content/Paks',
            'key_prefix': 'SUB-STRY',
        }
    )
    print(f"[{'CREATED' if created else 'UPDATED'}] Stray (stray)")

    print(f"\nTotal games imported: {imported + 1}")

if __name__ == '__main__':
    import_games()
