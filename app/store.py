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

        # 8. Saved Crate (Favorites & Custom Playlists)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_crate (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                playlist_name TEXT NOT NULL DEFAULT 'Favorites',
                track_key TEXT NOT NULL,
                track_json TEXT NOT NULL,
                added_at REAL NOT NULL,
                UNIQUE(guild_id, playlist_name, track_key)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crate_playlists (
                guild_id TEXT NOT NULL,
                playlist_name TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY(guild_id, playlist_name)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS taste_profiles (
                guild_id TEXT NOT NULL,
                artist TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY(guild_id, artist)
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


def clear_cache(clear_all: bool = False):
    """Clear expired or all entries in the api_cache and stream cache tables."""
    now = time.time()
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            if clear_all:
                cursor.execute("DELETE FROM api_cache")
                cursor.execute("DELETE FROM stream_resolutions")
            else:
                cursor.execute("DELETE FROM api_cache WHERE expires_at < ?", (now,))
                cursor.execute("DELETE FROM stream_resolutions WHERE expires_at < ?", (now,))
            conn.commit()
    except Exception as exc:
        _log.error(f"clear_cache error: {exc}")


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
    """Save persistent brain and player settings for a guild (merges with existing settings)."""
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
        cursor = conn.cursor()
        cursor.execute("SELECT settings_json FROM guild_settings WHERE guild_id = ?", (str(guild_id),))
        row = cursor.fetchone()
        merged = {}
        if row and row[0]:
            try:
                merged = json.loads(row[0])
            except Exception:
                merged = {}
        merged.update(settings)
        conn.execute("""
            INSERT OR REPLACE INTO guild_settings (guild_id, settings_json, updated_at)
            VALUES (?, ?, ?)
        """, (str(guild_id), json.dumps(merged), time.time()))
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
                SELECT track_json, played_at FROM playback_history
                WHERE guild_id = ?
                ORDER BY id DESC LIMIT ?
            """, (str(guild_id), limit))
            rows = cursor.fetchall()
            tracks = []
            for r in reversed(rows):
                if r and r[0]:
                    try:
                        td = json.loads(r[0])
                        if len(r) > 1 and r[1]:
                            td["played_at"] = r[1]
                        tracks.append(td)
                    except Exception:
                        pass
            return tracks
    except Exception as exc:
        _log.warning(f"load_playback_history error: {exc}")
        return []


def clear_playback_history(guild_id: str):
    """Clear all saved playback history for a guild in SQLite."""
    if not guild_id:
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
            conn.execute("DELETE FROM playback_history WHERE guild_id = ?", (str(guild_id),))
            conn.commit()
    except Exception as exc:
        _log.warning(f"clear_playback_history error: {exc}")


# -------------------------------------------------------------
# SAVED CRATE (FAVORITES & CUSTOM PLAYLISTS)
# -------------------------------------------------------------

def _make_crate_key(artist: str, title: str) -> str:
    return f"{str(artist or 'unknown').strip().lower()}:::{str(title or 'unknown').strip().lower()}"


def add_to_crate(guild_id: str, track_data: dict, playlist_name: str = "Favorites") -> dict:
    """Save a track to a guild's Favorites or custom playlist."""
    gid = str(guild_id or "").strip()
    pl_name = str(playlist_name or "Favorites").strip()[:60] or "Favorites"
    if not gid or not track_data:
        return {"added": False, "playlist": pl_name, "count": 0}
    t_key = _make_crate_key(track_data.get("artist", ""), track_data.get("title", ""))
    now = time.time()
    payload = {
        "title": track_data.get("title", "Unknown"),
        "artist": track_data.get("artist", "Unknown"),
        "album": track_data.get("album", ""),
        "duration": track_data.get("duration") or "",
        "duration_seconds": int(track_data.get("duration_seconds") or 0),
        "cover": track_data.get("cover") or track_data.get("cover_url") or "",
        "video_id": track_data.get("video_id"),
        "source": track_data.get("source") or "deezer",
        "track_key": t_key,
        "added_at": now
    }
    added = False
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO crate_playlists (guild_id, playlist_name, created_at) VALUES (?, ?, ?)", (gid, pl_name, now))
            cursor.execute("""
                INSERT OR IGNORE INTO saved_crate (guild_id, playlist_name, track_key, track_json, added_at)
                VALUES (?, ?, ?, ?, ?)
            """, (gid, pl_name, t_key, json.dumps(payload), now))
            added = cursor.rowcount > 0
            conn.commit()
    except Exception as exc:
        _log.warning(f"add_to_crate error: {exc}")
    tracks = get_crate_tracks(gid, pl_name)
    return {"added": added, "playlist": pl_name, "count": len(tracks), "track_key": t_key}


def remove_from_crate(guild_id: str, track_key: str, playlist_name: str = "Favorites") -> bool:
    """Remove a track from a guild's playlist by track_key."""
    gid = str(guild_id or "").strip()
    pl_name = str(playlist_name or "Favorites").strip() or "Favorites"
    if not gid or not track_key:
        return False
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM saved_crate WHERE guild_id = ? AND playlist_name = ? AND track_key = ?", (gid, pl_name, str(track_key)))
            conn.commit()
            return cursor.rowcount > 0
    except Exception as exc:
        _log.warning(f"remove_from_crate error: {exc}")
        return False


def get_crate_tracks(guild_id: str, playlist_name: str = "Favorites") -> list[dict]:
    """Return all saved tracks in a guild's playlist (newest first)."""
    gid = str(guild_id or "").strip()
    pl_name = str(playlist_name or "Favorites").strip() or "Favorites"
    if not gid:
        return []
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT track_key, track_json FROM saved_crate
                WHERE guild_id = ? AND playlist_name = ?
                ORDER BY id DESC
            """, (gid, pl_name))
            out = []
            for r in cursor.fetchall():
                try:
                    d = json.loads(r["track_json"])
                    d["track_key"] = r["track_key"]
                    out.append(d)
                except Exception:
                    pass
            return out
    except Exception as exc:
        _log.warning(f"get_crate_tracks error: {exc}")
        return []


def get_crate_playlists(guild_id: str) -> dict:
    """Return all playlists with track counts and total saved tracks for a guild."""
    gid = str(guild_id or "").strip()
    if not gid:
        return {"playlists": [{"name": "Favorites", "count": 0}], "total_count": 0}
    try:
        with _lock, _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO crate_playlists (guild_id, playlist_name, created_at) VALUES (?, 'Favorites', ?)", (gid, time.time()))
            conn.commit()
            cursor.execute("SELECT playlist_name FROM crate_playlists WHERE guild_id = ? ORDER BY CASE WHEN playlist_name = 'Favorites' THEN 0 ELSE 1 END, created_at ASC", (gid,))
            names = [r["playlist_name"] for r in cursor.fetchall()]
            cursor.execute("SELECT playlist_name, COUNT(*) as cnt FROM saved_crate WHERE guild_id = ? GROUP BY playlist_name", (gid,))
            counts = {r["playlist_name"]: int(r["cnt"]) for r in cursor.fetchall()}
            for p_name in counts:
                if p_name not in names:
                    names.append(p_name)
            if "Favorites" not in names:
                names.insert(0, "Favorites")
            playlists = [{"name": n, "count": counts.get(n, 0)} for n in names]
            return {"playlists": playlists, "total_count": sum(counts.values())}
    except Exception as exc:
        _log.warning(f"get_crate_playlists error: {exc}")
        return {"playlists": [{"name": "Favorites", "count": 0}], "total_count": 0}


def create_crate_playlist(guild_id: str, playlist_name: str) -> dict:
    """Create a custom named playlist in the guild's crate."""
    gid = str(guild_id or "").strip()
    pl_name = str(playlist_name or "").strip()[:60]
    if gid and pl_name:
        try:
            with _lock, _get_connection() as conn:
                conn.execute("INSERT OR IGNORE INTO crate_playlists (guild_id, playlist_name, created_at) VALUES (?, ?, ?)", (gid, pl_name, time.time()))
                conn.commit()
        except Exception as exc:
            _log.warning(f"create_crate_playlist error: {exc}")
    return get_crate_playlists(gid)


def delete_crate_playlist(guild_id: str, playlist_name: str) -> dict:
    """Delete a custom playlist or clear 'Favorites' if playlist_name is 'Favorites'."""
    gid = str(guild_id or "").strip()
    pl_name = str(playlist_name or "Favorites").strip()
    if gid and pl_name:
        try:
            with _lock, _get_connection() as conn:
                conn.execute("DELETE FROM saved_crate WHERE guild_id = ? AND playlist_name = ?", (gid, pl_name))
                if pl_name != "Favorites":
                    conn.execute("DELETE FROM crate_playlists WHERE guild_id = ? AND playlist_name = ?", (gid, pl_name))
                conn.commit()
        except Exception as exc:
            _log.warning(f"delete_crate_playlist error: {exc}")
    return get_crate_playlists(gid)


try:
    init_db()
except Exception as _e:
    pass


def save_taste_vote(guild_id: str, artist: str, score_delta: int) -> int:
    """Saves or updates persistent taste score for an artist in SQLite."""
    art = str(artist or "").strip().lower()
    if not art:
        return 0
    with _get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT score FROM taste_profiles WHERE guild_id = ? AND artist = ?", (str(guild_id), art))
        row = cursor.fetchone()
        new_score = (row[0] + score_delta) if row else score_delta
        cursor.execute("""
            INSERT INTO taste_profiles (guild_id, artist, score, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, artist) DO UPDATE SET
                score = ?,
                updated_at = ?
        """, (str(guild_id), art, new_score, time.time(), new_score, time.time()))
        conn.commit()
        return new_score


def get_taste_scores(guild_id: str) -> dict:
    """Retrieves all persistent artist taste scores for a guild from SQLite."""
    try:
        with _get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT artist, score FROM taste_profiles WHERE guild_id = ?", (str(guild_id),))
            return {r[0]: r[1] for r in cursor.fetchall()}
    except Exception as e:
        log.debug(f"Taste profile read notice: {e}")
        return {}


def clear_taste_scores(guild_id: str) -> bool:
    """Clear all artist taste scores for a guild from SQLite."""
    try:
        with _get_connection() as conn:
            conn.cursor().execute("DELETE FROM taste_profiles WHERE guild_id = ?", (str(guild_id),))
            conn.commit()
            return True
    except Exception as e:
        log.debug(f"Taste profile clear notice: {e}")
        return False

