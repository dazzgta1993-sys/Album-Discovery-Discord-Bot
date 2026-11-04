"""YouTube Music Studio Audio Resolution and Direct Stream Proxy Service.
Provides full-length studio track playback with zero-gap prewarming and byte-range streaming.
"""
import json
import os
import re
import threading
import time
import urllib.request
from typing import Optional, Tuple
from core.config import load_bot_config

from .stream_filters import (
    _JUNK_TITLE_REGEX, _JUNK_CHANNEL_REGEX, _DOT_OBFUSCATED_REGEX, _is_junk_video,
    _BRACKETED_MODIFIERS, _ATTRIBUTION_PATTERNS, BAD_CHANNEL_PATTERNS,
    _clean_target_title, _parse_duration_seconds
)

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_PATH = os.path.join(_ROOT_DIR, "config.json")

def _prune_cache_if_needed(cache: dict, max_size: int = 1500):
    if len(cache) > max_size:
        keys_to_remove = list(cache.keys())[:max_size // 4]
        for k in keys_to_remove:
            cache.pop(k, None)

# In-memory caches
_STREAM_URL_CACHE: dict[str, tuple[str, dict, float]] = {}  # video_id -> (url, headers, timestamp)
_STREAM_METADATA_CACHE: dict[str, dict] = {}  # video_id -> {title, artist, duration, thumbnail}
_TRACK_RESOLUTION_CACHE: dict[str, tuple[dict, float]] = {}  # query_key -> (result_dict, timestamp)

_ytmusic_client = None
_ytmusic_lock = threading.Lock()

def _get_ytmusic():
    """Lazy initialize singleton YTMusic client."""
    global _ytmusic_client
    if _ytmusic_client is None:
        with _ytmusic_lock:
            if _ytmusic_client is None:
                try:
                    from ytmusicapi import YTMusic
                    _ytmusic_client = YTMusic()
                except Exception as exc:
                    pass
    return _ytmusic_client

def _is_unwanted_variant(cand_title: str, target_title: str, channel: str = "") -> bool:
    """Strict Title & Channel Filtering with Title-Collision Protection.
    Rejects karaoke, tribute, covers, and UGC modifiers when appended in brackets,
    suffixes, or attribution phrases, while safely protecting authentic tracks
    whose legitimate names contain these words (e.g. 'Cover Me' by Springsteen, 'Tribute' by Tenacious D).
    """
    t_cand = (cand_title or "").lower()
    t_target = (target_title or "").lower()
    t_chan = (channel or "").lower()

    # 1. Immediate rejection of dedicated cover/karaoke/tribute channels
    for bad_ch in BAD_CHANNEL_PATTERNS:
        if bad_ch in t_chan and bad_ch not in t_target:
            return True

    # 2. Check for explicit attribution phrases (e.g. "Originally Performed by...", "In the Style of...")
    for phrase in _ATTRIBUTION_PATTERNS:
        if phrase in t_cand and phrase not in t_target:
            return True

    # 3. Structural Modifier Check: Detect modifiers in parentheses or brackets (e.g. '(Cover)', '[Karaoke]')
    # Compares against canonical target brackets (case-insensitive) to protect songs like "Cover Me" or "Tribute"
    bracketed_content = re.findall(r"[\(\[](.*?)[\)\]]", t_cand)
    target_brackets = re.findall(r"[\(\[](.*?)[\)\]]", t_target)
    target_brackets_lower = {tb.strip().lower() for tb in target_brackets}
    for b in bracketed_content:
        b_clean = b.strip()
        if b_clean.lower() not in target_brackets_lower:
            for mod in _BRACKETED_MODIFIERS:
                if re.search(r"\b" + re.escape(mod) + r"\b", b_clean, re.IGNORECASE):
                    return True

    # 4. Delimiter Check: Detect unbracketed modifiers following hyphens, slashes, or pipes (e.g. 'Artist - Cover Me - Acoustic Cover')
    # Uses re.finditer to inspect every delimiter without short-circuiting on the first legitimate keyword
    post_delimiter_pattern = r"(?:[-|/]\s*)(?:.*?\b)(" + "|".join(re.escape(m) for m in _BRACKETED_MODIFIERS) + r")\b"
    target_lower = t_target.lower()
    for match in re.finditer(post_delimiter_pattern, t_cand, re.IGNORECASE):
        mod_found = match.group(1).lower()
        if mod_found not in target_lower:
            return True

    return False

def _is_duration_valid(cand_dur_secs: int, expected_dur_secs: int, tolerance_secs: int = 5, allow_zero: bool = False) -> bool:
    """Strict Duration Tolerance Guardrail (±5 Seconds): Real studio cuts match
    canonical metadata length within 2-5 seconds. If delta > 5 seconds, discard the candidate.
    """
    if expected_dur_secs <= 0:
        return True
    if cand_dur_secs <= 0:
        return allow_zero
    return abs(cand_dur_secs - expected_dur_secs) <= tolerance_secs

def _is_artist_match(cand: dict, target_artist: str) -> bool:
    """Ensure candidate matches target artist or uploader channel matches '{Artist} - Topic' / verified channel."""
    t_art = (target_artist or "").lower().strip()
    norm_t = re.sub(r"[^\w\s]", "", t_art).strip()
    if not norm_t:
        return True

    ch = (cand.get("channel") or "").lower().strip()
    norm_ch = re.sub(r"[^\w\s]", "", ch).strip()

    # Reject known bootleg/karaoke channels immediately
    for bad_ch in BAD_CHANNEL_PATTERNS:
        if bad_ch in ch or bad_ch in norm_ch:
            return False

    # 1. Primary artist from structured metadata
    cand_artists = [a.lower().strip() for a in cand.get("artists", []) if a]
    if cand_artists:
        primary_a = re.sub(r"[^\w\s]", "", cand_artists[0]).strip()
        if primary_a == norm_t or norm_t in primary_a or primary_a in norm_t:
            return True

    # 2. Channel / uploader / author
    if norm_ch and (norm_t in norm_ch or norm_ch in norm_t):
        return True

    # 3. Topic channel convention (e.g. "Drake - Topic")
    if f"{t_art} - topic" in ch or f"{norm_t} topic" in norm_ch or "topic" in ch:
        if norm_t in norm_ch or norm_ch in norm_t:
            return True

    # 4. Candidate title fallback (e.g. "Drake - One Dance")
    # STRICT GUARD: If candidate is UGC (User Generated Content) from an unrelated channel,
    # reject it to prevent amateur fan uploads from masquerading as official tracks.
    if cand.get("videoType") == "MUSIC_VIDEO_TYPE_UGC":
        return False

    cand_title = (cand.get("title") or "").lower()
    norm_cand_title = re.sub(r"[^\w\s]", "", cand_title).strip()
    if any(phrase in cand_title for phrase in ("originally performed", "in the style of", "originally by", "made famous by", "tribute to", "feat. " + t_art, "ft. " + t_art, "feat " + t_art)):
        return False
    if re.match(r"^" + re.escape(t_art) + r"\s*[-–—:]", cand_title) or re.match(r"^" + re.escape(norm_t) + r"\s*[-–—:]", norm_cand_title):
        return True

    return False

def _is_title_match(cand_title: str, target_title: str) -> bool:
    """Ensure candidate title contains the essential tokens of the target track title."""
    clean_target = _clean_target_title(target_title).lower()
    target_words = [w for w in re.split(r"[^\w]+", clean_target) if len(w) > 1 and w not in ("the", "and", "feat", "featuring", "ft")]
    if not target_words:
        target_words = [w for w in re.split(r"[^\w]+", clean_target) if w]
    if not target_words:
        return True

    clean_cand = (cand_title or "").lower()
    cand_words = set(re.split(r"[^\w]+", clean_cand))
    matched_words = [w for w in target_words if w in cand_words]
    if len(target_words) <= 2:
        return len(matched_words) == len(target_words)
    return len(matched_words) / len(target_words) >= 0.6

def _fetch_yt_music_innertube(query: str) -> list[dict]:
    """Fallback: Search YouTube Music InnerTube directly for official studio tracks."""
    url = "https://music.youtube.com/youtubei/v1/search"
    body = {"context": {"client": {"clientName": "WEB_REMIX", "clientVersion": "1.20231211.01.00", "hl": "en", "gl": "US"}}, "query": query}
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    items = []
    seen = set()
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))

            def _walk(node):
                if isinstance(node, dict):
                    if "musicResponsiveListItemRenderer" in node:
                        item = node["musicResponsiveListItemRenderer"]
                        flex_cols = item.get("flexColumns", [])
                        vid = ""
                        title = ""
                        channel = ""
                        duration = ""

                        if flex_cols:
                            col0 = flex_cols[0].get("musicResponsiveListItemFlexColumnRenderer", {})
                            runs0 = col0.get("text", {}).get("runs", [])
                            if runs0:
                                title = runs0[0].get("text", "")
                                nav = runs0[0].get("navigationEndpoint", {})
                                vid = nav.get("watchEndpoint", {}).get("videoId", "")

                        if len(flex_cols) > 1:
                            col1 = flex_cols[1].get("musicResponsiveListItemFlexColumnRenderer", {})
                            runs1 = col1.get("text", {}).get("runs", [])
                            if runs1:
                                channel = runs1[0].get("text", "")
                                if len(runs1) > 2:
                                    for r in runs1:
                                        t_val = r.get("text", "")
                                        if re.match(r"^\d+:\d+$", t_val):
                                            duration = t_val
                                            break

                        if not vid:
                            overlay = item.get("overlay", {}).get("musicItemThumbnailOverlayRenderer", {})
                            play_nav = overlay.get("content", {}).get("musicPlayButtonRenderer", {}).get("playNavigationEndpoint", {})
                            vid = play_nav.get("watchEndpoint", {}).get("videoId", "")

                        if vid and title and vid not in seen:
                            seen.add(vid)
                            items.append({
                                "id": vid,
                                "title": title,
                                "artists": [channel] if channel else [],
                                "channel": channel,
                                "album": "",
                                "duration": duration,
                                "duration_seconds": _parse_duration_seconds(duration),
                                "videoType": "MUSIC_VIDEO_TYPE_ATV" if "topic" in channel.lower() else "",
                                "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                            })
                    for v in node.values():
                        _walk(v)
                elif isinstance(node, list):
                    for elem in node:
                        _walk(elem)

            _walk(data)
    except Exception:
        pass
    return items

def _search_ytmusic_songs(query: str, filter_songs: bool = True) -> list[dict]:
    """Search YouTube Music catalog for songs/audio tracks."""
    items = []
    ytm = _get_ytmusic()
    if ytm:
        try:
            raw_res = ytm.search(query, filter="songs" if filter_songs else None)
            for r in (raw_res or []):
                vid = r.get("videoId")
                if not vid:
                    continue
                art_names = [a.get("name", "") for a in r.get("artists", []) if a.get("name")]
                ch = art_names[0] if art_names else ""
                alb_obj = r.get("album") or {}
                alb_name = alb_obj.get("name", "") if isinstance(alb_obj, dict) else ""
                dur_secs = r.get("duration_seconds") or 0
                dur_str = r.get("duration") or ""
                if not dur_secs and dur_str:
                    dur_secs = _parse_duration_seconds(dur_str)

                thumb = f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
                if r.get("thumbnails"):
                    thumb = r["thumbnails"][-1].get("url") or thumb

                items.append({
                    "id": vid,
                    "title": r.get("title", ""),
                    "artists": art_names,
                    "channel": ch,
                    "album": alb_name,
                    "duration": dur_str,
                    "duration_seconds": dur_secs,
                    "videoType": r.get("videoType") or "",
                    "thumbnail": thumb,
                })
        except Exception:
            pass

    if not items and filter_songs:
        items = _fetch_yt_music_innertube(query)

    return items

def search_youtube_tracks(query: str, limit: int = 6) -> list[dict]:
    """Search YouTube / YouTube Music for tracks, remixes, bootlegs, and live versions."""
    q = (query or "").strip()
    if not q:
        return []

    items = []
    # 1. Search YouTube Music songs
    try:
        raw_items = _search_ytmusic_songs(q, filter_songs=False)
        for r in raw_items:
            vid = r.get("id")
            title = r.get("title")
            if not vid or not title:
                continue
            items.append({
                "id": f"yt_{vid}",
                "video_id": vid,
                "title": title,
                "artist": r.get("channel") or (r.get("artists")[0] if r.get("artists") else "YouTube"),
                "album": r.get("album") or "YouTube Music",
                "cover": r.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                "duration": r.get("duration_seconds") or 0,
                "source": "youtube",
            })
            if len(items) >= limit:
                break
    except Exception as exc:
        _log.debug("YTMusic track search notice: %s", exc)

    # 2. If no items or remix search with few items, search via yt_dlp flat extraction
    if len(items) < 3:
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "skip_download": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                res = ydl.extract_info(f"ytsearch{limit}:{q}", download=False)
                for entry in (res.get("entries") or []):
                    vid = entry.get("id")
                    title = entry.get("title")
                    if not vid or not title:
                        continue
                    if any(it.get("video_id") == vid for it in items):
                        continue
                    thumb = (
                        entry.get("thumbnail")
                        or (entry.get("thumbnails")[-1].get("url") if entry.get("thumbnails") else "")
                        or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
                    )
                    items.append({
                        "id": f"yt_{vid}",
                        "video_id": vid,
                        "title": title,
                        "artist": entry.get("uploader") or entry.get("channel") or "YouTube",
                        "album": "YouTube Audio",
                        "cover": thumb,
                        "duration": int(entry.get("duration") or 0),
                        "source": "youtube",
                    })
                    if len(items) >= limit:
                        break
        except Exception as exc:
            _log.debug("yt_dlp search notice: %s", exc)

    return items[:limit]

def get_ytmusic_related_tracks(video_id: str = "", query: str = "", limit: int = 25) -> list[dict]:
    """Fetch algorithmic Up Next / Radio recommendation tracks directly from YouTube Music."""
    yt = _get_ytmusic()
    if not yt:
        return []
    vid = str(video_id or "").strip()
    if not vid and query:
        songs = _search_ytmusic_songs(query, filter_songs=True)
        if songs:
            vid = songs[0].get("id") or ""
    if not vid:
        return []

    from ..utils.normalizer import clean_title_clutter
    results = []
    try:
        data = yt.get_watch_playlist(videoId=vid, limit=limit)
        raw_tracks = data.get("tracks", []) if data else []
        for t in raw_tracks:
            t_vid = t.get("videoId")
            title = t.get("title") or ""
            if not t_vid or not title or t_vid == vid:
                continue
            artists = [a.get("name") for a in t.get("artists", [])]
            art_str = ", ".join(artists) if artists else "Unknown Artist"
            dur_raw = t.get("length", "0:00")
            dur_secs = 0
            parts = str(dur_raw).split(":")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                dur_secs = int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
                dur_secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])

            clean_t = clean_title_clutter(title)
            thumbs = t.get("thumbnail", [])
            cov = thumbs[-1].get("url", "") if isinstance(thumbs, list) and thumbs else ""
            results.append({
                "id": f"yt_{t_vid}",
                "video_id": t_vid,
                "title": clean_t,
                "artist": art_str,
                "album": t.get("album", {}).get("name", "") if isinstance(t.get("album"), dict) else "",
                "duration_seconds": dur_secs,
                "cover": cov or f"https://i.ytimg.com/vi/{t_vid}/hqdefault.jpg",
                "source": "ytmusic",
                "is_official": True
            })
            if len(results) >= limit:
                break
    except Exception as exc:
        _log.debug("get_ytmusic_related_tracks notice: %s", exc)

    return results


