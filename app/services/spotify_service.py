"""Spotify Zero-Credential URL Resolution Service.
Resolves Spotify tracks, albums, and playlists into canonical studio tracks with zero API keys.
Includes __NEXT_DATA__, initial-state, meta tags, and official oEmbed + Deezer/iTunes enrichment fallbacks.
"""
import html as html_lib
import json
import logging
import re
import urllib.parse
import urllib.request
from typing import Optional

_log = logging.getLogger("spotify")

SPOTIFY_URL_REGEX = re.compile(
    r"(?:https?:\/\/)?(?:open\.)?spotify\.com\/(?:intl-[a-z]{2}\/)?(track|album|playlist)\/([a-zA-Z0-9]+)",
    re.IGNORECASE
)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def match_spotify_url(url: str) -> Optional[tuple[str, str]]:
    """Returns (entity_type, entity_id) if url matches Spotify pattern."""
    if not url:
        return None
    m = SPOTIFY_URL_REGEX.search(url.strip())
    if m:
        return m.group(1).lower(), m.group(2)
    return None


def _enrich_single_track(title: str, artist: str, cover: str = "") -> dict:
    """Enrich a resolved Spotify track with canonical duration, album, and cover from Deezer/iTunes."""
    clean_title = (title or "").strip()
    clean_artist = (artist or "").strip()
    dur_secs = 0
    album_name = ""
    best_cover = cover

    try:
        from . import deezer_api
        q = f"{clean_artist} {clean_title}".strip()
        dz_tracks = deezer_api.search_tracks(q, limit=3)
        if dz_tracks:
            top = dz_tracks[0]
            if not clean_artist or clean_artist == "Unknown Artist":
                clean_artist = top.get("artist") or clean_artist
            dur_secs = int(top.get("duration") or 0)
            album_name = top.get("album") or ""
            best_cover = top.get("cover_xl") or top.get("cover_big") or top.get("cover") or best_cover
    except Exception:
        pass

    return {
        "type": "track",
        "name": clean_title or "Unknown Title",
        "artist": clean_artist or "Unknown Artist",
        "cover": best_cover,
        "tracks": [{
            "title": clean_title or "Unknown Title",
            "artist": clean_artist or "Unknown Artist",
            "album": album_name,
            "duration_seconds": dur_secs,
            "cover": best_cover
        }]
    }


def _fallback_oembed_and_meta(entity_type: str, entity_id: str, embed_html: str = "") -> Optional[dict]:
    """Zero-key fallback using Spotify official oEmbed endpoint and page OpenGraph tags."""
    title = ""
    artist = ""
    cover = ""

    # 1. Try OpenGraph / meta tags from already-fetched HTML or main page
    for page_html in ([embed_html] if embed_html else []):
        t_m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']+)["\']', page_html, re.I)
        d_m = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^"\']+)["\']', page_html, re.I)
        i_m = re.search(r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']', page_html, re.I)
        if t_m:
            title = html_lib.unescape(t_m.group(1)).strip()
        if i_m:
            cover = i_m.group(1).strip()
        if d_m:
            desc = html_lib.unescape(d_m.group(1)).strip()
            parts = [p.strip() for p in re.split(r"·|\bull\b|-", desc) if p.strip()]
            if parts:
                artist = parts[0].replace("Song by ", "").strip()

    # 2. Try official zero-key Spotify oEmbed API
    if not title:
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/{entity_type}/{entity_id}"
        try:
            req = urllib.request.Request(oembed_url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=8) as resp:
                odata = json.loads(resp.read().decode("utf-8"))
                raw_title = (odata.get("title") or "").strip()
                cover = odata.get("thumbnail_url") or cover
                if " - " in raw_title:
                    p1, p2 = raw_title.split(" - ", 1)
                    title, artist = p1.strip(), p2.strip()
                else:
                    title = raw_title
        except Exception as e:
            _log.debug(f"Spotify oEmbed fallback notice: {e}")

    if title and entity_type == "track":
        return _enrich_single_track(title, artist, cover)
    return None


def fetch_spotify_entity(entity_type: str, entity_id: str) -> Optional[dict]:
    """Fetches public embed metadata for a Spotify track, album, or playlist."""
    embed_url = f"https://open.spotify.com/embed/{entity_type}/{entity_id}"
    req = urllib.request.Request(embed_url, headers={"User-Agent": _UA})
    html = ""
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
    except Exception as e:
        _log.warning(f"Error fetching Spotify embed for {entity_type}/{entity_id}: {e}")
        return _fallback_oembed_and_meta(entity_type, entity_id)

    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html)
    if not match:
        return _fallback_oembed_and_meta(entity_type, entity_id, html)

    try:
        data = json.loads(match.group(1))
        entity = data.get("props", {}).get("pageProps", {}).get("state", {}).get("data", {}).get("entity", {})
        if not entity:
            return _fallback_oembed_and_meta(entity_type, entity_id, html)

        cover = ""
        images = entity.get("visualIdentity", {}).get("image", [])
        if images and isinstance(images, list):
            cover = images[0].get("url") or ""

        if entity_type == "track":
            artists_list = entity.get("artists", [])
            artist_name = ", ".join(a.get("name", "") for a in artists_list if a.get("name")) or "Unknown Artist"
            dur_ms = entity.get("duration", 0)
            dur_secs = int(dur_ms / 1000) if dur_ms else 0
            title = entity.get("name") or entity.get("title") or "Unknown Title"
            if dur_secs <= 0:
                return _enrich_single_track(title, artist_name, cover)

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

        elif entity_type in ("album", "playlist"):
            name = entity.get("name") or entity.get("title") or "Spotify Collection"
            raw_tracks = entity.get("trackList", [])
            tracks = []
            for t in raw_tracks:
                dur_ms = t.get("duration", 0)
                dur_secs = int(dur_ms / 1000) if dur_ms else 0
                tracks.append({
                    "title": t.get("title") or "Unknown",
                    "artist": t.get("subtitle") or "Unknown Artist",
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
        return _fallback_oembed_and_meta(entity_type, entity_id, html)

    return _fallback_oembed_and_meta(entity_type, entity_id, html)

