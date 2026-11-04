"""Live Deezer API Client - Zero hardcoded data, 100% dynamic live queries."""
import urllib.parse
from ..utils.http_client import fetch_json
from ..utils.normalizer import is_junk_album

DEEZER_BASE = "https://api.deezer.com"


def get_live_genres() -> list[dict]:
    """Fetch live genre categories directly from Deezer API."""
    url = f"{DEEZER_BASE}/genre"
    data = fetch_json(url, cache_ttl=3600)  # 1 hour cache
    if not data or "data" not in data:
        return []
    
    genres = [{"id": 0, "name": "🔥 Top Global Charts", "picture": ""}]
    for g in data.get("data", []):
        gid = g.get("id")
        name = g.get("name", "").strip()
        if gid and name and name.lower() != "all":
            genres.append({
                "id": gid,
                "name": name,
                "picture": g.get("picture_medium") or g.get("picture") or ""
            })
    return genres


def get_chart_albums(genre_id: int = 0, limit: int = 30, genre_name: str = "") -> list[dict]:
    """Fetch official trending albums for a genre or global charts.
    Uses a 3-tier cascade:
    1. Direct album charts (/chart/{genre_id}/albums).
    2. If under limit, harvest albums from trending tracks (/chart/{genre_id}/tracks).
    3. If still under min(30, limit), search top curated albums matching genre name (/search/album).
    """
    url = f"{DEEZER_BASE}/chart/{genre_id}/albums?limit={limit}"
    data = fetch_json(url, cache_ttl=1800)  # 30 min cache

    albums = []
    seen = set()
    for item in (data.get("data", []) if data else []):
        aid = str(item.get("id") or "")
        title = (item.get("title") or "").strip()
        artist_obj = item.get("artist") or {}
        artist_name = (artist_obj.get("name") or "").strip()

        if not aid or not title or is_junk_album(title, artist_name):
            continue

        pair_key = (title.lower(), artist_name.lower())
        if pair_key in seen:
            continue
        seen.add(pair_key)

        cover = (
            item.get("cover_xl")
            or item.get("cover_big")
            or item.get("cover_medium")
            or item.get("cover")
            or ""
        )
        albums.append({
            "id": aid,
            "title": title,
            "artist": artist_name,
            "artist_id": str(artist_obj.get("id") or ""),
            "cover": cover,
            "release_date": str(item.get("release_date") or "")[:4],
            "record_type": (item.get("record_type") or "album").title(),
            "tracks_count": item.get("nb_tracks", 0),
            "link": item.get("link", ""),
            "source": "Deezer Charts"
        })

    # Tier 2: If sparse for a specific genre, harvest albums from trending tracks
    if genre_id != 0 and len(albums) < limit:
        trk_limit = min(100, max(60, limit * 2))
        trk_url = f"{DEEZER_BASE}/chart/{genre_id}/tracks?limit={trk_limit}"
        trk_data = fetch_json(trk_url, cache_ttl=1800)
        for trk in (trk_data.get("data", []) if trk_data else []):
            alb_obj = trk.get("album") or {}
            aid = str(alb_obj.get("id") or "")
            title = (alb_obj.get("title") or "").strip()
            art_obj = trk.get("artist") or {}
            artist_name = (art_obj.get("name") or "").strip()

            if not aid or not title or is_junk_album(title, artist_name):
                continue

            pair_key = (title.lower(), artist_name.lower())
            if pair_key in seen:
                continue
            seen.add(pair_key)

            cover = (
                alb_obj.get("cover_xl")
                or alb_obj.get("cover_big")
                or alb_obj.get("cover_medium")
                or alb_obj.get("cover")
                or ""
            )
            albums.append({
                "id": aid,
                "title": title,
                "artist": artist_name,
                "artist_id": str(art_obj.get("id") or ""),
                "cover": cover,
                "release_date": "",
                "record_type": "Album",
                "tracks_count": 0,
                "link": f"https://www.deezer.com/album/{aid}",
                "source": "Deezer Trending"
            })
            if len(albums) >= limit:
                break

    # Tier 3: If still sparse (< min(30, limit)), query top albums for this genre
    if genre_id != 0 and len(albums) < min(30, limit):
        if not genre_name:
            for g in get_live_genres():
                if g.get("id") == genre_id:
                    genre_name = g.get("name", "")
                    break

        if genre_name:
            custom_map = {
                "Films/Games": "Soundtrack",
                "Soul & Funk": "Soul Funk",
                "Rap/Hip Hop": "Hip Hop",
                "African Music": "African",
                "Asian Music": "Asian",
                "Brazilian Music": "Brazilian",
                "Indian Music": "Indian",
                "Latin Music": "Latin",
            }
            clean_q = custom_map.get(genre_name) or genre_name.replace("/", " ").replace("&", " ").replace("Music", "").strip()
            if clean_q:
                s_url = f"{DEEZER_BASE}/search/album?q={urllib.parse.quote(clean_q)}&limit=50"
                s_data = fetch_json(s_url, cache_ttl=3600)
                for item in (s_data.get("data", []) if s_data else []):
                    aid = str(item.get("id") or "")
                    title = (item.get("title") or "").strip()
                    art_obj = item.get("artist") or {}
                    artist_name = (art_obj.get("name") or "").strip()

                    if not aid or not title or is_junk_album(title, artist_name):
                        continue

                    pair_key = (title.lower(), artist_name.lower())
                    if pair_key in seen:
                        continue
                    seen.add(pair_key)

                    cover = (
                        item.get("cover_xl")
                        or item.get("cover_big")
                        or item.get("cover_medium")
                        or item.get("cover")
                        or ""
                    )
                    albums.append({
                        "id": aid,
                        "title": title,
                        "artist": artist_name,
                        "artist_id": str(art_obj.get("id") or ""),
                        "cover": cover,
                        "release_date": "",
                        "record_type": (item.get("record_type") or "album").title(),
                        "tracks_count": item.get("nb_tracks", 0),
                        "link": item.get("link", "") or f"https://www.deezer.com/album/{aid}",
                        "source": "Deezer Curated"
                    })
                    if len(albums) >= limit:
                        break

    return albums


