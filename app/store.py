from core.logger import get_logger
_log = get_logger("database")
"""SQLite WAL-Mode Persistent Caching & Storage Engine.
Handles multi-tier persistent API caching, track stream resolution caches,
favorites, and playback history with thread-safety and automatic expiry.
"""
import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional, Tuple

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_ROOT_DIR, "data")
_DB_PATH = os.path.join(_DATA_DIR, "cache.db")

_lock = threading.Lock()


def _get_connection() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    """Initialize SQLite database tables and indices."""
    with _lock, _get_connection() as conn:
        cursor = conn.cursor()

        # 1. API Cache (Deezer & MusicBrainz responses)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                url TEXT PRIMARY KEY,
                namespace TEXT,
                data_json TEXT,
                created_at REAL,
                expires_at REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_cache_namespace ON api_cache(namespace, expires_at)")

        # 2. Track Stream Resolution Cache (Artist + Title -> Official YouTube video ID)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stream_resolutions (
                track_key TEXT PRIMARY KEY,
                video_id TEXT,
                title TEXT,
                channel TEXT,
                duration TEXT,
                thumbnail TEXT,
                created_at REAL,
                expires_at REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stream_resolutions_expires ON stream_resolutions(expires_at)")

        # 3. Direct Audio Stream URLs Cache (Video ID -> CDN URL + headers)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stream_urls (
                video_id TEXT PRIMARY KEY,
                stream_url TEXT,
                headers_json TEXT,
                created_at REAL,
                expires_at REAL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_stream_urls_expires ON stream_urls(expires_at)")

        # 6. Multi-Service Deterministic Album Catalog (Deezer + iTunes + MusicBrainz)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS album_catalog (
                upc TEXT PRIMARY KEY,
                deezer_id TEXT,
                itunes_id TEXT,
                mb_release_group_id TEXT,
                artist TEXT NOT NULL,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                deezer_cover TEXT,
                itunes_artwork TEXT,
                cached_at INTEGER NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_deezer ON album_catalog(deezer_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_itunes ON album_catalog(itunes_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_artist ON album_catalog(artist)")

                # 7. Guild Persistent Settings (Brain & Autoplay configuration)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        conn.commit()


# -------------------------------------------------------------
# MULTI-SERVICE ALBUM CATALOG CACHE (<0.2ms lookups)
# -------------------------------------------------------------

def get_catalog_by_upc(upc: str) -> Optional[dict]:
    if not upc:
        return None
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM album_catalog WHERE upc = ?", (str(upc).strip(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
    except Exception as exc:
        _log.error(f"get_catalog_by_upc error: {exc}")
    return None


def get_catalog_by_deezer_id(deezer_id: str) -> Optional[dict]:
    if not deezer_id:
        return None
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM album_catalog WHERE deezer_id = ?", (str(deezer_id).strip(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
    except Exception as exc:
        _log.error(f"get_catalog_by_deezer_id error: {exc}")
    return None


def get_catalog_by_itunes_id(itunes_id: str) -> Optional[dict]:
    if not itunes_id:
        return None
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM album_catalog WHERE itunes_id = ?", (str(itunes_id).strip(),))
            row = cursor.fetchone()
            if row:
                return dict(row)
    except Exception as exc:
        _log.error(f"get_catalog_by_itunes_id error: {exc}")
    return None


def save_catalog_entry(entry: dict) -> bool:
    upc = str(entry.get("upc") or "").strip()
    if not upc:
        return False
    now = int(time.time())
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO album_catalog (
                    upc, deezer_id, itunes_id, mb_release_group_id,
                    artist, title, category, deezer_cover, itunes_artwork, cached_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(upc) DO UPDATE SET
                    deezer_id = COALESCE(excluded.deezer_id, album_catalog.deezer_id),
                    itunes_id = COALESCE(excluded.itunes_id, album_catalog.itunes_id),
                    mb_release_group_id = COALESCE(excluded.mb_release_group_id, album_catalog.mb_release_group_id),
                    artist = excluded.artist,
                    title = excluded.title,
                    category = excluded.category,
                    deezer_cover = COALESCE(excluded.deezer_cover, album_catalog.deezer_cover),
                    itunes_artwork = COALESCE(excluded.itunes_artwork, album_catalog.itunes_artwork),
                    cached_at = excluded.cached_at
            """, (
                upc,
                str(entry.get("deezer_id") or ""),
                str(entry.get("itunes_id") or ""),
                str(entry.get("mb_release_group_id") or ""),
                str(entry.get("artist") or "Unknown Artist"),
                str(entry.get("title") or "Unknown Album"),
                str(entry.get("category") or "Studio Albums"),
                str(entry.get("deezer_cover") or ""),
                str(entry.get("itunes_artwork") or ""),
                now
            ))
            conn.commit()
            return True
    except Exception as exc:
        _log.error(f"save_catalog_entry error: {exc}")
        return False


# -------------------------------------------------------------
# API CACHE (L2 Persistent Cache)
# -------------------------------------------------------------

def get_api_cache(url: str, allow_stale: bool = False) -> Optional[Any]:
    now = time.time()
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json, expires_at FROM api_cache WHERE url = ?",
                (url,)
            )
            row = cursor.fetchone()
            if row:
                if row["expires_at"] > now or allow_stale:
                    return json.loads(row["data_json"])
    except Exception as exc:
        _log.error(f"api_cache get error for {url}: {exc}")
    return None


def set_api_cache(url: str, data: Any, ttl_seconds: int = 1800, namespace: str = "general"):
    now = time.time()
    expires_at = now + ttl_seconds
    try:
        body = json.dumps(data, ensure_ascii=False)
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO api_cache (url, namespace, data_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    namespace = excluded.namespace,
                    data_json = excluded.data_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
            """, (url, namespace, body, now, expires_at))
            conn.commit()
    except Exception as exc:
        _log.error(f"api_cache set error for {url}: {exc}")


# -------------------------------------------------------------
# STREAM RESOLUTION CACHE
# -------------------------------------------------------------

def get_stream_resolution(track_key: str) -> Optional[dict]:
    now = time.time()
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT video_id, title, channel, duration, thumbnail, expires_at FROM stream_resolutions WHERE track_key = ?",
                (track_key,)
            )
            row = cursor.fetchone()
            if row:
                if row["expires_at"] > now:
                    return {
                        "ok": True,
                        "id": row["video_id"],
                        "title": row["title"],
                        "channel": row["channel"],
                        "duration": row["duration"],
                        "thumbnail": row["thumbnail"],
                    }
                else:
                    cursor.execute("DELETE FROM stream_resolutions WHERE track_key = ?", (track_key,))
                    conn.commit()
    except Exception as exc:
        _log.error(f"stream_resolution get error: {exc}")
    return None


def set_stream_resolution(track_key: str, result: dict, ttl_seconds: int = 604800):
    """Cache track resolution (default 7 days)."""
    now = time.time()
    expires_at = now + ttl_seconds
    vid = result.get("id")
    if not vid:
        return
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stream_resolutions (track_key, video_id, title, channel, duration, thumbnail, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_key) DO UPDATE SET
                    video_id = excluded.video_id,
                    title = excluded.title,
                    channel = excluded.channel,
                    duration = excluded.duration,
                    thumbnail = excluded.thumbnail,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
            """, (
                track_key,
                vid,
                result.get("title", ""),
                result.get("channel", ""),
                result.get("duration", ""),
                result.get("thumbnail", ""),
                now,
                expires_at,
            ))
            conn.commit()
    except Exception as exc:
        _log.error(f"stream_resolution set error: {exc}")


def clear_stream_resolutions():
    """Clear cached track resolutions to ensure only high-precision studio audio is used."""
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stream_resolutions")
            conn.commit()
    except Exception as exc:
        _log.error(f"clear_stream_resolutions error: {exc}")


# -------------------------------------------------------------
# STREAM URL CACHE (YouTube CDN URLs, 3 hours TTL)
# -------------------------------------------------------------

def get_stream_url(video_id: str) -> Tuple[Optional[str], dict]:
    now = time.time()
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT stream_url, headers_json, expires_at FROM stream_urls WHERE video_id = ?",
                (video_id,)
            )
            row = cursor.fetchone()
            if row:
                if row["expires_at"] > now:
                    hdrs = json.loads(row["headers_json"] or "{}")
                    return row["stream_url"], hdrs
                else:
                    cursor.execute("DELETE FROM stream_urls WHERE video_id = ?", (video_id,))
                    conn.commit()
    except Exception as exc:
        _log.error(f"stream_url get error: {exc}")
    return None, {}


def set_stream_url(video_id: str, stream_url: str, headers: dict, ttl_seconds: int = 10800):
    """Cache direct stream URL (default 3 hours)."""
    now = time.time()
    expires_at = now + ttl_seconds
    try:
        hdrs_str = json.dumps(headers or {})
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO stream_urls (video_id, stream_url, headers_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                    stream_url = excluded.stream_url,
                    headers_json = excluded.headers_json,
                    created_at = excluded.created_at,
                    expires_at = excluded.expires_at
            """, (video_id, stream_url, hdrs_str, now, expires_at))
            conn.commit()
    except Exception as exc:
        _log.error(f"stream_url set error: {exc}")

