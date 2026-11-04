"""Live New Releases Feed Service.
Fetches fresh studio album drops from live editorial feeds (Apple Music + Deezer).
Zero hardcoded data, 100% dynamic live queries with L1 Memory + L2 SQLite WAL caching.
"""
import concurrent.futures
import urllib.parse
from ..utils.http_client import fetch_json
from ..utils.normalizer import is_junk_album
from core.logger import get_logger

_log = get_logger("releases")

APPLE_FEEDS = [
    "https://rss.applemarketingtools.com/api/v2/us/music/most-played/100/albums.json",
    "https://rss.applemarketingtools.com/api/v2/gb/music/most-played/100/albums.json",
]


def _resolve_deezer_album(artist: str, title: str) -> dict:
    """Attempt to match an editorial drop with the Deezer catalog for full Deezer ID & previews."""
    clean_artist = (artist or "").strip()
    clean_title = (title or "").strip()
    if not clean_artist or not clean_title:
        return {}

    q = f"{clean_artist} {clean_title}"
    url = f"https://api.deezer.com/search/album?q={urllib.parse.quote(q)}&limit=1"
    data = fetch_json(url, cache_ttl=86400, namespace="dz_album_match")
    if data and data.get("data"):
        match = data["data"][0]
        return {
            "deezer_id": str(match.get("id") or ""),
            "cover": match.get("cover_xl") or match.get("cover_big") or match.get("cover_medium") or "",
            "tracks_count": match.get("nb_tracks", 0),
            "record_type": (match.get("record_type") or "album").title(),
        }
    return {}


def get_new_releases(limit: int = 100) -> dict:
    """Fetch live new releases this week, merge catalog IDs, and categorize."""
    cache_key = f"new_releases_v2_{limit}"
    
    seen_titles = set()
    raw_candidates = []

    for feed_url in APPLE_FEEDS:
        feed_data = fetch_json(feed_url, cache_ttl=1800, namespace="new_releases")  # 30 min cache
        if not feed_data or "feed" not in feed_data:
            continue
        
        results = feed_data["feed"].get("results", [])
        for item in results:
            title = (item.get("name") or "").strip()
            artist = (item.get("artistName") or "").strip()
            aid = str(item.get("id") or "")
            if not title or not artist or is_junk_album(title, artist):
                continue
            
            key = (title.lower(), artist.lower())
            if key in seen_titles:
                continue
            seen_titles.add(key)

            artwork = item.get("artworkUrl100", "")
            if artwork:
                cover = artwork.replace("/100x100bb.jpg", "/1000x1000bb.jpg").replace("/100x100bb.png", "/1000x1000bb.png")
            else:
                cover = ""

            genres = [g.get("name") for g in item.get("genres", []) if g.get("name")]
            primary_genre = genres[0] if genres else "Music"

            raw_candidates.append({
                "apple_id": aid,
                "title": title,
                "artist": artist,
                "release_date": item.get("releaseDate", ""),
                "cover": cover,
                "genre": primary_genre,
                "url": item.get("url", ""),
            })

    if not raw_candidates:
        return {"albums": [], "categories": [], "counts": {}, "total": 0}

    # Parallel Deezer resolution up to requested limit (from settings, default 100)
    target_limit = max(10, min(150, int(limit or 100)))
    to_resolve = raw_candidates[:target_limit]
    
    def _enrich(item):
        dz_match = _resolve_deezer_album(item["artist"], item["title"])
        aid = dz_match.get("deezer_id") or f"apple:{item['apple_id']}"
        cover = dz_match.get("cover") or item["cover"]
        tracks_count = dz_match.get("tracks_count", 0)
        
        # Categorize
        t_lower = item["title"].lower()
        if "ep" in t_lower or " ep" in t_lower:
            cat = "EPs"
        elif "single" in t_lower:
            cat = "Singles"
        elif "live" in t_lower:
            cat = "Live Albums"
        elif "remix" in t_lower:
            cat = "Remixes"
        else:
            cat = "Studio Albums"

        return {
            "id": aid,
            "title": item["title"],
            "artist": item["artist"],
            "cover": cover,
            "release_date": item["release_date"],
            "year": item["release_date"][:4] if item["release_date"] else "",
            "category": cat,
            "record_type": cat,
            "genre": item["genre"],
            "tracks_count": tracks_count,
            "source": "✨ Fresh New Drop",
            "is_new": True,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        albums = list(ex.map(_enrich, to_resolve))

    # Sort by release date descending
    albums.sort(key=lambda x: x.get("release_date") or "0000", reverse=True)

    category_counts = {}
    for alb in albums:
        cat = alb.get("category") or "Studio Albums"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    desired_order = ["Studio Albums", "EPs", "Singles", "Live Albums", "Remixes"]
    sorted_categories = [c for c in desired_order if c in category_counts]
    for c in category_counts:
        if c not in sorted_categories:
            sorted_categories.append(c)

    _log.info("[New Releases] Fetched %d fresh releases across %d categories", len(albums), len(sorted_categories))

    return {
        "albums": albums[:limit],
        "categories": sorted_categories,
        "counts": category_counts,
        "total": len(albums)
    }


def get_apple_album_details(apple_id: str) -> dict:
    """Fetch tracklist & metadata for an Apple Music album via iTunes API."""
    raw_id = str(apple_id).replace("apple:", "").strip()
    if not raw_id:
        return {"error": "Invalid album id"}

    url = f"https://itunes.apple.com/lookup?id={raw_id}&entity=song&limit=200"
    data = fetch_json(url, cache_ttl=3600, namespace="apple_album")
    if not data or not data.get("results"):
        return {"error": "Album not found on catalog"}

    results = data["results"]
    collection = results[0] if results else {}
    tracks_data = [r for r in results if r.get("wrapperType") == "track"]

    title = collection.get("collectionName") or "Unknown Album"
    artist = collection.get("artistName") or "Unknown Artist"
    cover_100 = collection.get("artworkUrl100") or ""
    cover = cover_100.replace("/100x100bb.jpg", "/1000x1000bb.jpg").replace("/100x100bb.png", "/1000x1000bb.png")
    release_date = str(collection.get("releaseDate") or "")[:10]
    genre = collection.get("primaryGenreName") or "Music"

    tracks = []
    total_duration = 0
    for idx, t in enumerate(tracks_data, start=1):
        dur = (t.get("trackTimeMillis") or 0) // 1000
        total_duration += dur
        tracks.append({
            "track_num": t.get("trackNumber") or idx,
            "disc_num": t.get("discNumber", 1),
            "title": t.get("trackName") or f"Track {idx}",
            "artist": t.get("artistName") or artist,
            "duration": dur,
            "explicit": t.get("trackExplicitness") == "explicit",
            "preview_url": t.get("previewUrl") or "",
            "id": str(t.get("trackId") or idx),
        })

    return {
        "id": f"apple:{raw_id}",
        "title": title,
        "artist": artist,
        "artist_id": "",
        "artist_picture": "",
        "cover": cover,
        "release_date": release_date,
        "year": release_date[:4] if release_date else "",
        "genre": genre,
        "record_type": "Album",
        "tracks_count": len(tracks),
        "duration": total_duration,
        "fans": 0,
        "label": collection.get("copyright", ""),
        "upc": "",
        "tracks": tracks
    }