def search_albums(query: str, limit: int = 30) -> list[dict]:
    """Search albums live across the catalog."""
    q = (query or "").strip()
    if not q:
        return []
    url = f"{DEEZER_BASE}/search/album?q={urllib.parse.quote(q)}&limit={limit}"
    data = fetch_json(url, cache_ttl=600)
    if not data or "data" not in data:
        return []

    albums = []
    seen = set()
    for item in data.get("data", []):
        aid = str(item.get("id") or "")
        title = (item.get("title") or "").strip()
        artist_obj = item.get("artist") or {}
        artist_name = (artist_obj.get("name") or "").strip()

        if not aid or not title or is_junk_album(title, artist_name):
            continue

        pair_key = (title.lower(), artist_name.lower())
        if pair_key in seen:
            continue
        seen.add(pair_key)

        cover = (
            item.get("cover_xl")
            or item.get("cover_big")
            or item.get("cover_medium")
            or item.get("cover")
            or ""
        )
        albums.append({
            "id": aid,
            "title": title,
            "artist": artist_name,
            "artist_id": str(artist_obj.get("id") or ""),
            "cover": cover,
            "release_date": "",
            "record_type": (item.get("record_type") or "album").title(),
            "tracks_count": item.get("nb_tracks", 0),
            "link": item.get("link", ""),
            "source": "Deezer Search"
        })
    return albums


def search_tracks(query: str, limit: int = 15) -> list[dict]:
    """Search Deezer for tracks, singles, live cuts, and remixes."""
    q = (query or "").strip()
    if not q:
        return []
    url = f"{DEEZER_BASE}/search?q={urllib.parse.quote(q)}&limit={limit}"
    data = fetch_json(url, cache_ttl=900)
    if not data or "data" not in data:
        return []

    tracks = []
    q_lower = q.lower()
    explicit_request = any(k in q_lower for k in ("karaoke", "tribute", "cover", "sped", "speed", "slowed", "nightcore", "instrumental", "lullaby"))
    for item in data.get("data", []):
        tid = str(item.get("id") or "")
        title = (item.get("title") or item.get("title_short") or "").strip()
        if not tid or not title:
            continue
        artist_obj = item.get("artist") or {}
        artist_name = (artist_obj.get("name") or "Unknown Artist").strip()

        # Reject junk/tribute/sped-up/slowed tracks unless explicitly requested
        if not explicit_request and is_junk_album(title, artist_name):
            continue

        album_obj = item.get("album") or {}
        cover = (
            album_obj.get("cover_big")
            or album_obj.get("cover_medium")
            or album_obj.get("cover")
            or ""
        )
        tracks.append({
            "id": tid,
            "title": title,
            "artist": artist_obj.get("name") or "Unknown Artist",
            "artist_id": str(artist_obj.get("id") or ""),
            "album": album_obj.get("title") or "",
            "album_id": str(album_obj.get("id") or ""),
            "cover": cover,
            "duration": item.get("duration", 0),
            "preview_url": item.get("preview", ""),
            "explicit": item.get("explicit_lyrics", False),
            "rank": item.get("rank", 0),
            "source": "deezer"
        })
    return tracks