def delete_stream_url(video_id: str):
    """Evict expired or invalid stream URL from SQLite store."""
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM stream_urls WHERE video_id = ?", (video_id,))
            conn.commit()
    except Exception as exc:
        _log.error(f"stream_url delete error: {exc}")




def save_guild_settings(guild_id: str, settings: dict):
    """Save persistent brain and player settings for a guild."""
    if not guild_id or not settings:
        return
    with _lock, _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO guild_settings (guild_id, settings_json, updated_at)
            VALUES (?, ?, ?)
        """, (str(guild_id), json.dumps(settings), time.time()))
        conn.commit()


def load_guild_settings(guild_id: str) -> dict:
    """Load persistent brain and player settings for a guild."""
    if not guild_id:
        return {}
    with _lock, _get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id TEXT PRIMARY KEY,
                settings_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        cursor = conn.cursor()
        cursor.execute("SELECT settings_json FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
        row = cursor.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except Exception:
                pass
    return {}


def save_playback_history(guild_id: str, track_data: dict):
    """Save played track to persistent history in SQLite."""
    if not guild_id or not track_data:
        return
    try:
        with _lock, _get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playback_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    track_json TEXT NOT NULL,
                    played_at REAL NOT NULL
                )
            """)
            conn.execute("""
                INSERT INTO playback_history (guild_id, track_json, played_at)
                VALUES (?, ?, ?)
            """, (str(guild_id), json.dumps(track_data), time.time()))
            conn.execute("""
                DELETE FROM playback_history WHERE id IN (
                    SELECT id FROM playback_history WHERE guild_id = ?
                    ORDER BY id DESC LIMIT -1 OFFSET 100
                )
            """, (str(guild_id),))
            conn.commit()
    except Exception as exc:
        _log.warning(f"save_playback_history error: {exc}")


def load_playback_history(guild_id: str, limit: int = 50) -> list:
    """Load persistent playback history for a guild from SQLite."""
    if not guild_id:
        return []
    try:
        with _lock, _get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS playback_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    track_json TEXT NOT NULL,
                    played_at REAL NOT NULL
                )
            """)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT track_json FROM playback_history
                WHERE guild_id = ?
                ORDER BY id DESC LIMIT ?
            """, (str(guild_id), limit))
            rows = cursor.fetchall()
            tracks = []
            for r in reversed(rows):
                if r and r[0]:
                    try:
                        tracks.append(json.loads(r[0]))
                    except Exception:
                        pass
            return tracks
    except Exception as exc:
        _log.warning(f"load_playback_history error: {exc}")
        return []


try:
    init_db()
except Exception as _e:
    pass
