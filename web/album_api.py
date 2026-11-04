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
    response = await handler(request)
    if request.path.startswith("/static/") or request.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response



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

    albums_raw = await asyncio.to_thread(deezer_api.get_artist_albums, art_id, 80)
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
