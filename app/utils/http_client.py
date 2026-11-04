"""Resilient HTTP client with User-Agent headers, timeout guards, and multi-tier caching (L1 Memory + L2 SQLite WAL)."""
import json
import time
import urllib.request
from typing import Any, Optional

_MEMORY_CACHE: dict[str, tuple[Any, float]] = {}


def fetch_json(
    url: str,
    timeout: float = 12.0,
    cache_ttl: int = 300,
    headers: Optional[dict] = None,
    namespace: str = "general"
) -> Optional[Any]:
    """Fetch JSON from a remote URL with L1 memory & L2 persistent SQLite caching."""
    now = time.time()

    # 1. Check L1 Memory Cache (microsecond speed)
    if cache_ttl > 0 and url in _MEMORY_CACHE:
        cached_data, timestamp = _MEMORY_CACHE[url]
        if (now - timestamp) < cache_ttl:
            return cached_data

    # 2. Check L2 SQLite Persistent Database Cache
    if cache_ttl > 0:
        try:
            from .. import store
            db_cached = store.get_api_cache(url)
            if db_cached is not None:
                _MEMORY_CACHE[url] = (db_cached, now)
                return db_cached
        except Exception:
            pass

    # 3. Network Fetch
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 AlbumDiscovery/1.0",
        "Accept": "application/json",
    }
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)

            # Save to L1 Memory
            if cache_ttl > 0:
                _MEMORY_CACHE[url] = (data, now)

            # Save to L2 SQLite Persistent Store
            if cache_ttl > 0:
                try:
                    from .. import store
                    store.set_api_cache(url, data, ttl_seconds=cache_ttl, namespace=namespace)
                except Exception:
                    pass

            return data
    except Exception as exc:
        try:
            from core.logger import get_logger
            err_str = str(exc)
            if "404" in err_str or "403" in err_str or "429" in err_str:
                get_logger("http").debug(f"HTTP notice for {url}: {exc}")
            else:
                get_logger("http").warning(f"Error fetching {url}: {exc}")
        except Exception:
            pass

        # Graceful Stale Fallback: If network fetch timed out or failed, return stale cached copy
        try:
            from .. import store
            stale_cached = store.get_api_cache(url, allow_stale=True)
            if stale_cached is not None:
                _MEMORY_CACHE[url] = (stale_cached, now)
                return stale_cached
        except Exception:
            pass

        return None


def clear_cache():
    """Clear memory and database caches."""
    _MEMORY_CACHE.clear()
    try:
        from .. import store
        store.clear_cache(clear_all=True)
    except Exception:
        pass
