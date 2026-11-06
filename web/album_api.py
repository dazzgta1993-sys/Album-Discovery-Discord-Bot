"""Album Details & Tracklist API handler for Web Control Hub."""

import asyncio
from aiohttp import web
import logging

log = logging.getLogger("server")
search_log = logging.getLogger("search")

async def api_album_tracks(request: web.Request) -> web.Response:
    from app.services import deezer_api, musicbrainz_api
    from app.services.taxonomy import clean_master_title
    from core.player import AudioTrack

    aid = request.query.get("id", "").strip()
    title = request.query.get("title", "").strip()
    artist = request.query.get("artist", "").strip()

    if not aid and not title:
        return web.json_response({"tracks": [], "error": "Album ID or Title required"}, status=400)

    alb_data = None
    clean_aid = aid
    while clean_aid.startswith("mb_"):
        clean_aid = clean_aid[3:]

    try:
        if clean_aid.isdigit():
            alb_data = await asyncio.to_thread(deezer_api.get_album_details, clean_aid)
        elif "-" in clean_aid or len(clean_aid) == 36:
            alb_data = await asyncio.to_thread(musicbrainz_api.get_release_group_details, clean_aid)

        if not alb_data or not alb_data.get("tracks"):
            if title:
                search_queries = [f"{artist} {title}".strip()]
                cleaned = clean_master_title(title).strip()
                if cleaned and cleaned.lower() != title.lower():
                    search_queries.append(f"{artist} {cleaned}".strip())
                for sq in search_queries:
                    found = await asyncio.to_thread(deezer_api.search_albums, sq, limit=5)
                    for f_alb in (found or []):
                        if (f_alb.get("record_type") or "").lower() == "album" or int(f_alb.get("tracks_count") or 0) >= 4:
                            alb_data = await asyncio.to_thread(deezer_api.get_album_details, str(f_alb["id"]))
                            aid = str(f_alb["id"])
                            break
                    if alb_data and alb_data.get("tracks"):
                        break
                if not alb_data and found:
                    alb_data = await asyncio.to_thread(deezer_api.get_album_details, str(found[0]["id"]))
                    aid = str(found[0]["id"])

        if alb_data and (alb_data.get("record_type", "").lower() == "single" or len(alb_data.get("tracks", [])) <= 2) and title:
            search_queries = [f"{artist} {title}".strip()]
            cleaned = clean_master_title(title).strip()
            if cleaned and cleaned.lower() != title.lower():
                search_queries.append(f"{artist} {cleaned}".strip())
            for sq in search_queries:
                candidate_albums = await asyncio.to_thread(deezer_api.search_albums, sq, limit=5)
                for ca in (candidate_albums or []):
                    ca_rec = (ca.get("record_type") or "").lower()
                    ca_tracks = int(ca.get("tracks_count") or ca.get("nb_tracks") or 0)
                    if ca_rec == "album" or ca_tracks >= 4:
                        full_alb = await asyncio.to_thread(deezer_api.get_album_details, str(ca["id"]))
                        if full_alb and len(full_alb.get("tracks", [])) >= 4:
                            alb_data = full_alb
                            aid = str(ca["id"])
                            break
                if alb_data and len(alb_data.get("tracks", [])) >= 4:
                    break
    except Exception as e:
        log.warning(f"Error fetching album details for {artist} - {title} ({aid}): {e}")

    tracks = []
    alb_title = (alb_data.get("title") if alb_data else "") or title or "Unknown Album"
    alb_artist = (alb_data.get("artist") if alb_data else "") or artist or "Unknown Artist"
    alb_cover = (alb_data.get("cover") if alb_data else "") or ""

    raw_tracks = alb_data.get("tracks", []) if alb_data else []
    for idx, t in enumerate(raw_tracks, 1):
        dur = int(t.get("duration", 0))
        t_artist = t.get("artist") or alb_artist
        if isinstance(t_artist, dict):
            t_artist = t_artist.get("name", alb_artist)
        tracks.append({
            "track_num": t.get("track_num") or idx,
            "disc_num": t.get("disc_num", 1),
            "title": t.get("title") or f"Track {idx}",
            "artist": t_artist,
            "album": alb_title,
            "duration": AudioTrack._format_duration(dur),
            "duration_seconds": dur,
            "cover": alb_cover,
            "id": str(t.get("id") or ""),
            "source": "deezer"
        })

    search_log.info(f"[Web Hub Album Tracks] Fetched {len(tracks)} tracks for '{alb_artist} - {alb_title}' (id: {aid})")
    return web.json_response({
        "album_id": aid,
        "title": alb_title,
        "artist": alb_artist,
        "cover": alb_cover,
        "track_count": len(tracks),
        "tracks": tracks
    })

