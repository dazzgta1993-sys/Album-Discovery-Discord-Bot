"""Spotify Zero-Credential URL Resolution Service.
Resolves Spotify tracks, albums, and playlists into canonical studio tracks with zero API keys.
"""
import json
import logging
import re
import urllib.request
from typing import Optional

_log = logging.getLogger("spotify")

SPOTIFY_URL_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:open\.)?spotify\.com\/(track|album|playlist)\/([a-zA-Z0-9]+)",
    re.IGNORECASE
)


def match_spotify_url(url: str) -> Optional[tuple[str, str]]:
    """Returns (entity_type, entity_id) if url matches Spotify pattern."""
    if not url:
        return None
    m = SPOTIFY_URL_REGEX.search(url.strip())
    if m:
        return m.group(1).lower(), m.group(2)
    return None


def fetch_spotify_entity(entity_type: str, entity_id: str) -> Optional[dict]:
    """Fetches public embed metadata for a Spotify track, album, or playlist."""
    embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
    req = urllib.request.Request(
        embed_url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        _log.warning(f"Error fetching Spotify embed for {entity_type}/{entity_id}: {e}")
        return None

    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
    if not match:
        return None

    try:
        data = json.loads(match.group(1))
        entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
        if not entity:
            return None

        # Extract Cover Art
        cover = ""
        images = entity.get("visualIdentity", {}).get("image", [])
        if images and isinstance(images, list):
            cover = images[0].get("url") or ""

        # Track single
        if entity_type == "track":
            artists_list = entity.get("artists", [])
            artist_name = artists_list[0].get("name", "Unknown Artist") if artists_list else "Unknown Artist"
            dur_ms = entity.get("duration", 0)
            dur_secs = int(dur_ms / 1000) if dur_ms else 0
            title = entity.get("name") or entity.get("title") or "Unknown Title"

            return {
                "type": "track",
                "name": title,
                "artist": artist_name,
                "cover": cover,
                "tracks": [{
                    "title": title,
                    "artist": artist_name,
                    "album": entity.get("album", {}).get("name", ""),
                    "duration_seconds": dur_secs,
                    "cover": cover
                }]
            }

        # Album or Playlist
        elif entity_type in ("album", "playlist"):
            name = entity.get("name") or entity.get("title") or "Spotify Collection"
            raw_tracks = entity.get("trackList", [])
            tracks = []

            for t in raw_tracks:
                dur_ms = t.get("duration", 0)
                dur_secs = int(dur_ms / 1000) if dur_ms else 0
                t_title = t.get("title") or "Unknown"
                t_artist = t.get("subtitle") or "Unknown Artist"
                tracks.append({
                    "title": t_title,
                    "artist": t_artist,
                    "album": name if entity_type == "album" else "",
                    "duration_seconds": dur_secs,
                    "cover": cover
                })

            return {
                "type": entity_type,
                "name": name,
                "artist": entity.get("subtitle") or "Various Artists",
                "cover": cover,
                "track_count": len(tracks),
                "tracks": tracks
            }

    except Exception as e:
        _log.warning(f"Error parsing Spotify JSON for {entity_type}/{entity_id}: {e}")
        return None

    return None
