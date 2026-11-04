"""Apple Music / iTunes API Integration.
Provides authoritative official studio discographies, clean release classifications,
and ultra high-resolution album artwork (1400x1400) with zero API keys required.
"""
import re
import urllib.parse
from typing import List, Dict, Any, Optional
from ..utils.http_client import fetch_json
from core.logger import get_logger

_log = get_logger("itunes")

_BASE_URL = "https://itunes.apple.com/search"
_itunes_cooldown_until = 0.0

def _is_cooling_down() -> bool:
    import time
    return time.time() < _itunes_cooldown_until

def _set_cooldown(seconds: int = 300):
    global _itunes_cooldown_until
    import time
    _itunes_cooldown_until = time.time() + seconds


def _clean_artwork_url(url: str, size: int = 1400) -> str:
    """Transform low-res thumbnail URL into pristine high-resolution artwork."""
    if not url:
        return ""
    # iTunes artwork URLs end with e.g. /100x100bb.jpg or /60x60bb.jpg
    cleaned = re.sub(r"/\d+x\d+bb\.jpg$", f"/{size}x{size}bb.jpg", url)
    return cleaned


def _categorize_itunes_release(item: dict) -> str:
    """Categorize an iTunes release with high precision."""
    title = (item.get("collectionName") or "").strip().lower()
    genre = (item.get("primaryGenreName") or "").strip().lower()
    track_count = int(item.get("trackCount") or 1)

    if "soundtrack" in genre or "motion picture" in title or "original soundtrack" in title or " ost" in title:
        return "Soundtracks"
    if "live" in title or "in concert" in title or "recorded live" in title:
        return "Live Albums"
    if "remix" in title or "remixes" in title:
        return "Remixes"
    if "greatest hits" in title or "best of" in title or "anthology" in title or "essentials" in title or "the collection" in title:
        return "Compilations"
    if title.endswith(" - ep") or " ep" in title or (3 <= track_count <= 5 and not title.endswith(" - single")):
        return "EPs"
    if title.endswith(" - single") or track_count <= 2:
        return "Singles"
    return "Studio Albums"


def _clean_release_title(title: str) -> str:
    """Clean promotional suffixes from collection title while preserving edition names."""
    if not title:
        return ""
    # Strip trailing " - Single", " - EP"
    cleaned = re.sub(r"\s+-\s+(Single|EP)$", "", title, flags=re.IGNORECASE).strip()
    return cleaned


def lookup_by_upc(upc: str) -> Optional[Dict[str, Any]]:
    """Lookup an album on iTunes / Apple Music by physical commercial barcode (UPC).
    Returns verified collection ID, clean title, artist, and uncompressed 1400x1400 artwork.
    """
    # Guardrail: UPC barcodes are strictly numeric digits (6 to 14 digits)
    raw_upc = re.sub(r"[^\d]", "", str(upc or "").strip())
    if not raw_upc or len(raw_upc) < 6:
        return None

    # Test exact UPC first, then stripped leading zeros if needed
    candidates = [raw_upc]
    stripped = raw_upc.lstrip("0")
    if stripped and stripped != raw_upc:
        candidates.append(stripped)

    for candidate in candidates:
        url = f"https://itunes.apple.com/lookup?upc={urllib.parse.quote(candidate)}&entity=album"
        try:
            data = fetch_json(url, cache_ttl=86400 * 7, namespace="itunes_upc")
            if data and data.get("results"):
                item = data["results"][0]
                raw_title = item.get("collectionName") or "Unknown Album"
                cat = _categorize_itunes_release(item)
                cover_1400 = _clean_artwork_url(item.get("artworkUrl100") or "", size=1400)
                year = str(item.get("releaseDate") or "")[:4]
                return {
                    "itunes_id": str(item.get("collectionId") or ""),
                    "title": _clean_release_title(raw_title),
                    "artist": item.get("artistName") or "Unknown Artist",
                    "artwork_url": cover_1400,
                    "category": cat,
                    "tracks_count": int(item.get("trackCount") or 0),
                    "year": year,
                    "genre": item.get("primaryGenreName") or "",
                    "upc": raw_upc
                }
        except Exception as exc:
            _log.debug("iTunes UPC lookup error for %s: %s", candidate, exc)
    return None


def search_artist_albums(artist_name: str, limit: int = 60) -> List[Dict[str, Any]]:
    if _is_cooling_down():
        return []
    """Fetch verified official discography for an artist from Apple Music catalog."""
    if not artist_name or not artist_name.strip():
        return []

    clean_name = artist_name.strip()
    params = {
        "term": clean_name,
        "entity": "album",
        "attribute": "artistTerm",
        "limit": min(limit, 100),
    }
    url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"

    try:
        data = fetch_json(url, cache_ttl=86400, namespace="itunes_discography")  # 24h cache
        if not data or "results" not in data:
            return []

        albums = []
        name_lower = clean_name.lower().replace("the ", "").strip()

        for item in data.get("results", []):
            item_artist = (item.get("artistName") or "").strip()
            item_artist_clean = item_artist.lower().replace("the ", "").strip()

            # Strict artist match check so random third-party tributes/features are excluded
            if name_lower not in item_artist_clean and item_artist_clean not in name_lower:
                continue

            raw_title = item.get("collectionName") or "Unknown Album"
            cat = _categorize_itunes_release(item)
            year = str(item.get("releaseDate") or "")[:4]
            cover = _clean_artwork_url(item.get("artworkUrl100") or "")
            tracks_count = int(item.get("trackCount") or 0)
            genre = item.get("primaryGenreName") or ""
            itunes_id = item.get("collectionId")

            album = {
                "id": f"it_{itunes_id}",
                "itunes_id": itunes_id,
                "title": _clean_release_title(raw_title),
                "artist": item_artist,
                "year": year,
                "genre": genre,
                "cover": cover,
                "category": cat,
                "record_type": cat[:-1] if cat.endswith("s") else cat,
                "tracks_count": tracks_count,
                "copyright": item.get("copyright") or "",
                "source": "apple_music"
            }
            albums.append(album)

        return albums
    except Exception as exc:
        _set_cooldown(600)
        _log.debug("iTunes cooling down for %s: %s", artist_name, exc)
        return []