async def api_dna(request: web.Request) -> web.Response:
    bot = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    try:
        gid = int(guild_id)
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid guild id"}, status=400)
    
    from app.services import dna_engine
    player = bot.player_manager.players.get(gid)
    if not player:
        return web.json_response(dna_engine.compute_session_music_dna([]))
    tracks = [h.to_dict() if hasattr(h, "to_dict") else h for h in player.history if getattr(h, "artist", "") != "Unknown Artist"]
    if player.current_track:
        tracks.append(player.current_track.to_dict() if hasattr(player.current_track, "to_dict") else player.current_track)
        
    dna = dna_engine.compute_session_music_dna(tracks)
    return web.json_response(dna)

@web.middleware
async def static_cache_control_middleware(request: web.Request, handler):
    import os
    from urllib.parse import urlparse
    if request.path.startswith("/api/"):
        # 1. Local network / optional API token security guard
        api_key = os.getenv("WEB_API_KEY", "").strip()
        remote_ip = (request.remote or "").strip()
        is_local = remote_ip in ("127.0.0.1", "::1", "localhost") or remote_ip.startswith(("192.168.", "10.", "172."))
        if api_key:
            req_key = request.headers.get("X-API-Key") or request.query.get("api_key") or ""
            if req_key != api_key and not is_local:
                return web.json_response({"error": "Unauthorized: valid API key required"}, status=401)
        elif not is_local:
            return web.json_response({"error": "Forbidden: Web Control Hub is restricted to local access"}, status=403)
        # 2. CSRF / Origin validation on state-mutating requests
        if request.method in ("POST", "PUT", "DELETE"):
            origin = request.headers.get("Origin", "").strip()
            if origin:
                parsed_origin = urlparse(origin)
                req_host = (request.host or "").split(":")[0].lower()
                orig_host = (parsed_origin.hostname or "").lower()
                if orig_host not in (req_host, "localhost", "127.0.0.1", "::1"):
                    return web.json_response({"error": "Forbidden: cross-origin state mutation blocked"}, status=403)
    response = await handler(request)
    if request.path.startswith("/static/") or request.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def handle_logs_io_sync(file_map: dict, method: str, log_type: str):
    import os
    if method == "POST":
        for p in file_map.values():
            if os.path.exists(p):
                try:
                    with open(p, "w", encoding="utf-8") as f:
                        f.truncate(0)
                except Exception as e:
                    log.debug(f"Log truncate notice for {p}: {e}")
        return {"status": "ok", "cleared": True}
    lines = []
    if log_type in file_map:
        target_path = file_map[log_type]
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines()[-80:] if l.strip()]
            except Exception as e:
                log.debug(f"Log read notice for {target_path}: {e}")
    else:
        merged = []
        for p in file_map.values():
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        merged.extend([l.strip() for l in f.readlines()[-60:] if l.strip()])
                except Exception as e:
                    log.debug(f"Log merge notice for {p}: {e}")
        merged.sort()
        lines = merged[-80:]
    return {"logs": lines, "type": log_type}



async def api_discography(request: web.Request) -> web.Response:
    from app.services import deezer_api
    artist = request.query.get("artist", "").strip()
    if not artist:
        return web.json_response({"albums": [], "categories": [], "counts": {}})
    artists = await asyncio.to_thread(deezer_api.search_artists, query=artist, limit=1)
    if not artists:
        return web.json_response({"albums": [], "categories": [], "counts": {}})
    art = artists[0]
    art_id = str(art.get("id"))
    art_name = art.get("name") or artist

    albums_raw = await asyncio.to_thread(deezer_api.get_artist_discography, art_id, 80)
    seen_titles = set()
    cleaned = []
    for a in albums_raw:
        title = a.get("title", "").strip()
        t_lower = title.lower()
        if t_lower in seen_titles:
            continue
        seen_titles.add(t_lower)
        cleaned.append(a)
    return web.json_response({"artist": art_name, "albums": cleaned})

async def api_timemachine(request: web.Request) -> web.Response:
    try:
        from app.services import timemachine_service
        year_str = request.query.get("year", "1999").strip()
        year = int(year_str) if year_str.isdigit() else 1999
        data = await asyncio.to_thread(timemachine_service.get_timemachine_albums, year)
        years = await asyncio.to_thread(timemachine_service.get_timemachine_years)
        return web.json_response({"year": year, "years": years, "albums": data.get("albums", [])})
    except Exception as e:
        return web.json_response({"year": 1999, "years": [], "albums": [], "error": str(e)})

async def api_radio(request: web.Request) -> web.Response:
    try:
        from app.services import official_charts
        radio_id = request.query.get("station", "").strip()
        if radio_id:
            tracks = await asyncio.to_thread(official_charts.get_live_radio_tracks, radio_id)
            return web.json_response({"station": radio_id, "tracks": tracks})
        stations = await asyncio.to_thread(official_charts.get_live_dj_stations, limit=100)
        return web.json_response({"stations": stations})
    except Exception as e:
        return web.json_response({"stations": [], "error": str(e)})