def search_artists(query: str, limit: int = 8) -> list[dict]:
    """Search artists live and rank by fan count."""
    q = (query or "").strip()
    if not q:
        return []
    fetch_limit = max(30, limit * 4)
    url = f"{DEEZER_BASE}/search/artist?q={urllib.parse.quote(q)}&limit={fetch_limit}"
    data = fetch_json(url, cache_ttl=900)
    if not data or "data" not in data:
        return []

    artists = []
    for a in data.get("data", []):
        aid = str(a.get("id") or "")
        name = (a.get("name") or "").strip()
        if not aid or not name:
            continue
        artists.append({
            "id": aid,
            "name": name,
            "picture": a.get("picture_big") or a.get("picture_medium") or a.get("picture") or "",
            "fans": a.get("nb_fan", 0),
            "albums_count": a.get("nb_album", 0),
            "link": a.get("link", "")
        })

    from ..utils.normalizer import rank_artists
    return rank_artists(q, artists)[:limit]


def get_artist_discography(artist_id: str, limit: int = 100, max_pages: int = 10) -> list[dict]:
    """Fetch complete verified discography for an artist with exhaustive index pagination.
    Loops through all available batches until the full catalog (including older singles,
    compilations, and bonus releases) is retrieved.
    Caches the assembled catalog in SQLite for 7-30 days to protect against UI lag and rate limits.
    """
    aid = str(artist_id or "").strip()
    if not aid:
        return []

    cache_key = f"deezer_discography:{aid}"
    try:
        from .. import store
        cached = store.get_api_cache(cache_key)
        if cached and isinstance(cached, list) and len(cached) > 0:
            return cached
    except Exception:
        pass

    albums = []
    seen = set()
    index = 0
    page_size = 100

    while True:
        url = f"{DEEZER_BASE}/artist/{aid}/albums?limit={page_size}&index={index}"
        data = fetch_json(url, cache_ttl=1800)
        if not data or "data" not in data:
            break

        items = data.get("data", [])
        if not items:
            break

        for item in items:
            alb_id = str(item.get("id") or "")
            title = (item.get("title") or "").strip()

            # Exclude ghost/empty packages with 0 tracks
            if not alb_id or not title or is_junk_album(title) or item.get("nb_tracks") == 0:
                continue

            if alb_id in seen:
                continue
            seen.add(alb_id)

            cover = (
                item.get("cover_xl")
                or item.get("cover_big")
                or item.get("cover_medium")
                or item.get("cover")
                or ""
            )
            release_date = str(item.get("release_date") or "").strip()
            albums.append({
                "id": alb_id,
                "title": title,
                "artist_id": aid,
                "cover": cover,
                "release_date": release_date[:4] if release_date else "",
                "full_release_date": release_date,
                "record_type": (item.get("record_type") or "album").title(),
                "tracks_count": item.get("nb_tracks", 0),
                "genre_id": item.get("genre_id", 0),
                "fans": item.get("fans", 0),
                "source": "Verified Discography"
            })

        total = int(data.get("total") or 0)
        has_next = bool(data.get("next"))
        index += len(items)

        if not has_next or index >= total or (max_pages and (index // page_size) >= max_pages):
            break

    # Sort albums by release date descending
    albums.sort(key=lambda x: x.get("full_release_date") or "0000", reverse=True)

    # Persist assembled full catalog in SQLite (7-day TTL)
    if albums:
        try:
            from .. import store
            store.set_api_cache(cache_key, albums, ttl_seconds=86400 * 7, namespace="deezer_discography")
        except Exception:
            pass

    return albums


def get_album_details(album_id: str) -> dict:
    """Fetch complete verified album metadata, tracklist, and 30s audio previews."""
    aid = str(album_id or "").strip()
    if not aid:
        return {"error": "Invalid album id"}

    url = f"{DEEZER_BASE}/album/{aid}"
    data = fetch_json(url, cache_ttl=1800)
    if not data or "id" not in data:
        return {"error": "Album not found on catalog"}

    artist_obj = data.get("artist") or {}
    artist_name = artist_obj.get("name") or "Unknown Artist"
    cover = (
        data.get("cover_xl")
        or data.get("cover_big")
        or data.get("cover_medium")
        or data.get("cover")
        or ""
    )

    genres = [g.get("name") for g in (data.get("genres") or {}).get("data", []) if g.get("name")]
    primary_genre = genres[0] if genres else "Music"

    tracks = []
    tracklist_data = (data.get("tracks") or {}).get("data", [])
    nb_tracks = data.get("nb_tracks", 0)

    # Deezer /album/{id} only embeds the first 25 tracks by default.
    # If the album has more tracks, fetch the complete tracklist via pagination.
    if nb_tracks > len(tracklist_data) or (data.get("tracks") or {}).get("next"):
        fetched_tracks = []
        next_url = f"{DEEZER_BASE}/album/{aid}/tracks?limit=100"
        while next_url and len(fetched_tracks) < 500:
            full_data = fetch_json(next_url, cache_ttl=1800)
            if not full_data or "data" not in full_data:
                break
            batch = full_data["data"]
            if not batch:
                break
            fetched_tracks.extend(batch)
            next_url = full_data.get("next")
        if len(fetched_tracks) > len(tracklist_data):
            tracklist_data = fetched_tracks

    for idx, t in enumerate(tracklist_data, start=1):
        tracks.append({
            "track_num": t.get("track_position") or idx,
            "disc_num": t.get("disk_number", 1),
            "title": t.get("title") or t.get("title_short") or f"Track {idx}",
            "artist": (t.get("artist") or {}).get("name") or artist_name,
            "duration": t.get("duration", 0),
            "explicit": t.get("explicit_lyrics", False),
            "preview_url": t.get("preview", ""),
            "id": str(t.get("id", "")),
            "rank": t.get("rank", 0),
            "isrc": str(t.get("isrc") or "")
        })

    return {
        "id": str(data.get("id")),
        "title": data.get("title", ""),
        "artist": artist_name,
        "artist_id": str(artist_obj.get("id") or ""),
        "artist_picture": artist_obj.get("picture_medium") or "",
        "cover": cover,
        "release_date": data.get("release_date", ""),
        "year": str(data.get("release_date") or "")[:4],
        "genre": primary_genre,
        "record_type": (data.get("record_type") or "album").title(),
        "tracks_count": len(tracks) or data.get("nb_tracks", 0),
        "duration": data.get("duration", 0),
        "fans": data.get("fans", 0),
        "label": data.get("label", ""),
        "upc": data.get("upc", ""),
        "tracks": tracks
    }


def get_related_artists(artist_id: str, limit: int = 15) -> list[dict]:
    """Fetch live similar/related artists from Deezer API."""
    aid = str(artist_id or "").strip()
    if not aid:
        return []
    if not aid.isdigit():
        found = search_artists(aid, limit=1)
        if found and found[0].get("id"):
            aid = str(found[0]["id"])
        else:
            return []
    url = f"{DEEZER_BASE}/artist/{aid}/related?limit={limit}"
    data = fetch_json(url, cache_ttl=3600)  # 1 hour cache
    if not data or "data" not in data:
        return []

    artists = []
    for a in data.get("data", []):
        rel_id = str(a.get("id") or "")
        name = (a.get("name") or "").strip()
        if not rel_id or not name:
            continue
        picture = (
            a.get("picture_big")
            or a.get("picture_medium")
            or a.get("picture")
            or ""
        )
        artists.append({
            "id": rel_id,
            "name": name,
            "picture": picture,
            "picture_small": a.get("picture_small") or "",
            "fans": a.get("nb_fan", 0),
            "albums_count": a.get("nb_album", 0),
            "link": a.get("link", "")
        })
    return artists[:limit]


def get_artist_top_tracks(artist_id: str, limit: int = 5) -> list[dict]:
    """Fetch live top popular tracks for an artist."""
    aid = str(artist_id or "").strip()
    if not aid:
        return []
    url = f"{DEEZER_BASE}/artist/{aid}/top?limit={limit}"
    data = fetch_json(url, cache_ttl=3600)  # 1 hour cache
    if not data or "data" not in data:
        return []

    tracks = []
    for t in data.get("data", []):
        tid = str(t.get("id") or "")
        title = (t.get("title") or "").strip()
        if not tid or not title:
            continue
        alb = t.get("album") or {}
        art = t.get("artist") or {}
        if is_junk_album(title, art.get("name") or ""):
            continue
        cover = alb.get("cover_medium") or alb.get("cover") or ""
        tracks.append({
            "id": tid,
            "title": title,
            "artist": art.get("name") or "",
            "album_title": alb.get("title") or "",
            "album_id": str(alb.get("id") or ""),
            "duration": t.get("duration", 0),
            "preview_url": t.get("preview", ""),
            "cover": cover,
            "explicit": t.get("explicit_lyrics", False),
        })
    return tracks[:limit]


def get_track_isrc(track_id: str) -> str:
    """Fetch track ISRC code from Deezer API."""
    tid = str(track_id or "").strip()
    if not tid or not tid.isdigit():
        return ""
    url = f"{DEEZER_BASE}/track/{tid}"
    data = fetch_json(url, cache_ttl=86400 * 7)  # 7 days cache
    if data and "isrc" in data:
        return str(data.get("isrc") or "").strip()
    return ""

def get_artist_radio(artist_id: str, limit: int = 25) -> list[dict]:
    """Fetch live radio tracks matching artist's vibe from diverse related artists."""
    aid = str(artist_id or "").strip()
    if not aid or not aid.isdigit():
        return []
    url = f"{DEEZER_BASE}/artist/{aid}/radio"
    data = fetch_json(url, cache_ttl=1800)
    if not data or "data" not in data:
        return []

    tracks = []
    for t in data.get("data", [])[:limit]:
        tid = t.get("id")
        title = (t.get("title") or "").strip()
        art = t.get("artist") or {}
        alb = t.get("album") or {}
        if tid and title:
            cover = alb.get("cover_big") or alb.get("cover_medium") or alb.get("cover") or ""
            tracks.append({
                "id": str(tid),
                "title": title,
                "artist": art.get("name") or "",
                "artist_id": str(art.get("id") or ""),
                "album": alb.get("title") or "",
                "album_id": str(alb.get("id") or ""),
                "duration": t.get("duration", 0),
                "preview_url": t.get("preview", ""),
                "cover": cover,
                "explicit": t.get("explicit_lyrics", False),
            })
    return tracks


def get_chart_tracks(limit: int = 30) -> list[dict]:
    """Fetch live top tracks from global charts across diverse artists."""
    url = f"{DEEZER_BASE}/chart/0/tracks?limit={limit}"
    data = fetch_json(url, cache_ttl=1800)
    if not data or "data" not in data:
        return []

    tracks = []
    for t in data.get("data", [])[:limit]:
        tid = t.get("id")
        title = (t.get("title") or "").strip()
        art = t.get("artist") or {}
        alb = t.get("album") or {}
        if tid and title:
            cover = alb.get("cover_big") or alb.get("cover_medium") or alb.get("cover") or ""
            tracks.append({
                "id": str(tid),
                "title": title,
                "artist": art.get("name") or "",
                "artist_id": str(art.get("id") or ""),
                "album": alb.get("title") or "",
                "album_id": str(alb.get("id") or ""),
                "duration": t.get("duration", 0),
                "preview_url": t.get("preview", ""),
                "cover": cover,
                "explicit": t.get("explicit_lyrics", False),
            })
    return tracks



# Compatibility Aliases and Helper Functions for Bot
get_album = get_album_details


def get_album_tracks(album_id: str) -> list[dict]:
    """Return list of tracks for an album."""
    details = get_album_details(album_id)
    return details.get("tracks", [])


def get_track(track_id: str) -> dict:
    """Fetch single track metadata from Deezer."""
    tid = str(track_id or "").strip()
    data = fetch_json(f"{DEEZER_BASE}/track/{tid}", cache_ttl=1800)
    if not data or "id" not in data:
        return {}
    alb = data.get("album") or {}
    art = data.get("artist") or {}
    return {
        "id": data.get("id"),
        "title": data.get("title", ""),
        "artist": art.get("name", "Unknown"),
        "album": alb.get("title", ""),
        "duration": data.get("duration", 0),
        "cover_xl": alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium") or "",
        "cover_medium": alb.get("cover_medium") or alb.get("cover") or "",
        "preview": data.get("preview", "")
    }