def search_albums(query: str, limit: int = 30) -> List[Dict[str, Any]]:
    """Search for specific albums across the Apple Music catalog."""
    if not query or not query.strip():
        return []

    params = {
        "term": query.strip(),
        "entity": "album",
        "limit": min(limit, 50),
    }
    url = f"{_BASE_URL}?{urllib.parse.urlencode(params)}"

    try:
        data = fetch_json(url, cache_ttl=86400, namespace="itunes_albums")
        if not data or "results" not in data:
            return []

        albums = []
        for item in data.get("results", []):
            raw_title = item.get("collectionName") or "Unknown Album"
            cat = _categorize_itunes_release(item)
            year = str(item.get("releaseDate") or "")[:4]
            cover = _clean_artwork_url(item.get("artworkUrl100") or "")
            tracks_count = int(item.get("trackCount") or 0)
            itunes_id = item.get("collectionId")

            album = {
                "id": f"it_{itunes_id}",
                "itunes_id": itunes_id,
                "title": _clean_release_title(raw_title),
                "artist": item.get("artistName") or "Unknown Artist",
                "year": year,
                "genre": item.get("primaryGenreName") or "",
                "cover": cover,
                "category": cat,
                "record_type": cat[:-1] if cat.endswith("s") else cat,
                "tracks_count": tracks_count,
                "copyright": item.get("copyright") or "",
                "source": "apple_music"
            }
            albums.append(album)

        return albums
    except Exception as exc:
        _log.warning("Failed to search iTunes albums for '%s': %s", query, exc)
        return []


def lookup_album_tracks(collection_id: Any) -> Optional[Dict[str, Any]]:
    """Look up an album's complete official tracklist by iTunes Collection ID."""
    cid = str(collection_id).replace("it_", "").strip()
    if not cid or not cid.isdigit():
        return None

    url = f"https://itunes.apple.com/lookup?id={cid}&entity=song&limit=200"
    try:
        data = fetch_json(url, cache_ttl=86400, namespace="itunes_tracks")
        if not data or not data.get("results"):
            return None

        results = data["results"]
        album_meta = next((r for r in results if r.get("wrapperType") == "collection"), {})
        tracks_raw = [r for r in results if r.get("wrapperType") == "track"]

        tracks = []
        for t in tracks_raw:
            tracks.append({
                "id": f"it_trk_{t.get('trackId')}",
                "title": t.get("trackName") or "Unknown Track",
                "artist": t.get("artistName") or album_meta.get("artistName") or "Unknown Artist",
                "duration": int((t.get("trackTimeMillis") or 0) / 1000),
                "track_position": int(t.get("trackNumber") or len(tracks) + 1),
                "preview": t.get("previewUrl") or "",
            })

        year = str(album_meta.get("releaseDate") or "")[:4]
        cover = _clean_artwork_url(album_meta.get("artworkUrl100") or "")

        return {
            "id": f"it_{cid}",
            "title": _clean_release_title(album_meta.get("collectionName") or ""),
            "artist": album_meta.get("artistName") or "",
            "year": year,
            "genre": album_meta.get("primaryGenreName") or "",
            "cover": cover,
            "tracks": tracks,
            "tracks_count": len(tracks),
            "label": album_meta.get("copyright") or "",
            "category": _categorize_itunes_release(album_meta)
        }
    except Exception as exc:
        _log.warning("Failed to lookup iTunes album %s: %s", cid, exc)
        return None


def search_tracks(query: str, limit: int = 15) -> list[dict]:
    """Search for individual tracks on Apple Music / iTunes."""
    clean_q = (query or "").strip()
    if not clean_q or _is_cooling_down():
        return []

    url = f"{_BASE_URL}?term={urllib.parse.quote(clean_q)}&entity=song&limit={limit}"
    try:
        data = fetch_json(url, cache_ttl=3600, namespace="itunes_song_search")
        if not data or not data.get("results"):
            return []

        results = []
        for r in data["results"]:
            dur_ms = int(r.get("trackTimeMillis") or 0)
            results.append({
                "id": str(r.get("trackId") or ""),
                "title": r.get("trackName") or "Unknown",
                "artist": r.get("artistName") or "Unknown",
                "album": r.get("collectionName") or "",
                "duration": int(dur_ms / 1000),
                "cover": _clean_artwork_url(r.get("artworkUrl100") or "", size=1000),
                "preview": r.get("previewUrl") or "",
                "source": "apple"
            })
        return results
    except Exception as exc:
        _log.warning("Failed to search iTunes tracks: %s", exc)
        return []