async def api_crate(request: web.Request) -> web.Response:
    """GET or POST handler for ❤️ My Crate (Saved Favorites & Custom Playlists)."""
    import random
    from app import store
    from core.player import AudioTrack

    bot = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    try:
        gid = int(guild_id)
    except (ValueError, TypeError):
        return web.json_response({"error": "Invalid guild id"}, status=400)

    guild = bot.get_guild(gid)
    player = bot.player_manager.get_player(guild) if guild else None

    if request.method == "GET":
        playlist = request.query.get("playlist", "Favorites").strip() or "Favorites"
        pl_meta = store.get_crate_playlists(str(gid))
        tracks = store.get_crate_tracks(str(gid), playlist)
        return web.json_response({
            "playlist": playlist,
            "playlists": pl_meta.get("playlists", []),
            "total_count": pl_meta.get("total_count", 0),
            "tracks": tracks
        })

    try:
        data = await request.json()
    except Exception:
        data = {}

    action = str(data.get("action", "add")).lower().strip()
    playlist = str(data.get("playlist", "Favorites")).strip()[:60] or "Favorites"

    if action == "add":
        track_payload = data.get("track")
        if not track_payload and player and player.current_track:
            t = player.current_track
            track_payload = {
                "title": t.title, "artist": t.artist, "album": t.album,
                "duration": t.duration_str, "duration_seconds": t.duration_seconds,
                "cover": t.cover_url, "video_id": t.video_id, "source": getattr(t, "source", "deezer")
            }
        if not track_payload:
            return web.json_response({"error": "No track playing or specified"}, status=400)
        res = store.add_to_crate(str(gid), track_payload, playlist_name=playlist)
        if player and track_payload.get("artist"):
            player.handle_feedback(track_payload.get("artist", ""), track_payload.get("title", ""), "up")
        pl_meta = store.get_crate_playlists(str(gid))
        return web.json_response({
            "status": "ok",
            "added": res.get("added", False),
            "playlist": playlist,
            "count": res.get("count", 0),
            "total_count": pl_meta.get("total_count", 0),
            "playlists": pl_meta.get("playlists", []),
            "tracks": store.get_crate_tracks(str(gid), playlist)
        })

    elif action == "remove":
        track_key = data.get("track_key", "")
        store.remove_from_crate(str(gid), track_key, playlist_name=playlist)
        pl_meta = store.get_crate_playlists(str(gid))
        return web.json_response({
            "status": "ok",
            "playlist": playlist,
            "total_count": pl_meta.get("total_count", 0),
            "playlists": pl_meta.get("playlists", []),
            "tracks": store.get_crate_tracks(str(gid), playlist)
        })

    elif action == "create_playlist":
        pl_meta = store.create_crate_playlist(str(gid), playlist)
        return web.json_response({
            "status": "ok",
            "playlist": playlist,
            "total_count": pl_meta.get("total_count", 0),
            "playlists": pl_meta.get("playlists", []),
            "tracks": store.get_crate_tracks(str(gid), playlist)
        })

    elif action == "delete_playlist":
        pl_meta = store.delete_crate_playlist(str(gid), playlist)
        next_pl = "Favorites"
        return web.json_response({
            "status": "ok",
            "playlist": next_pl,
            "total_count": pl_meta.get("total_count", 0),
            "playlists": pl_meta.get("playlists", []),
            "tracks": store.get_crate_tracks(str(gid), next_pl)
        })

    elif action == "play_all":
        if not guild or not player:
            return web.json_response({"error": "Guild player not available"}, status=404)
        tracks = store.get_crate_tracks(str(gid), playlist)
        if not tracks:
            return web.json_response({"error": f"Playlist '{playlist}' is empty"}, status=400)
        if not player.is_connected:
            target_vc = next((vc for vc in guild.voice_channels if any(not m.bot for m in vc.members)), guild.voice_channels[0] if guild.voice_channels else None)
            if target_vc:
                try:
                    await player.connect(target_vc)
                except Exception as e:
                    log.debug(f'Crate voice connect notice: {e}')
        work = list(tracks)
        if data.get("shuffle"):
            random.shuffle(work)
        play_now = bool(data.get("play_now", False))
        q_tracks = [
            AudioTrack(
                title=t.get("title", "Unknown"), artist=t.get("artist", "Unknown"),
                album=t.get("album", ""), duration_seconds=int(t.get("duration_seconds") or 0),
                duration_str=t.get("duration") or "", cover_url=t.get("cover") or "",
                video_id=t.get("video_id"), requested_by=f"My Crate ❤️ ({playlist})",
                source=t.get("source", "deezer")
            )
            for t in work
        ]
        was_playing = player.is_playing
        total = player.enqueue_many(q_tracks, at_front=play_now)
        if play_now and was_playing:
            player.skip()
        elif not was_playing:
            asyncio.create_task(player.play_next())
        return web.json_response({"status": "ok", "enqueued_count": len(q_tracks), "total": total})

    return web.json_response({"error": f"Unknown crate action: {action}"}, status=400)