def search_ytmusic_catalog(query: str, limit: int = 12) -> list[dict]:
    """Search YouTube Music official catalog exclusively for studio audio tracks.
    Filters out music videos, live concerts, fan uploads, and audio clutter.
    """
    q = (query or "").strip()
    if not q:
        return []

    from ..utils.normalizer import clean_title_clutter

    items = _search_ytmusic_songs(q, filter_songs=True)
    results = []
    seen_ids = set()

    for it in items:
        vid = it.get("id")
        title = it.get("title") or ""
        if not vid or not title or vid in seen_ids:
            continue
        seen_ids.add(vid)

        ch = it.get("channel") or (it.get("artists")[0] if it.get("artists") else "")
        if _is_junk_video(it) or _is_unwanted_variant(title, q, ch):
            continue

        clean_t = clean_title_clutter(title)
        dur_secs = it.get("duration_seconds") or 0
        m, s = divmod(int(dur_secs), 60)
        formatted_dur = f"{m}:{s:02d}"

        results.append({
            "id": f"yt_{vid}",
            "video_id": vid,
            "title": clean_t,
            "artist": ch or "Official Artist",
            "album": it.get("album") or "Studio Audio",
            "duration": formatted_dur,
            "duration_seconds": dur_secs,
            "cover": it.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "source": "ytmusic",
            "is_official": it.get("videoType") == "MUSIC_VIDEO_TYPE_ATV" or "topic" in ch.lower(),
        })
        if len(results) >= limit:
            break

    return results

