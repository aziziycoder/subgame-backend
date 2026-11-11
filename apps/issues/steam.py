"""Steam store lookups for translation requests. These endpoints are public but undocumented."""

import re

import requests
from django.core.cache import cache

SEARCH_URL = 'https://store.steampowered.com/api/storesearch/'
DETAILS_URL = 'https://store.steampowered.com/api/appdetails'
SEARCH_CACHE_SECONDS = 6 * 60 * 60
DETAILS_CACHE_SECONDS = 24 * 60 * 60
TIMEOUT_SECONDS = 6
MAX_RESULTS = 10

# Search reports soundtracks, demos and tools as plain apps, so the obvious ones are dropped by
# name. Voting re-checks the type through appdetails, which catches the rest.
NOT_A_GAME = re.compile(r'soundtrack|\bost\b|art ?book|playtest|\bdemo\b|dedicated server|\bsdk\b|wallpaper', re.IGNORECASE)
STEAM_APP_URL = re.compile(r'store\.steampowered\.com/app/(\d+)', re.IGNORECASE)


class SteamUnavailable(Exception):
    """Steam did not answer, or answered with something unusable."""


def _get_json(url, params):
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as err:
        raise SteamUnavailable(str(err)) from err


def search_games(query):
    """Returns up to MAX_RESULTS games matching `query`, as dicts with steamAppId, title and imageUrl."""
    key = f'steam-search:{query.strip().lower()}'
    cached = cache.get(key)
    if cached is not None:
        return cached

    data = _get_json(SEARCH_URL, {'term': query, 'l': 'english', 'cc': 'US'})
    results = [
        {'steamAppId': item['id'], 'title': item['name'], 'imageUrl': item.get('tiny_image', '')}
        for item in data.get('items', [])
        if item.get('type') == 'app' and item.get('id') and not NOT_A_GAME.search(item.get('name', ''))
    ][:MAX_RESULTS]
    cache.set(key, results, SEARCH_CACHE_SECONDS)
    return results


def get_game(app_id):
    """Returns the Steam game with this id, or None if it doesn't exist or isn't a game."""
    key = f'steam-game:{app_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached or None

    # appdetails only accepts several ids at once without filters, so it is one call per game.
    data = _get_json(DETAILS_URL, {'appids': app_id, 'filters': 'basic', 'l': 'english'})
    entry = data.get(str(app_id)) or {}
    details = entry.get('data') or {}
    game = None
    if entry.get('success') and details.get('type') == 'game' and details.get('name'):
        game = {'steamAppId': app_id, 'title': details['name'], 'imageUrl': details.get('header_image', '')}
    # An empty dict caches the "not a game" answer too, without confusing it with a miss.
    cache.set(key, game or {}, DETAILS_CACHE_SECONDS)
    return game


def steam_app_ids_of(game):
    """Steam app ids found in a site game's official store links."""
    ids = set()
    for link in game.official_store_links or []:
        url = link.get('url', '') if isinstance(link, dict) else ''
        match = STEAM_APP_URL.search(url)
        if match:
            ids.add(int(match.group(1)))
    return ids
