"""Live Official Music Charts & Cloud Radio Discovery Service.

Fetches dynamic live charts (UK Official, US Billboard, Global Hits, Top Albums)
and live official Deezer radio streams with zero hardcoding.
"""
import concurrent.futures
import json
import os
import random

from ..utils.http_client import fetch_json
from ..utils.normalizer import is_junk_album
from core.logger import get_logger
from .. import store

_log = get_logger("official_charts")

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "official_charts_data.json")

def _load_chart_data():
    try:
        if os.path.exists(_DATA_PATH):
            with open(_DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        _log.error("Failed to load chart data: %s", e)
    return {}

_CHART_DATA = _load_chart_data()
DEFAULT_CHART_FEEDS = {
    "gb": {
        "title": "UK Official Top 50 Singles",
        "url": "https://itunes.apple.com/gb/rss/topsongs/limit=50/json",
        "badge": "🇬🇧 UK OFFICIAL SINGLES",
        "type": "itunes_tracks",
        "fallback_url": "https://rss.applemarketingtools.com/api/v2/gb/music/most-played/50/songs.json"
    },
    "us": {
        "title": "US Billboard Hot 50 Singles",
        "url": "https://itunes.apple.com/us/rss/topsongs/limit=50/json",
        "badge": "🇺🇸 US BILLBOARD HOT 50",
        "type": "itunes_tracks",
        "fallback_url": "https://rss.applemarketingtools.com/api/v2/us/music/most-played/50/songs.json"
    },
    "global": {
        "title": "Global Top 50 Viral Hits",
        "url": "https://itunes.apple.com/us/rss/topsongs/limit=50/json",
        "badge": "🌍 WORLDWIDE NO. 1s",
        "type": "itunes_tracks"
    },
    "albums_gb": {
        "title": "UK Official Top 50 Albums",
        "url": "https://itunes.apple.com/gb/rss/topalbums/limit=50/json",
        "badge": "💿 UK TOP 50 ALBUMS",
        "type": "itunes_albums",
        "fallback_url": "https://rss.applemarketingtools.com/api/v2/gb/music/most-played/50/albums.json"
    },
    "albums_us": {
        "title": "US Billboard 200 Albums",
        "url": "https://itunes.apple.com/us/rss/topalbums/limit=50/json",
        "badge": "🏆 US BILLBOARD 200",
        "type": "itunes_albums",
        "fallback_url": "https://rss.applemarketingtools.com/api/v2/us/music/most-played/50/albums.json"
    }
}
APPLE_OFFICIAL_FEEDS = {**_CHART_DATA.get("APPLE_OFFICIAL_FEEDS", {}), **DEFAULT_CHART_FEEDS}
STATION_METAS = _CHART_DATA.get("STATION_METAS", {})
CURATED_STATIONS = _CHART_DATA.get("CURATED_STATIONS", [])

def get_live_official_charts(country: str = "gb", limit: int = 50, force_refresh: bool = False) -> dict:
    """Fetch live official songs or albums chart from Apple Music RSS / iTunes / Deezer and enhance with stream metadata."""
    c_key = (country or "gb").lower().strip()
    feed_info = APPLE_OFFICIAL_FEEDS.get(c_key, DEFAULT_CHART_FEEDS.get("gb"))
    feed_url = feed_info.get("url", "")
    feed_type = feed_info.get("type", "itunes_tracks")

    data = fetch_json(feed_url, timeout=10.0, cache_ttl=0 if force_refresh else 1800)
    if not data and feed_info.get("fallback_url"):
        data = fetch_json(feed_info["fallback_url"], timeout=10.0, cache_ttl=0 if force_refresh else 1800)

    items = []

    if feed_type in ("apple_tracks", "itunes_tracks"):
        raw_results = data.get("feed", {}).get("results", []) if data else []
        raw_entries = data.get("feed", {}).get("entry", []) if data else []

        if raw_entries:
            for idx, e in enumerate(raw_entries[:limit]):
                title = (e.get("im:name", {}).get("label") or "").strip()
                artist = (e.get("im:artist", {}).get("label") or "").strip()
                if not title or not artist:
                    continue
                images = e.get("im:image", [])
                raw_artwork = images[-1].get("label", "") if images else ""
                artwork = raw_artwork.replace("170x170bb.png", "1000x1000bb.jpg").replace("170x170bb.jpg", "1000x1000bb.jpg").replace("100x100bb.jpg", "1000x1000bb.jpg") if raw_artwork else ""
                alb = e.get("im:collection", {}).get("im:name", {}).get("label") or title
                rel_date = str(e.get("im:releaseDate", {}).get("label") or "")[:10]
                items.append({
                    "position": idx + 1,
                    "id": f"itunes-{c_key}-{idx + 1}",
                    "title": title,
                    "artist": artist,
                    "cover": artwork,
                    "album": alb,
                    "url": e.get("link", {}).get("attributes", {}).get("href", "") if isinstance(e.get("link"), dict) else "",
                    "release_date": rel_date
                })
        elif raw_results:
            for idx, item in enumerate(raw_results[:limit]):
                artist = (item.get("artistName") or "").strip()
                title = (item.get("name") or "").strip()
                if not artist or not title:
                    continue
                raw_artwork = item.get("artworkUrl100", "")
                artwork = raw_artwork.replace("100x100bb.jpg", "1000x1000bb.jpg") if raw_artwork else ""
                items.append({
                    "position": idx + 1,
                    "id": f"official-{c_key}-{idx + 1}",
                    "title": title,
                    "artist": artist,
                    "cover": artwork,
                    "album": title,
                    "url": item.get("url", ""),
                    "release_date": str(item.get("releaseDate") or "")[:10]
                })

    elif feed_type in ("apple_albums", "itunes_albums"):
        raw_results = data.get("feed", {}).get("results", []) if data else []
        raw_entries = data.get("feed", {}).get("entry", []) if data else []

        if raw_entries:
            for idx, e in enumerate(raw_entries[:limit]):
                title = (e.get("im:name", {}).get("label") or "").strip()
                artist = (e.get("im:artist", {}).get("label") or "").strip()
                if not title or not artist:
                    continue
                images = e.get("im:image", [])
                raw_artwork = images[-1].get("label", "") if images else ""
                artwork = raw_artwork.replace("170x170bb.png", "1000x1000bb.jpg").replace("170x170bb.jpg", "1000x1000bb.jpg").replace("100x100bb.jpg", "1000x1000bb.jpg") if raw_artwork else ""
                rel_date = str(e.get("im:releaseDate", {}).get("label") or "")[:10]
                items.append({
                    "position": idx + 1,
                    "id": f"official-alb-{c_key}-{idx + 1}",
                    "title": title,
                    "artist": artist,
                    "cover": artwork,
                    "album": title,
                    "is_album": True,
                    "url": e.get("link", {}).get("attributes", {}).get("href", "") if isinstance(e.get("link"), dict) else "",
                    "release_date": rel_date
                })
        elif raw_results:
            for idx, item in enumerate(raw_results[:limit]):
                artist = (item.get("artistName") or "").strip()
                title = (item.get("name") or "").strip()
                if not artist or not title:
                    continue
                raw_artwork = item.get("artworkUrl100", "")
                artwork = raw_artwork.replace("100x100bb.jpg", "1000x1000bb.jpg") if raw_artwork else ""
                raw_id = str(item.get("id") or "").strip()
                album_id = f"apple:{raw_id}" if raw_id else f"official-alb-{c_key}-{idx + 1}"
                items.append({
                    "position": idx + 1,
                    "id": album_id,
                    "title": title,
                    "artist": artist,
                    "cover": artwork,
                    "album": title,
                    "is_album": True,
                    "url": item.get("url", ""),
                    "release_date": str(item.get("releaseDate") or "")[:10]
                })

    elif feed_type == "deezer_tracks":
        raw_results = data.get("data", []) if data else []
        for idx, item in enumerate(raw_results[:limit]):
            artist = item.get("artist", {}).get("name") or ""
            title = item.get("title") or ""
            if not artist or not title:
                continue
            alb = item.get("album", {})
            artwork = alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium") or ""
            items.append({
                "position": idx + 1,
                "id": str(item.get("id")),
                "title": title,
                "artist": artist,
                "cover": artwork,
                "album": alb.get("title") or title,
                "duration": item.get("duration", 0),
                "preview_url": item.get("preview", ""),
                "release_date": ""
            })

    if not items:
        try:
            deezer_chart_url = f"https://api.deezer.com/chart/0/tracks?limit={limit}"
            d_data = fetch_json(deezer_chart_url, timeout=6.0, cache_ttl=1800)
            if d_data and "data" in d_data:
                for idx, item in enumerate(d_data.get("data", [])[:limit]):
                    items.append({
                        "position": idx + 1,
                        "id": str(item.get("id")),
                        "title": item.get("title", ""),
                        "artist": item.get("artist", {}).get("name", ""),
                        "cover": item.get("album", {}).get("cover_xl") or item.get("album", {}).get("cover_medium", ""),
                        "album": item.get("album", {}).get("title", ""),
                        "duration": item.get("duration", 0),
                        "url": item.get("link", "")
                    })
        except Exception:
            pass
        else:
            for idx, item in enumerate(raw_results[:limit]):
                artist = (item.get("artistName") or "").strip()
                title = (item.get("name") or "").strip()
                if not artist or not title:
                    continue
                raw_artwork = item.get("artworkUrl100", "")
                artwork = raw_artwork.replace("100x100bb.jpg", "1000x1000bb.jpg") if raw_artwork else ""
                items.append({
                    "position": idx + 1,
                    "id": f"official-{country}-{idx + 1}",
                    "title": title,
                    "artist": artist,
                    "cover": artwork,
                    "album": title,
                    "url": item.get("url", ""),
                    "release_date": str(item.get("releaseDate") or "")[:10]
                })

    elif feed_type == "apple_albums":
        raw_results = data.get("feed", {}).get("results", []) if data else []
        for idx, item in enumerate(raw_results[:limit]):
            artist = (item.get("artistName") or "").strip()
            title = (item.get("name") or "").strip()
            if not artist or not title:
                continue
            raw_artwork = item.get("artworkUrl100", "")
            artwork = raw_artwork.replace("100x100bb.jpg", "1000x1000bb.jpg") if raw_artwork else ""
            raw_id = str(item.get("id") or "").strip()
            album_id = f"apple:{raw_id}" if raw_id else f"official-alb-{country}-{idx + 1}"
            items.append({
                "position": idx + 1,
                "id": album_id,
                "title": title,
                "artist": artist,
                "cover": artwork,
                "album": title,
                "is_album": True,
                "url": item.get("url", ""),
                "release_date": str(item.get("releaseDate") or "")[:10]
            })

    elif feed_type == "deezer_tracks":
        raw_results = data.get("data", []) if data else []
        for idx, item in enumerate(raw_results[:limit]):
            artist = item.get("artist", {}).get("name") or ""
            title = item.get("title") or ""
            if not artist or not title:
                continue
            alb = item.get("album", {})
            artwork = alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium") or ""
            items.append({
                "position": idx + 1,
                "id": str(item.get("id")),
                "title": title,
                "artist": artist,
                "cover": artwork,
                "album": alb.get("title") or title,
                "duration": item.get("duration", 0),
                "preview_url": item.get("preview", ""),
                "release_date": ""
            })

    if not items:
        try:
            deezer_chart_url = f"https://api.deezer.com/chart/0/tracks?limit={limit}"
            d_data = fetch_json(deezer_chart_url, timeout=6.0, cache_ttl=1800)
            if d_data and "data" in d_data:
                for idx, item in enumerate(d_data.get("data", [])[:limit]):
                    items.append({
                        "position": idx + 1,
                        "id": str(item.get("id")),
                        "title": item.get("title", ""),
                        "artist": item.get("artist", {}).get("name", ""),
                        "cover": item.get("album", {}).get("cover_xl") or item.get("album", {}).get("cover_medium", ""),
                        "album": item.get("album", {}).get("title", ""),
                        "duration": item.get("duration", 0),
                        "url": item.get("link", "")
                    })
        except Exception:
            pass

    return {
        "title": feed_info["title"],
        "badge": feed_info["badge"],
        "country": country,
        "is_album_chart": feed_type == "apple_albums",
        "tracks": items,
        "count": len(items)
    }


def get_live_radio_tracks(radio_id: str, limit: int = 25, force_refresh: bool = False) -> list[dict]:
    """Fetch live tracks from a specific official Deezer radio channel."""
    rid = str(radio_id or "").strip()
    if not rid:
        return []

    # Check if curated station seed
    if rid.startswith("radio-curated-"):
        rid = rid[6:]  # strip 'radio-'
    if rid.startswith("curated-"):
        curated_list = _load_chart_data().get("CURATED_STATIONS", CURATED_STATIONS)
        for cs in curated_list:
            if cs.get("radio_id") == rid or cs.get("id") == rid or cs.get("id") == f"radio-{rid}":
                return cs.get("singles", [])[:limit]

    url = f"https://api.deezer.com/radio/{rid}/tracks"
    data = fetch_json(url, cache_ttl=0 if force_refresh else 900)  # Bypass cache on force refresh
    raw = data.get("data", []) if data else []

    tracks = []
    for t in raw[:limit]:
        tid = str(t.get("id") or "")
        title = (t.get("title") or "").strip()
        art = t.get("artist") or {}
        alb = t.get("album") or {}
        if not tid or not title:
            continue
        cover = alb.get("cover_big") or alb.get("cover_medium") or alb.get("cover") or ""
        tracks.append({
            "id": tid,
            "title": title,
            "artist": art.get("name") or "",
            "artist_id": str(art.get("id") or ""),
            "album": alb.get("title") or "",
            "album_id": str(alb.get("id") or ""),
            "cover": cover,
            "duration": t.get("duration", 0),
            "preview_url": t.get("preview", ""),
            "explicit": t.get("explicit_lyrics", False)
        })
    return tracks


def get_live_dj_stations(limit: int = 250, force_refresh: bool = False) -> list[dict]:
    """Dynamically construct live DJ stations from curated presets and official Deezer radio categories."""
    cache_key = "https://album-discovery.internal/live_dj_stations_v11"
    if not force_refresh:
        cached = store.get_api_cache(cache_key)
        if cached and isinstance(cached, list) and len(cached) > 0:
            return cached[:limit]

    stations = []

    # 1. Add all Curated Decades & Mood stations first!
    curated_list = _load_chart_data().get("CURATED_STATIONS", CURATED_STATIONS)
    for cs in curated_list:
        stations.append(dict(cs))

    # 2. Add Live Cloud Radio Categories from Deezer
    url = "https://api.deezer.com/radio/genres"
    data = fetch_json(url, cache_ttl=0 if force_refresh else 1800)  # Bypass cache on force refresh
    categories = data.get("data", []) if data else []

    blank_hashes = {
        "9079f8fa55799fa7d10da72c578ab846",
        "b2dfd860d84c13a693b48455fa2c46f1",
        "f47f2ffbe8df7cae96f1d82121e7845f",
        "25eb5bf396788dbd111d4e0bbfdca6b3",
        "15ce110191c95b6cbe19e7102e3bce7c"
    }

    def _build_stations_for_category(cat):
        title = cat.get("title", "")
        radios = cat.get("radios", [])
        if not radios:
            return []

        built = []
        for lead in radios[:2]:
            rid = str(lead.get("id") or "")
            if not rid:
                continue

            sub_title = lead.get("title") or title
            meta = None
            for k, v in STATION_METAS.items():
                if k.lower() in title.lower() or k.lower() in sub_title.lower():
                    meta = v
                    break
            if not meta:
                badge_name = (sub_title if sub_title != title else title).upper()[:16]
                meta = {
                    "color": "#06b6d4",
                    "icon": "📻",
                    "badge": f"📻 {badge_name}",
                    "desc": f"Live streaming {sub_title} broadcast directly from cloud feeds.",
                    "category": "genres"
                }

            live_tracks = get_live_radio_tracks(rid, limit=5, force_refresh=force_refresh)
            pic = lead.get("picture_big") or lead.get("picture_medium") or lead.get("picture") or ""
            singles = []
            for t in live_tracks:
                cov = t.get("cover") or pic or "/placeholder-cover.svg"
                if any(bh in cov for bh in blank_hashes) or not cov.strip():
                    cov = pic or "/placeholder-cover.svg"
                singles.append({
                    "id": t["id"],
                    "title": t["title"],
                    "artist": t["artist"],
                    "album": t["album"],
                    "cover": cov,
                    "dur": t["duration"],
                    "preview_url": t["preview_url"]
                })

            if not singles:
                continue

            seed_artist = singles[0]["artist"] if singles else sub_title

            display_title = f"Live {sub_title} Broadcast" if sub_title != title else f"Live {title} Radio"
            display_subtitle = title if sub_title != title else "Official Cloud Radio"

            built.append({
                "id": f"radio-{rid}",
                "title": display_title,
                "sub_title": display_subtitle,
                "radio_id": rid,
                "genre": title,
                "category": meta.get("category", "genres"),
                "badge": meta["badge"],
                "icon": meta["icon"],
                "color": meta["color"],
                "desc": meta["desc"],
                "picture": pic,
                "seedArtist": seed_artist,
                "singles": singles,
                "algorithm": "deezer",
                "algorithm_name": "⚡ Deezer Cloud"
            })
        return built

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(_build_stations_for_category, cat) for cat in categories]
        for f in concurrent.futures.as_completed(futures):
            try:
                station_batch = f.result()
                if station_batch:
                    stations.extend(station_batch)
            except Exception as e:
                _log.debug(f"Error building stations: {e}")

    if stations:
        store.set_api_cache(cache_key, stations, ttl_seconds=1800, namespace="dj_stations")

    return stations[:limit]