def search_soundcloud_tracks(query: str, limit: int = 12) -> list[dict]:
    """Search SoundCloud catalog for underground tracks, remixes, and DJ sets."""
    q = (query or "").strip()
    if not q:
        return []

    items = []
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            res = ydl.extract_info(f"scsearch{limit}:{q}", download=False)
            for entry in (res.get("entries") or []):
                title = entry.get("title")
                uploader = entry.get("uploader") or entry.get("artist") or "SoundCloud"
                dur = int(entry.get("duration") or 0)
                web_url = entry.get("webpage_url") or entry.get("url") or ""
                thumb = ""
                if entry.get("thumbnails"):
                    thumb = entry["thumbnails"][-1].get("url") or ""

                m, s = divmod(dur, 60)
                items.append({
                    "id": f"sc_{entry.get('id')}",
                    "video_id": web_url,
                    "title": title or "SoundCloud Track",
                    "artist": uploader,
                    "album": "SoundCloud",
                    "duration": f"{m}:{s:02d}",
                    "duration_seconds": dur,
                    "cover": thumb or "https://a-v2.sndcdn.com/assets/images/sc-icons/favicon-2cadd14bdb.ico",
                    "url": web_url,
                    "source": "soundcloud"
                })
    except Exception as exc:
        _log.debug("SoundCloud search notice: %s", exc)

    return items[:limit]

