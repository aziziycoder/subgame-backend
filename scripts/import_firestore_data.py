import os
import sys
import json
from pathlib import Path
from datetime import datetime

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from apps.users.models import User
from apps.games.models import Game
from apps.licenses.models import License
from apps.payments.models import Order


def parse_dt(val):
    if not val:
        return timezone.now()
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        parsed = parse_datetime(val)
        if parsed:
            if timezone.is_naive(parsed):
                return timezone.make_aware(parsed)
            return parsed
    return timezone.now()


def run_migration():
    export_file = BASE_DIR / 'data' / 'firestore_full_export.json'
    if not export_file.exists():
        print(f"Error: {export_file} not found!", flush=True)
        return

    with open(export_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 60, flush=True)
    print("MIGRATING FIRESTORE DATA TO POSTGRESQL / DJANGO DATABASE", flush=True)
    print("=" * 60, flush=True)

    # 1. MIGRATE GAMES
    print(f"\n[1/4] Migrating Games ({len(data['games'])} games)...", flush=True)
    game_map = {}

    with transaction.atomic():
        for g in data['games']:
            game_id = g.get('id') or g.get('slug')
            slug = g.get('slug') or game_id
            if not game_id or not slug:
                continue

            defaults = {
                'slug': slug,
                'title': g.get('title') or slug.replace('-', ' ').title(),
                'cover': g.get('cover') or g.get('cardImage') or '',
                'card_image': g.get('cardImage') or '',
                'hero_image': g.get('heroImage') or '',
                'gameplay_video_url': g.get('gameplayVideoUrl') or '',
                'torrent_url': g.get('torrentUrl') or '',
                'screenshots': g.get('screenshots') or [],
                'short_description': g.get('shortDescription') or '',
                'full_description': g.get('fullDescription') or '',
                'release_year': g.get('releaseYear') or 2024,
                'developer': g.get('developer') or '',
                'publisher': g.get('publisher') or '',
                'genres': g.get('genres') or [],
                'platforms': g.get('platforms') or ['PC'],
                'official_store_links': g.get('officialStoreLinks') or [],
                'price': str(g.get('price') or 'Tekin'),
                'price_note': g.get('priceNote') or '',
                'subtitle_status': g.get('subtitleStatus') or 'Tayyor',
                'subtitle_language': g.get('subtitleLanguage') or 'O‘zbekcha (Lotin)',
                'subtitle_version': g.get('subtitleVersion') or 'v1.0.0',
                'subtitle_last_updated': str(g.get('subtitleLastUpdated') or '2026-10-28'),
                'subtitle_compatibility': g.get('subtitleCompatibility') or '',
                'subtitle_format': g.get('subtitleFormat') or '',
                'subtitle_size': g.get('subtitleSize') or '',
                'subtitle_download_url': g.get('subtitleDownloadUrl') or '',
                'subtitle_price': str(g.get('subtitlePrice') or 'Bepul'),
                'subtitle_translation_type': g.get('subtitleTranslationType') or '',
                'installation_guide': g.get('installationGuide') or [],
                'known_issues': g.get('knownIssues') or [],
                'minimum_requirements': g.get('minimumRequirements') or {},
                'recommended_requirements': g.get('recommendedRequirements') or {},
                'is_featured': bool(g.get('isFeatured', False)),
                'tags': g.get('tags') or [],
                'default_exe_name': g.get('defaultExeName') or '',
                'target_file_name': g.get('targetFileName') or '',
                'target_relative_dir': g.get('targetRelativeDir') or '',
                'key_prefix': g.get('keyPrefix') or '',
            }

            obj, _ = Game.objects.update_or_create(id=game_id, defaults=defaults)
            game_map[game_id] = obj
            game_map[slug] = obj

    print(f"  Games done: {len(game_map)} indexed.", flush=True)

    # 2. MIGRATE USERS
    print(f"\n[2/4] Migrating Users ({len(data['users'])} users)...", flush=True)
    existing_users = {u.email.lower(): u for u in User.objects.all()}
    existing_by_id = {u.id: u for u in existing_users.values()}

    user_by_id = {}
    user_by_email = {}

    with transaction.atomic():
        for u in data['users']:
            uid = u['id']
            email = u['email'].strip().lower()
            if not email:
                continue

            user = existing_users.get(email) or existing_by_id.get(uid)
            created_at_dt = parse_dt(u.get('createdAt'))

            if not user:
                user = User(
                    id=uid,
                    email=email,
                    display_name=(u.get('displayName') or email.split('@')[0])[:255],
                    photo_url=u.get('photoUrl') or '',
                    role=u.get('role', 'user'),
                    is_staff=bool(u.get('isStaff', False)),
                    is_superuser=bool(u.get('isSuperuser', False)),
                    created_at=created_at_dt
                )
                user.set_unusable_password()
                user.save()
                existing_users[email] = user
                existing_by_id[uid] = user
            else:
                changed = False
                if not user.display_name and u.get('displayName'):
                    user.display_name = u['displayName']
                    changed = True
                if not user.photo_url and u.get('photoUrl'):
                    user.photo_url = u['photoUrl']
                    changed = True
                if u.get('isSuperuser') and not user.is_superuser:
                    user.is_superuser = True
                    user.is_staff = True
                    user.role = 'admin'
                    changed = True
                if changed:
                    user.save()

            user_by_id[uid] = user
            user_by_email[email] = user

    print(f"  Users done: {len(user_by_id)} cached.", flush=True)

    # 3. MIGRATE LICENSES
    print(f"\n[3/4] Migrating Licenses ({len(data['licenses'])} licenses)...", flush=True)
    existing_licenses = {lic.id: lic for lic in License.objects.all()}
    user_game_pairs = {(lic.user_id, lic.game_id): lic for lic in existing_licenses.values()}

    licenses_created = 0
    licenses_updated = 0
    licenses_skipped = 0

    with transaction.atomic():
        for lic in data['licenses']:
            lic_id = lic['id']
            user_id = lic.get('userId') or lic_id.split('_')[0]
            email = (lic.get('userEmail') or '').strip().lower()
            game_id = lic.get('gameId') or lic.get('gameSlug')

            user = user_by_id.get(user_id) or user_by_email.get(email) or existing_users.get(email) or existing_by_id.get(user_id)
            if not user:
                if email:
                    user = User(
                        id=user_id,
                        email=email,
                        display_name=(lic.get('userName') or email.split('@')[0])[:255],
                        photo_url=lic.get('userPhoto') or ''
                    )
                    user.set_unusable_password()
                    user.save()
                    user_by_id[user_id] = user
                    user_by_email[email] = user
                    existing_users[email] = user
                    existing_by_id[user_id] = user
                else:
                    licenses_skipped += 1
                    continue

            game = game_map.get(game_id)
            if not game:
                game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=game_id).first()
            if not game:
                game = Game.objects.create(
                    id=game_id,
                    slug=game_id,
                    title=lic.get('gameTitle') or game_id.replace('-', ' ').title(),
                    cover='',
                    price='Tekin'
                )
                game_map[game_id] = game

            created_at_dt = parse_dt(lic.get('createdAt'))
            bound_at_dt = parse_dt(lic.get('boundAt')) if lic.get('boundAt') else None

            status = lic.get('status', 'active')
            hwid = lic.get('hwid')
            bound_device_name = lic.get('boundDeviceName')
            payment_provider = lic.get('paymentProvider', 'none')
            payment_ref = str(lic.get('paymentRef') or '')
            paid_amount = int(lic.get('paidAmount') or 0)
            revoked_reason = lic.get('revokedReason', '')

            existing = user_game_pairs.get((user.id, game.id)) or existing_licenses.get(lic_id)

            if existing:
                existing.status = status
                if hwid and not existing.hwid:
                    existing.hwid = hwid
                    existing.bound_at = bound_at_dt
                    existing.bound_device_name = bound_device_name
                if payment_ref and not existing.payment_ref:
                    existing.payment_ref = payment_ref
                    existing.payment_provider = payment_provider
                    existing.paid_amount = paid_amount
                existing.save()
                licenses_updated += 1
            else:
                new_lic = License(
                    id=lic_id,
                    user=user,
                    game=game,
                    user_email=user.email,
                    user_name=lic.get('userName') or user.display_name,
                    user_photo=lic.get('userPhoto') or user.photo_url,
                    game_title=game.title,
                    game_slug=game.slug,
                    status=status,
                    hwid=hwid,
                    bound_at=bound_at_dt,
                    bound_device_name=bound_device_name,
                    payment_provider=payment_provider,
                    payment_ref=payment_ref,
                    paid_amount=paid_amount,
                    revoked_reason=revoked_reason,
                    created_at=created_at_dt
                )
                new_lic.save()
                user_game_pairs[(user.id, game.id)] = new_lic
                existing_licenses[lic_id] = new_lic
                licenses_created += 1

    print(f"  Licenses done: {licenses_created} created, {licenses_updated} updated, {licenses_skipped} skipped.", flush=True)

    # 4. MIGRATE ORDERS
    print(f"\n[4/4] Migrating Orders ({len(data['orders'])} orders)...", flush=True)
    orders_created = 0
    orders_updated = 0

    with transaction.atomic():
        for ord_data in data.get('orders', []):
            order_id = ord_data.get('orderId') or ord_data.get('id')
            if not order_id:
                continue
            user_id = ord_data.get('userId') or (order_id.split('__')[0] if '__' in order_id else '')
            email = (ord_data.get('userEmail') or '').strip().lower()
            game_id = ord_data.get('gameId') or ord_data.get('gameSlug') or (order_id.split('__')[1] if '__' in order_id else '')

            user = user_by_id.get(user_id) or user_by_email.get(email) or existing_users.get(email) or existing_by_id.get(user_id)
            game = game_map.get(game_id)
            if not game and game_id:
                game = Game.objects.filter(id=game_id).first() or Game.objects.filter(slug=game_id).first()

            if not user or not game:
                continue

            created_at_dt = parse_dt(ord_data.get('createdAt'))
            order, created = Order.objects.update_or_create(
                order_id=order_id,
                defaults={
                    'user': user,
                    'game': game,
                    'user_email': user.email,
                    'game_title': game.title,
                    'game_slug': game.slug,
                    'amount': ord_data.get('amount', 5000),
                    'currency': ord_data.get('currency', 'UZS'),
                    'status': 'paid',
                    'payment_provider': ord_data.get('paymentProvider', 'click'),
                    'click_trans_id': ord_data.get('clickTransId', ''),
                    'paid_amount': ord_data.get('paidAmount', 5000),
                    'created_at': created_at_dt
                }
            )
            if created:
                orders_created += 1
            else:
                orders_updated += 1

    print(f"  Orders done: {orders_created} created, {orders_updated} updated.", flush=True)

    print("\n" + "=" * 60, flush=True)
    print("MIGRATION COMPLETED SUCCESSFULLY!", flush=True)
    print(f"Total Games in DB:    {Game.objects.count()}", flush=True)
    print(f"Total Users in DB:    {User.objects.count()}", flush=True)
    print(f"Total Licenses in DB: {License.objects.count()}", flush=True)
    print(f"Total Orders in DB:   {Order.objects.count()}", flush=True)
    print("=" * 60, flush=True)


if __name__ == '__main__':
    run_migration()