def resolve_soundcloud_url(url: str) -> list[dict]:
    """Extract metadata for a SoundCloud track, album, or playlist URL."""
    items = []
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "skip_download": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            entries = info.get("entries") or [info]
            for entry in entries:
                title = entry.get("title")
                uploader = entry.get("uploader") or entry.get("artist") or "SoundCloud"
                dur = int(entry.get("duration") or 0)
                web_url = entry.get("webpage_url") or entry.get("url") or url
                thumb = ""
                if entry.get("thumbnails"):
                    thumb = entry["thumbnails"][-1].get("url") or ""
                m, s = divmod(dur, 60)
                items.append({
                    "id": f"sc_{entry.get('id', 'item')}",
                    "video_id": web_url,
                    "title": title or "SoundCloud Track",
                    "artist": uploader,
                    "album": "SoundCloud",
                    "duration": f"{m}:{s:02d}",
                    "duration_seconds": dur,
                    "cover": thumb or "https://a-v2.sndcdn.com/assets/images/sc-icons/favicon-2cadd14bdb.ico",
                    "url": web_url,
                    "source": "soundcloud"
                })
    except Exception as exc:
        _log.warning(f"Error resolving SoundCloud URL {url}: {exc}")
    return items

def resolve_track_stream(
    artist: str,
    title: str,
    album: str = "",
    duration: int = 0,
    track_id: str = "",
    isrc: str = "",
    force_fresh: bool = False,
    heal: bool = False
) -> dict:
    """Resolve an album track to its official YouTube studio audio video ID with strict
    ISRC priority, duration tolerance guardrail (±5s), and unwanted variant rejection.
    """
    clean_artist = (artist or "").strip()
    clean_title = (title or "").strip()
    clean_album = (album or "").strip()
    clean_core = _clean_target_title(clean_title)
    clean_isrc = (isrc or "").strip().upper()

    cache_key = f"{clean_artist.lower()}:::{clean_title.lower()}:::{clean_album.lower()}"
    now = time.time()

    # Check In-Memory Cache with Guardrail Validation (skipped if healing / fresh requested)
    if not force_fresh and not heal and cache_key in _TRACK_RESOLUTION_CACHE:
        val, ts = _TRACK_RESOLUTION_CACHE[cache_key]
        if now - ts < 86400:  # 24 hour memory cache
            cached_dur = _parse_duration_seconds(val.get("duration", ""))
            # Ensure cached track satisfies duration and variant guardrails
            if (
                _is_duration_valid(cached_dur, duration, tolerance_secs=5)
                and not _is_unwanted_variant(val.get("title", ""), clean_title, val.get("channel", ""))
            ):
                return val

    # Check L2 SQLite Persistent Store with Guardrail Validation (skipped if healing / fresh requested)
    if not force_fresh and not heal:
        try:
            from .. import store
            db_res = store.get_stream_resolution(cache_key)
            if db_res:
                db_dur = _parse_duration_seconds(db_res.get("duration", ""))
                if (
                    _is_duration_valid(db_dur, duration, tolerance_secs=5)
                    and not _is_unwanted_variant(db_res.get("title", ""), clean_title, db_res.get("channel", ""))
                ):
                    _TRACK_RESOLUTION_CACHE[cache_key] = (db_res, now)
                    if db_res.get("id"):
                        prewarm_stream(db_res["id"])
                    return db_res
        except Exception:
            pass

    # Direct YouTube video ID passthrough if discovered via YouTube Music cloud feed
    if track_id and str(track_id).startswith("yt_"):
        vid = str(track_id)[3:].strip()
        if vid:
            res_obj = {
                "id": vid,
                "title": clean_title,
                "artist": clean_artist,
                "album": clean_album,
                "duration": str(duration) if duration else "",
                "match_type": "direct_youtube_cloud"
            }
            _TRACK_RESOLUTION_CACHE[cache_key] = (res_obj, now)
            prewarm_stream(vid)
            return res_obj

    found_candidate = None

    candidates = []
    seen_ids = set()

    def _evaluate_items(items, tolerance_secs: int = 5, match_target: str = None):
        if match_target is None:
            match_target = clean_title
        for item in items:
            vid = item.get("id")
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)

            cdur = item.get("duration_seconds") or 0
            c_title = item.get("title") or ""

            # Guardrail 1: Duration Tolerance Guardrail (require duration when target has duration)
            if not _is_duration_valid(cdur, duration, tolerance_secs=tolerance_secs, allow_zero=(duration <= 0)):
                continue

            # Guardrail 2: Strict Title & Variant Rejection
            if _is_unwanted_variant(c_title, match_target, item.get("channel", "")):
                continue

            # Guardrail 3: Title Matching (Must contain target core words)
            if not _is_title_match(c_title, match_target):
                continue

            # Guardrail 4: Artist & Topic Channel Verification
            if not _is_artist_match(item, clean_artist):
                continue

            # Candidate Scoring
            score = 0
            vtype = item.get("videoType") or ""
            ch_name = (item.get("channel") or "").lower()

            # Heavy penalty for amateur UGC (User Generated Content)
            if vtype == "MUSIC_VIDEO_TYPE_UGC":
                score -= 60

            # Official label studio upload (ATV / Topic channel)
            if vtype == "MUSIC_VIDEO_TYPE_ATV" or "topic" in ch_name:
                score += 50
            elif "vevo" in ch_name:
                score += 35
            elif clean_artist.lower() in ch_name:
                score += 25

            # Exact title match
            norm_c_title = re.sub(r"[^\w\s]", "", c_title.lower()).strip()
            norm_target_core = re.sub(r"[^\w\s]", "", clean_core.lower()).strip()
            if norm_c_title == norm_target_core:
                score += 30
            elif norm_target_core in norm_c_title:
                score += 15

            # Album match
            item_alb = (item.get("album") or "").lower().strip()
            if clean_album and item_alb and clean_album.lower() in item_alb:
                score += 20

            # Duration exactness
            if duration > 0 and cdur > 0:
                diff = abs(cdur - duration)
                if diff <= 1:
                    score += 25
                elif diff <= 3:
                    score += 15
            # Official audio bonus vs lyrics video
            c_low = c_title.lower()
            if "official audio" in c_low or "(audio)" in c_low:
                score += 35
            elif "official" in c_low:
                score += 15
            if "lyrics" in c_low or "lyric video" in c_low:
                score -= 20

            candidates.append((score, item))

    # Pass 1: Direct Clean Studio Queries
    fast_queries = [
        f"{clean_artist} {clean_core}",
        f"{clean_artist} - {clean_core}",
    ]
    if clean_album:
        fast_queries.insert(1, f"{clean_artist} {clean_album} {clean_core}")
    if clean_artist.lower() in ("various artists", "various", "compilation", ""):
        fast_queries.append(clean_core)

    for q_try in fast_queries:
        items = _search_ytmusic_songs(q_try, filter_songs=True)
        _evaluate_items(items)
        if candidates and any(s >= 50 for s, _ in candidates):
            break

    # Pass 2: Specific Quoted Match
    if not candidates:
        quoted_queries = [
            f'"{clean_artist} - {clean_core} (Official Audio)"',
            f'"{clean_artist}" "{clean_core}"',
        ]
        for q_try in quoted_queries:
            items = _search_ytmusic_songs(q_try, filter_songs=True)
            _evaluate_items(items)
            if candidates and any(s >= 50 for s, _ in candidates):
                break

    # Pass 3: ISRC Exact Lookup
    if not candidates:
        if not clean_isrc and track_id and str(track_id).isdigit():
            try:
                from . import deezer_api
                clean_isrc = deezer_api.get_track_isrc(str(track_id)).strip().upper()
            except Exception:
                pass

        if clean_isrc:
            isrc_items = _search_ytmusic_songs(clean_isrc, filter_songs=True)
            _evaluate_items(isrc_items)

    # Pass 4: Unfiltered Audio Search
    if not candidates:
        for q_try in fast_queries:
            items = _search_ytmusic_songs(q_try, filter_songs=False)
            _evaluate_items(items)
            if candidates:
                break

    # Pass 5: Auto-Healing Official Cut Fallback
    if not candidates:
        heal_queries = [
            f"{clean_artist} {clean_core} official",
            f"{clean_artist} {clean_core}",
            f"{clean_artist} - {clean_core}",
        ]
        for q_try in heal_queries:
            items = _search_ytmusic_songs(q_try, filter_songs=True)
            if not items:
                items = _search_ytmusic_songs(q_try, filter_songs=False)
            _evaluate_items(items, tolerance_secs=15, match_target=clean_core)
            if candidates:
                break

    # Pass 6: Direct YouTube Search Fallback
    if not candidates:
        try:
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "extract_flat": True,
                "skip_download": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                for yt_query in (f"{clean_artist} - {clean_core} Official Audio", f"{clean_artist} - {clean_core}"):
                    res_flat = ydl.extract_info(f"ytsearch5:{yt_query}", download=False)
                    raw_entries = []
                    for entry in (res_flat.get("entries") or []):
                        vid = entry.get("id")
                        title = entry.get("title")
                        if vid and title:
                            raw_entries.append({
                                "id": vid,
                                "title": title,
                                "channel": entry.get("uploader") or entry.get("channel") or "",
                                "artists": [entry.get("uploader") or ""],
                                "duration_seconds": int(entry.get("duration") or 0),
                                "duration": str(entry.get("duration") or ""),
                                "thumbnail": entry.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                            })
                    _evaluate_items(raw_entries, tolerance_secs=5, match_target=clean_core)
                    if candidates:
                        break
        except Exception:
            pass

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        found_candidate = candidates[0][1]

    result = {
        "ok": bool(found_candidate),
        "id": found_candidate["id"] if found_candidate else None,
        "title": found_candidate["title"] if found_candidate else clean_title,
        "channel": found_candidate["channel"] if found_candidate else clean_artist,
        "duration": found_candidate.get("duration", "") if found_candidate else "",
        "thumbnail": found_candidate.get("thumbnail", "") if found_candidate else "",
    }

    if found_candidate:
        _TRACK_RESOLUTION_CACHE[cache_key] = (result, now)
        try:
            from .. import store
            store.set_stream_resolution(cache_key, result, ttl_seconds=604800)  # 7 days
        except Exception:
            pass
        try:
            from .. import logger
            logger.get_logger("stream").info(f"Resolved track '{clean_artist} - {clean_title}' -> YouTube [{found_candidate['id']}] ({found_candidate.get('duration')})")
        except Exception:
            pass
        prewarm_stream(found_candidate["id"])
    else:
        try:
            from .. import logger
            logger.get_logger("stream").warning(f"No match found for track '{clean_artist} - {clean_title}'")
        except Exception:
            pass

    return result

def get_stream_info(video_id: str, quality: str = "auto", force_fresh: bool = False) -> Tuple[Optional[str], dict]:
    """Extract direct audio stream URL and HTTP headers via yt-dlp with cookie support and selectable quality."""
    vid = (video_id or "").strip()
    is_yt_id = bool(re.match(r"^[a-zA-Z0-9_-]{11}$", vid))
    is_url = bool(re.match(r"^https?://", vid))
    if not vid or (not is_yt_id and not is_url):
        return None, {}

    q_key = str(quality or "auto").lower()
    cache_key = f"{vid}_{q_key}"
    now = time.time()
    if not force_fresh:
        if cache_key in _STREAM_URL_CACHE:
            cached_url, hdrs, ts = _STREAM_URL_CACHE[cache_key]
            if now - ts < 10800:  # 3 hours memory cache
                return cached_url, hdrs

        # Check L2 SQLite Persistent Store
        try:
            from .. import store
            db_url, db_hdrs = store.get_stream_url(vid)
            if db_url:
                _STREAM_URL_CACHE[vid] = (db_url, db_hdrs, now)
                return db_url, db_hdrs
        except Exception:
            pass

    try:
        import yt_dlp

        cfg = load_bot_config()
        cookies_browser = str(cfg.get("yt_dlp_cookies_browser") or "").strip().lower()

        format_map = {
            "128k": "140/bestaudio[abr<=128]/bestaudio",
            "192k": "251/bestaudio[abr<=192]/bestaudio",
            "320k": "bestaudio[abr>=320]/bestaudio[abr>=256]/251/bestaudio",
            "auto": "bestaudio[abr>=160]/251/140/bestaudio[abr>=128]/bestaudio"
        }
        chosen_format = format_map.get(q_key, format_map["auto"])

        ydl_opts = {
            "format": chosen_format,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "compat_opts": ["no-plugins"],
            "check_formats": False,
        }

        cookie_file_candidates = [
            os.path.join(_ROOT_DIR, "cookies.txt"),
            os.path.join(_ROOT_DIR, "data", "cookies.txt"),
        ]
        cookie_file = next((f for f in cookie_file_candidates if os.path.isfile(f)), None)

        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        elif cookies_browser:
            ydl_opts["cookiesfrombrowser"] = (cookies_browser, None, None, None)

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}" if is_yt_id else vid, download=False)
        except Exception:
            # Fallback without browser cookies if browser profile is locked
            if "cookiefile" in ydl_opts or "cookiesfrombrowser" in ydl_opts:
                ydl_opts.pop("cookiesfrombrowser", None)
                ydl_opts.pop("cookiefile", None)
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}" if is_yt_id else vid, download=False)
            else:
                raise

        url = info.get("url")
        hdrs = info.get("http_headers") or {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        if info:
            _STREAM_METADATA_CACHE[vid] = {
                "title": info.get("title") or "",
                "artist": info.get("uploader") or info.get("channel") or "",
                "duration": info.get("duration") or 0,
                "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            }
        if url:
            _STREAM_URL_CACHE[cache_key] = (url, hdrs, now)
            try:
                from .. import store
                store.set_stream_url(vid, url, hdrs, ttl_seconds=10800)  # 3 hours
            except Exception:
                pass
            return url, hdrs
    except Exception as exc:
        try:
            from .. import logger
            logger.get_logger("stream").warning(f"Stream extraction notice for {vid}: {exc}")
        except Exception:
            pass

    return None, {}

def get_video_metadata(video_id: str) -> dict:
    """Retrieve cached YouTube video metadata (title, artist, duration, thumbnail)."""
    vid = (video_id or "").strip()
    return _STREAM_METADATA_CACHE.get(vid, {})

def prewarm_stream(video_id: str, quality: str = "auto"):
    """Pre-extract direct stream URL in background so playback begins instantly with zero delay."""
    vid = (video_id or "").strip()
    if not vid or not re.match(r"^[a-zA-Z0-9_-]{11}$", vid):
        return
    q_key = str(quality or "auto").lower()
    if f"{vid}_{q_key}" in _STREAM_URL_CACHE or vid in _STREAM_URL_CACHE:
        return

    import threading
    def _worker():
        try:
            get_stream_info(vid, quality=q_key)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True, name=f"prewarm_{vid}").start()

