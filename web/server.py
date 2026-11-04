"""Album Discovery Web Control Hub - Real-time async web dashboard.
Runs embedded inside the bot's asyncio event loop using aiohttp.web.
"""
import asyncio
import os
import re
import time
from typing import Optional
from aiohttp import web
import discord

from app.services import deezer_api, stream_service, discovery, itunes_api, musicbrainz_api, official_charts
from core.player import AudioTrack, GuildPlayer
from core.vibe_engine import get_guild_taste_profile
from core.logger import get_bot_logger

log = get_bot_logger("web")
search_log = get_bot_logger("search")

START_TIME = time.time()
WEB_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(WEB_DIR, "static")
INDEX_PATH = os.path.join(STATIC_DIR, "index.html")

def _get_player_and_guild(bot: discord.Client, guild_id_str: str) -> tuple[Optional[discord.Guild], Optional[GuildPlayer]]:
    try:
        gid = int(guild_id_str)
    except (ValueError, TypeError):
        return None, None
    guild = bot.get_guild(gid)
    if not guild:
        return None, None
    player = bot.player_manager.get_player(guild)
    return guild, player

async def handle_index(request: web.Request) -> web.StreamResponse:
    if os.path.exists(INDEX_PATH):
        resp = web.FileResponse(INDEX_PATH)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp
    return web.Response(text="Web Hub frontend index.html not found.", status=404)

async def api_status(request: web.Request) -> web.Response:
    bot: discord.Client = request.app["bot"]
    guilds_data = []
    
    for g in bot.guilds:
        player = bot.player_manager.players.get(g.id)
        vc_name = None
        vc_members = []
        is_conn = False
        is_playing = False
        current_track_dict = None

        if player and player.voice_client and player.voice_client.channel:
            vc = player.voice_client.channel
            vc_name = vc.name
            vc_members = [m.display_name for m in vc.members if not m.bot]
            is_conn = player.is_connected
            is_playing = bool(player.is_playing and player.current_track)
            if player.current_track:
                current_track_dict = player.current_track.to_dict()

        guilds_data.append({
            "id": str(g.id),
            "name": g.name,
            "icon": str(g.icon.url) if g.icon else None,
            "member_count": g.member_count,
            "voice_channel": vc_name,
            "voice_members": vc_members,
            "is_connected": is_conn,
            "is_playing": is_playing,
            "current_track": current_track_dict
        })

    bot_user_tag = str(bot.user) if bot.user else "Offline"
    bot_avatar = str(bot.user.display_avatar.url) if bot.user else ""
    ping = int(bot.latency * 1000) if bot.latency else 0
    uptime = int(time.time() - START_TIME)

    return web.json_response({
        "bot_user": bot_user_tag,
        "bot_avatar": bot_avatar,
        "bot_ping_ms": ping,
        "uptime_seconds": uptime,
        "guilds": guilds_data
    })

async def api_guild_state(request: web.Request) -> web.Response:
    bot: discord.Client = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    guild, player = _get_player_and_guild(bot, guild_id)
    if not guild or not player:
        return web.json_response({"error": "Guild or player not found"}, status=404)

    # Voice channels in guild
    voice_channels = []
    for vc in guild.voice_channels:
        human_members = [m.display_name for m in vc.members if not m.bot]
        voice_channels.append({
            "id": str(vc.id),
            "name": vc.name,
            "members": human_members,
            "member_count": len(human_members)
        })

    connected_vc_id = None
    connected_vc_name = None
    connected_vc_members = []
    if player.voice_client and player.voice_client.channel:
        connected_vc_id = str(player.voice_client.channel.id)
        connected_vc_name = player.voice_client.channel.name
        connected_vc_members = [m.display_name for m in player.voice_client.channel.members if not m.bot]

    elapsed, total = player.get_progress()
    progress_pct = (elapsed / total * 100.0) if (total and total > 0) else 0.0

    queue_list = []
    for i, t in enumerate(list(player.queue)):
        td = t.to_dict()
        td["index"] = i
        td["duration_seconds"] = t.duration_seconds
        queue_list.append(td)

    history_list = []
    for t in list(player.history):
        history_list.append(t.to_dict())

    is_paused = bool(player.voice_client and player.voice_client.is_paused())

    d2 = getattr(player, "deck2_track", None)
    d3 = getattr(player, "deck3_track", None)
    preloaded = d2.to_dict() if d2 else None
    if preloaded and d2:
        preloaded["is_prewarmed"] = bool(d2.stream_url)
        preloaded["is_autoplay"] = bool(d2 == getattr(player, "_prewarmed_autoplay_track", None) or getattr(d2, "is_autoplay", False) or getattr(d2, "requested_by", None) == "Autonomous Autoplay")
    cued_deck3 = d3.to_dict() if d3 else None
    if cued_deck3 and d3:
        cued_deck3["is_prewarmed"] = bool(d3.stream_url)
        cued_deck3["is_autoplay"] = bool(d3 == getattr(player, "_deck3_autoplay_track", None) or getattr(d3, "is_autoplay", False) or getattr(d3, "requested_by", None) == "Autonomous Autoplay")

    return web.json_response({
        "guild": {
            "id": str(guild.id),
            "name": guild.name,
            "icon": str(guild.icon.url) if guild.icon else None
        },
        "voice": {
            "is_connected": player.is_connected,
            "current_channel_id": connected_vc_id,
            "current_channel_name": connected_vc_name,
            "members": connected_vc_members,
            "available_channels": voice_channels
        },
        "player": {
            "is_playing": bool(player.is_playing and player.current_track),
            "is_paused": is_paused,
            "volume": int(player.volume * 100),
            "loop_mode": player.loop_mode,
            "autoplay": player.autoplay,
            "audio_quality": player.audio_quality,
            "progress": {
                "elapsed": elapsed,
                "total": total,
                "formatted_elapsed": AudioTrack._format_duration(elapsed),
                "formatted_total": AudioTrack._format_duration(total),
                "percent": round(progress_pct, 1)
            },
            "current_track": player.current_track.to_dict() if player.current_track else None,
            "preloaded_track": preloaded,
            "deck3_track": cued_deck3,
            "queue": queue_list,
            "queue_count": len(queue_list),
            "history": history_list,
            "brain": {
                "vibe_mode": getattr(player, "vibe_mode", "balanced"),
                "vibe_drift_freq": getattr(player, "vibe_drift_freq", 1),
                "hit_depth": getattr(player, "hit_depth", "balanced"),
                "deck2_enabled": getattr(player, "deck2_enabled", True),
                "deck3_enabled": getattr(player, "deck3_enabled", True),
                "explicit_filter": getattr(player, "explicit_filter", "allow"),
                "artist_cooldown": getattr(player, "artist_cooldown", 10),
                "era_filter": getattr(player, "era_filter", "all"),
                "vibe_energy": getattr(player, "vibe_energy", "auto"),
                "vibe_engine_source": getattr(player, "vibe_engine_source", "auto"),
                "vibe_anchor_artist": player.vibe_anchor_artist or (player.current_track.artist if player.current_track else "None"),
                "is_anchor_locked": getattr(player, "is_anchor_locked", False),
                "consecutive_autoplay_count": player.consecutive_autoplay_count,
                "last_brain_decision": getattr(player, "last_brain_decision", "Brain Online"),
                "deck2_status": "Ready (Preloaded)" if (d2 and d2.stream_url) else ("Buffering" if d2 else "Standby"),
                "deck3_status": "Ready (Cued)" if (d3 and d3.stream_url) else ("Cued" if d3 else "Standby"),
                "taste_profile": get_guild_taste_profile(guild.id)
            }
        }
    })

async def api_feedback(request: web.Request) -> web.Response:
    bot: discord.Client = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    guild, player = _get_player_and_guild(bot, guild_id)
    if not guild or not player:
        return web.json_response({"error": "Guild or player not found"}, status=404)
    try:
        data = await request.json()
    except Exception:
        data = {}
    artist = data.get("artist") or (player.current_track.artist if player.current_track else "")
    title = data.get("title") or (player.current_track.title if player.current_track else "")
    vote = str(data.get("vote", "up")).lower()
    profile = player.handle_feedback(artist, title, vote)
    return web.json_response({"status": "ok", "vote": vote, "artist": artist, "title": title, "taste_profile": profile})

async def api_control(request: web.Request) -> web.Response:
    bot: discord.Client = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    guild, player = _get_player_and_guild(bot, guild_id)
    if not guild or not player:
        return web.json_response({"error": "Guild or player not found"}, status=404)

    try:
        data = await request.json()
    except Exception:
        data = {}

    action = data.get("action", "").lower()
    value = data.get("value")

    if action == "pause":
        player.pause()
    elif action == "resume":
        player.resume()
    elif action == "toggle_play":
        if player.voice_client and player.voice_client.is_paused():
            player.resume()
        elif player.voice_client and player.voice_client.is_playing():
            player.pause()
        elif not player.is_playing and (len(player.queue) > 0 or player.autoplay):
            player._is_stopped = False
            asyncio.create_task(player.play_next())
    elif action == "skip":
        next_t = getattr(player, "deck2_track", None) or (player.queue[0] if player.queue else None)
        player.skip()
        return web.json_response({
            "status": "ok",
            "action": "skip",
            "next_track": next_t.to_dict() if next_t else None
        })
    elif action == "stop":
        player.stop()
    elif action == "shuffle":
        if len(player.queue) == 0 and player.autoplay:
            player._prewarmed_autoplay_track = None
            player._deck3_autoplay_track = None
            asyncio.create_task(player._prewarm_next_track())
        else:
            player.shuffle()
    elif action == "toggle_anchor_lock":
        curr = getattr(player, "is_anchor_locked", False)
        player.is_anchor_locked = not curr
        if player.is_anchor_locked and player.current_track:
            player.vibe_anchor_artist = player.current_track.artist
        return web.json_response({
            "status": "ok",
            "is_locked": player.is_anchor_locked,
            "anchor": player.vibe_anchor_artist or "None"
        })
    elif action == "set_volume":
        try:
            vol = float(value) / 100.0
            player.set_volume(vol)
        except (ValueError, TypeError):
            pass
    elif action == "set_loop":
        modes = ["off", "track", "queue"]
        if value in modes:
            player.loop_mode = value
        else:
            # cycle
            curr_idx = modes.index(player.loop_mode) if player.loop_mode in modes else 0
            player.loop_mode = modes[(curr_idx + 1) % len(modes)]
        asyncio.create_task(player.update_player_message())
    elif action == "set_autoplay":
        player.autoplay = bool(value)
        asyncio.create_task(player.update_player_message())
    elif action == "set_quality":
        if value in ("auto", "128k", "192k", "320k"):
            player.set_quality(str(value))
    elif action == "join_voice":
        ch_id = data.get("channel_id")
        channel = guild.get_channel(int(ch_id)) if ch_id else None
        if channel and (isinstance(channel, (discord.VoiceChannel, discord.StageChannel)) or hasattr(channel, "connect")):
            try:
                await player.connect(channel)
            except Exception as e:
                log.warning(f"Failed to join voice channel: {e}")
    elif action == "leave_voice":
        await player.disconnect()
    elif action == "seek":
        try:
            pos_sec = max(0, int(float(value if value is not None else data.get("position", 0))))
            if player.is_playing and player.current_track:
                player.play_start_time = time.time() - pos_sec
                player.total_paused_time = 0.0
                player.pause_start_time = 0.0
                asyncio.create_task(player.update_player_message())
                return web.json_response({"status": "ok", "action": "seek", "position": pos_sec})
        except Exception as e:
            return web.json_response({"error": f"Seek error: {e}"}, status=400)
    elif action == "set_brain_config":
        if "vibe_mode" in data and data["vibe_mode"] in ("deep_dive", "collabs", "balanced", "discovery"):
            player.vibe_mode = data["vibe_mode"]
        if "vibe_drift_freq" in data:
            try:
                player.vibe_drift_freq = max(1, min(10, int(data["vibe_drift_freq"])))
            except Exception:
                pass
        if "hit_depth" in data and data["hit_depth"] in ("top_hits", "balanced", "deep_cuts"):
            player.hit_depth = data["hit_depth"]
        if "deck2_enabled" in data:
            player.deck2_enabled = bool(data["deck2_enabled"])
        if "deck3_enabled" in data:
            player.deck3_enabled = bool(data["deck3_enabled"])
        if "explicit_filter" in data and data["explicit_filter"] in ("allow", "clean_only"):
            player.explicit_filter = data["explicit_filter"]
        if "artist_cooldown" in data:
            try: player.artist_cooldown = int(data["artist_cooldown"])
            except: pass
        if "era_filter" in data and str(data["era_filter"]) in ("all", "2020s", "2010s", "2000s", "classics"):
            player.era_filter = str(data["era_filter"])
        if "vibe_energy" in data and str(data["vibe_energy"]) in ("auto", "high", "chill"):
            player.vibe_energy = str(data["vibe_energy"])
        if "vibe_engine_source" in data and str(data["vibe_engine_source"]) in ("auto", "ytmusic", "youtube", "deezer", "spotify", "apple", "soundcloud", "musicbrainz", "charts"):
            player.vibe_engine_source = str(data["vibe_engine_source"])
        player.last_brain_decision = f"Brain Hub Update: {player.vibe_mode.title()} (Drift: {player.vibe_drift_freq} tracks)"
        log.info(f"[{guild.name}] Brain configuration updated: {player.vibe_mode}, drift={player.vibe_drift_freq}")
        try:
            from app import store
            store.save_guild_settings(str(guild.id), {
                "vibe_mode": player.vibe_mode,
                "vibe_drift_freq": player.vibe_drift_freq,
                "hit_depth": player.hit_depth,
                "deck2_enabled": player.deck2_enabled,
                "deck3_enabled": getattr(player, "deck3_enabled", True),
                "explicit_filter": player.explicit_filter,
                "artist_cooldown": getattr(player, "artist_cooldown", 10),
                "era_filter": getattr(player, "era_filter", "all"),
                "vibe_energy": getattr(player, "vibe_energy", "auto"),
            })
        except Exception as e:
            log.warning(f"Failed to persist guild brain settings to store: {e}")
        return web.json_response({
            "status": "ok",
            "action": "set_brain_config",
            "brain": {
                "vibe_mode": player.vibe_mode,
                "vibe_drift_freq": player.vibe_drift_freq,
                "hit_depth": player.hit_depth,
                "deck2_enabled": player.deck2_enabled,
                "deck3_enabled": getattr(player, "deck3_enabled", True),
                "explicit_filter": player.explicit_filter
            }
        })
    else:
        return web.json_response({"error": f"Unknown action: {action}"}, status=400)

    return web.json_response({"status": "ok", "action": action})

async def api_queue_action(request: web.Request) -> web.Response:
    bot: discord.Client = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    guild, player = _get_player_and_guild(bot, guild_id)
    if not guild or not player:
        return web.json_response({"error": "Guild or player not found"}, status=404)

    try:
        data = await request.json()
    except Exception:
        data = {}

    op = request.match_info.get("op", "")
    q_list = list(player.queue)

    if op == "remove":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(q_list):
            removed = q_list.pop(idx)
            player.queue = type(player.queue)(q_list)
            asyncio.create_task(player.update_player_message())
            return web.json_response({"status": "ok", "removed": removed.title})
        return web.json_response({"error": "Index out of range"}, status=400)

    elif op == "clear":
        player.queue.clear()
        player._prewarmed_autoplay_track = None
        player._deck3_autoplay_track = None
        asyncio.create_task(player.update_player_message())
        return web.json_response({"status": "ok", "message": "Queue cleared"})

    elif op == "move":
        f_idx = int(data.get("from_index", -1))
        t_idx = int(data.get("to_index", -1))
        if 0 <= f_idx < len(q_list) and 0 <= t_idx < len(q_list):
            item = q_list.pop(f_idx)
            q_list.insert(t_idx, item)
            player.queue = type(player.queue)(q_list)
            asyncio.create_task(player.update_player_message())
            return web.json_response({"status": "ok"})
        return web.json_response({"error": "Invalid move indices"}, status=400)

    elif op == "play_now":
        idx = int(data.get("index", -1))
        if 0 <= idx < len(q_list):
            item = q_list.pop(idx)
            q_list.insert(0, item)
            player.queue = type(player.queue)(q_list)
            player.skip()
            return web.json_response({"status": "ok"})
        return web.json_response({"error": "Index out of range"}, status=400)

    return web.json_response({"error": f"Unknown queue operation: {op}"}, status=400)

async def api_search(request: web.Request) -> web.Response:
    q = request.query.get("q", "").strip()
    source = request.query.get("source", "auto").lower()
    if not q:
        return web.json_response({"results": []})

    results = []
    if source in ("auto", "all", "universal"):
        from app.services import spotify_service
        spot_match = spotify_service.match_spotify_url(q)
        if spot_match:
            ent_type, ent_id = spot_match
            spot_data = await asyncio.to_thread(spotify_service.fetch_spotify_entity, ent_type, ent_id)
            if spot_data and spot_data.get("tracks"):
                for it in spot_data["tracks"]:
                    dur = int(it.get("duration_seconds") or 0)
                    results.append({
                        "title": it.get("title", "Unknown"), "artist": it.get("artist", "Spotify"),
                        "album": it.get("album") or spot_data.get("name", "Spotify Collection"),
                        "duration": AudioTrack._format_duration(dur), "duration_seconds": dur,
                        "cover": it.get("cover") or spot_data.get("cover") or "", "source": "spotify"
                    })
                return web.json_response({"results": results})

        t_albs, t_dz, t_yt, t_it, t_sc = await asyncio.gather(
            asyncio.to_thread(deezer_api.search_albums, q, limit=4),
            asyncio.to_thread(deezer_api.search_tracks, q, limit=10),
            asyncio.to_thread(stream_service.search_ytmusic_catalog, q, limit=10),
            asyncio.to_thread(itunes_api.search_tracks, q, limit=6),
            asyncio.to_thread(stream_service.search_soundcloud_tracks, q, limit=4),
            return_exceptions=True
        )
        from app.utils.normalizer import is_junk_album
        raw_candidates = []
        for a in (t_albs if isinstance(t_albs, list) else []):
            raw_candidates.append({
                "id": str(a.get("id")), "title": a.get("title", "Unknown Album"),
                "artist": a.get("artist", "Unknown Artist"), "cover": a.get("cover") or "",
                "tracks_count": a.get("tracks_count", 0), "record_type": (a.get("record_type") or "Album").title(),
                "is_album": True, "source": "deezer", "duration_seconds": 0
            })
        dz_items = t_dz if isinstance(t_dz, list) else []
        yt_items = t_yt if isinstance(t_yt, list) else []
        it_items = t_it if isinstance(t_it, list) else []
        sc_items = t_sc if isinstance(t_sc, list) else []
        for items_list, src_name in ((dz_items, "deezer"), (yt_items, "ytmusic"), (it_items, "apple"), (sc_items, "soundcloud")):
            for it in items_list:
                dur = int(it.get("duration_seconds") or it.get("duration") or 0)
                raw_candidates.append({
                    "title": it.get("title", "Unknown"), "artist": it.get("artist", "Unknown"),
                    "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                    "duration_seconds": dur, "cover": it.get("cover") or it.get("cover_medium") or "",
                    "video_id": it.get("video_id") or it.get("url") or it.get("id", ""),
                    "source": src_name, "is_official": src_name in ("deezer", "ytmusic", "apple"), "is_album": False
                })

        q_tokens = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1]
        generic_descriptors = {"live", "remix", "remixes", "greatest hits", "the best of", "best of", "deluxe", "single", "album"}
        def _score(item):
            art = (item.get("artist") or "").lower()
            tit = (item.get("title") or "").lower()
            alb = (item.get("album") or "").lower()
            full = f"{art} - {tit} {alb}"
            dur = item.get("duration_seconds", 0)
            is_alb = item.get("is_album", False)
            if q_tokens and not any(tok in full for tok in q_tokens):
                return -9999
            if not is_alb and 0 < dur < 45:
                return -5000
            score = 0
            if art == q.lower():
                score += 700
            elif q.lower() in art:
                score += 500
            elif tit == q.lower() and q.lower() not in generic_descriptors:
                score += 450
            elif any(tok in art for tok in q_tokens):
                score += 250
            elif any(tok in tit for tok in q_tokens):
                score += 150
            if is_alb:
                if art == q.lower() or q.lower() in art:
                    score += 350
                elif tit == q.lower() and q.lower() not in generic_descriptors:
                    score += 200
                else:
                    score -= 400
            if is_junk_album(tit, art):
                score -= 400
            if item.get("source") in ("deezer", "ytmusic", "apple"):
                score += 50
            return score

        seen = set()
        ranked = sorted(raw_candidates, key=_score, reverse=True)
        for it in ranked:
            if _score(it) <= 0:
                continue
            k = f"{it.get('artist','').lower()} - {it.get('title','').lower()}"
            if k not in seen:
                seen.add(k)
                results.append(it)
    elif source in ("album", "albums"):
        albs = await asyncio.to_thread(deezer_api.search_albums, q, limit=25)
        for a in albs:
            results.append({
                "id": str(a.get("id")), "title": a.get("title", "Unknown Album"),
                "artist": a.get("artist", "Unknown Artist"), "cover": a.get("cover") or "",
                "tracks_count": a.get("tracks_count", 0), "record_type": (a.get("record_type") or "Album").title(),
                "is_album": True, "source": "deezer"
            })
    elif source in ("ytmusic", "youtube_music"):
        for it in await asyncio.to_thread(stream_service.search_ytmusic_catalog, q, limit=25):
            dur = int(it.get("duration_seconds") or 0)
            results.append({
                "title": it.get("title", "Unknown"), "artist": it.get("artist", "YouTube Music"),
                "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                "duration_seconds": dur, "cover": it.get("cover") or "",
                "video_id": it.get("video_id") or it.get("id", ""), "source": "ytmusic", "is_official": True
            })
    elif source in ("deezer", "dz"):
        for it in await asyncio.to_thread(deezer_api.search_tracks, q, limit=25):
            dur = int(it.get("duration", 0))
            results.append({
                "title": it.get("title", "Unknown"), "artist": it.get("artist", "Unknown"),
                "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                "duration_seconds": dur, "cover": it.get("cover") or it.get("cover_medium") or "", "source": "deezer"
            })
    elif source == "spotify":
        from app.services import spotify_service
        spot_match = spotify_service.match_spotify_url(q)
        if spot_match:
            ent_type, ent_id = spot_match
            spot_data = await asyncio.to_thread(spotify_service.fetch_spotify_entity, ent_type, ent_id)
            if spot_data and spot_data.get("tracks"):
                for it in spot_data["tracks"]:
                    dur = int(it.get("duration_seconds") or 0)
                    results.append({
                        "title": it.get("title", "Unknown"), "artist": it.get("artist", "Unknown"),
                        "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                        "duration_seconds": dur, "cover": it.get("cover") or spot_data.get("cover") or "", "source": "spotify"
                    })
        else:
            for it in await asyncio.to_thread(deezer_api.search_tracks, q, limit=25):
                dur = int(it.get("duration", 0))
                results.append({
                    "title": it.get("title", "Unknown"), "artist": it.get("artist", "Unknown"),
                    "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                    "duration_seconds": dur, "cover": it.get("cover") or it.get("cover_medium") or "", "source": "deezer"
                })
    elif source in ("musicbrainz", "mb"):
        from app.services import musicbrainz_api
        mb_items = await asyncio.to_thread(musicbrainz_api.search_release_groups, q, limit=25)
        if not mb_items:
            mb_res = await asyncio.to_thread(musicbrainz_api.get_artist_categorized_discography, q, limit=25)
            mb_items = mb_res.get("albums") or []
        for a in mb_items:
            results.append({
                "id": str(a.get("mbid") or a.get("mb_release_group_id") or a.get("id", "")),
                "title": a.get("title", "Unknown Release"),
                "artist": a.get("artist", q),
                "cover": a.get("cover") or "",
                "record_type": (a.get("category") or a.get("record_type") or "Album").title(),
                "is_album": True,
                "source": "musicbrainz"
            })
    elif source in ("charts", "billboard", "uktop40"):
        charts_data = await asyncio.to_thread(official_charts.get_live_official_charts, country="gb", limit=40)
        q_words = [w.lower() for w in q.split() if len(w) > 1]
        matches = []
        for c in (charts_data.get("tracks") or []):
            haystack = f"{c.get('title', '')} {c.get('artist', '')}".lower()
            if not q_words or any(w in haystack for w in q_words):
                dur = int(c.get("duration", 0))
                matches.append({
                    "title": c.get("title", "Unknown"), "artist": c.get("artist", "Chart Hit"),
                    "album": c.get("album", "Official Chart"), "duration": AudioTrack._format_duration(dur),
                    "duration_seconds": dur, "cover": c.get("cover") or "", "source": "charts"
                })
        if not matches:
            for c in (charts_data.get("tracks") or [])[:15]:
                dur = int(c.get("duration", 0))
                matches.append({
                    "title": c.get("title", "Unknown"), "artist": c.get("artist", "Chart Hit"),
                    "album": c.get("album", "Official Trending Chart"), "duration": AudioTrack._format_duration(dur),
                    "duration_seconds": dur, "cover": c.get("cover") or "", "source": "charts"
                })
        results.extend(matches)
    elif source in ("itunes", "apple"):
        for it in await asyncio.to_thread(itunes_api.search_tracks, q, limit=25):
            dur = int(it.get("duration", 0))
            results.append({
                "title": it.get("title", "Unknown"), "artist": it.get("artist", "Unknown"),
                "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                "duration_seconds": dur, "cover": it.get("cover") or "", "source": "apple"
            })
    elif source == "soundcloud":
        for it in await asyncio.to_thread(stream_service.search_soundcloud_tracks, q, limit=25):
            dur = int(it.get("duration_seconds") or 0)
            results.append({
                "title": it.get("title", "Unknown"), "artist": it.get("artist", "SoundCloud"),
                "album": "SoundCloud", "duration": AudioTrack._format_duration(dur),
                "duration_seconds": dur, "cover": it.get("cover") or "", "video_id": it.get("url"), "source": "soundcloud"
            })
    elif source == "youtube":
        for it in await asyncio.to_thread(stream_service.search_youtube_tracks, q, limit=25):
            raw_dur = it.get("duration", 0)
            dur_int = int(raw_dur) if (isinstance(raw_dur, (int, float)) or (isinstance(raw_dur, str) and str(raw_dur).isdigit())) else 0
            results.append({
                "title": it.get("title", "Unknown"), "artist": it.get("artist", "YouTube"),
                "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur_int),
                "duration_seconds": dur_int, "cover": it.get("cover") or "", "video_id": it.get("video_id") or it.get("id", ""), "source": "youtube"
            })
    else:
        for it in await asyncio.to_thread(deezer_api.search_tracks, q, limit=25):
            dur = int(it.get("duration", 0))
            results.append({
                "title": it.get("title", "Unknown"), "artist": it.get("artist", "Unknown"),
                "album": it.get("album", ""), "duration": AudioTrack._format_duration(dur),
                "duration_seconds": dur, "cover": it.get("cover") or it.get("cover_medium") or "", "source": "deezer"
            })

    search_log.info(f"[Web Hub Search] Query: '{q}' (Source: {source}) -> Found {len(results)} results")
    return web.json_response({"results": results})

async def api_play(request: web.Request) -> web.Response:
    bot: discord.Client = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    guild, player = _get_player_and_guild(bot, guild_id)
    if not guild or not player:
        return web.json_response({"error": "Guild or player not found"}, status=404)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    # Auto connect to voice if not connected
    if not player.is_connected:
        target_vc = None
        # Check if user specified a channel
        ch_id = data.get("voice_channel_id")
        if ch_id:
            target_vc = guild.get_channel(int(ch_id))
        if not target_vc:
            # Pick first voice channel that has human listeners
            for vc in guild.voice_channels:
                if any(not m.bot for m in vc.members):
                    target_vc = vc
                    break
        if not target_vc and len(guild.voice_channels) > 0:
            target_vc = guild.voice_channels[0]

        if target_vc and (isinstance(target_vc, (discord.VoiceChannel, discord.StageChannel)) or hasattr(target_vc, "connect")):
            try:
                await player.connect(target_vc)
            except Exception as e:
                log.warning(f"Voice auto-connect notice: {e}")
        elif not player.is_connected and not target_vc:
            return web.json_response({"error": "No voice channel found to join. Please connect to a voice channel or join from the hub."}, status=400)

    play_now = bool(data.get("play_now", False))

    album_id = data.get("album_id")
    if album_id:
        alb_data = None
        if str(album_id).isdigit():
            alb_data = await asyncio.to_thread(deezer_api.get_album, str(album_id))
        if not alb_data or not alb_data.get("tracks"):
            alb_title = data.get("title") or ""
            alb_artist = data.get("artist") or ""
            if alb_title:
                found = await asyncio.to_thread(deezer_api.search_albums, f"{alb_artist} {alb_title}".strip(), limit=1)
                if found:
                    alb_data = await asyncio.to_thread(deezer_api.get_album, str(found[0]["id"]))
        tracks = alb_data.get("tracks", []) if alb_data else []
        if not tracks and str(album_id).isdigit():
            tracks = await asyncio.to_thread(deezer_api.get_album_tracks, str(album_id))
        album_tracks = []
        for t in tracks:
            album_tracks.append(AudioTrack(
                title=t.get("title", "Unknown"),
                artist=t.get("artist", alb_data.get("artist", "Unknown")),
                album=alb_data.get("title", ""),
                duration_seconds=int(t.get("duration", 0)),
                cover_url=alb_data.get("cover_xl") or alb_data.get("cover_medium") or "",
                requested_by="Web Control Hub 🌐",
                source="deezer"
            ))
        if album_tracks:
            total = player.enqueue_many(album_tracks, at_front=play_now)
            if play_now and player.is_playing:
                player.skip()
            elif not player.is_playing:
                asyncio.create_task(player.play_next())
            return web.json_response({"status": "ok", "enqueued_count": len(album_tracks), "total": total, "position": total})

    query = data.get("query")
    if query and not data.get("title"):
        found = await asyncio.to_thread(deezer_api.search_tracks, query, limit=1)
        if found:
            data["title"] = found[0].get("title", query)
            data["artist"] = found[0].get("artist", "Unknown Artist")
            data["album"] = found[0].get("album", "")
            data["cover"] = found[0].get("cover_xl") or found[0].get("cover") or ""
            data["duration_seconds"] = int(found[0].get("duration", 0))

    track = AudioTrack(
        title=data.get("title", "Unknown Title"),
        artist=data.get("artist", "Unknown Artist"),
        album=data.get("album", ""),
        duration_seconds=int(data.get("duration_seconds", 0)),
        cover_url=data.get("cover", ""),
        video_id=data.get("video_id"),
        requested_by="Web Control Hub 🌐",
        source=data.get("source", "deezer")
    )

    pos = player.enqueue(track, at_front=play_now)
    if play_now and player.is_playing:
        player.skip()
    elif not player.is_playing:
        asyncio.create_task(player.play_next())

    return web.json_response({
        "status": "ok",
        "position": pos,
        "track": track.to_dict()
    })

async def api_charts(request: web.Request) -> web.Response:
    try:
        country = request.query.get("country", "gb").strip().lower()
        force_refresh = request.query.get("refresh", "0") in ("1", "true")
        data = await asyncio.to_thread(
            official_charts.get_live_official_charts,
            country=country,
            limit=50,
            force_refresh=force_refresh
        )
        raw_tracks = data.get("tracks", []) if isinstance(data, dict) else []
        chart_title = data.get("title", "Official Trending Charts") if isinstance(data, dict) else "Official Trending Charts"
        chart_badge = data.get("badge", "🔥 LIVE CHARTS") if isinstance(data, dict) else "🔥 LIVE CHARTS"
        is_album_chart = data.get("is_album_chart", False) if isinstance(data, dict) else False

        clean_tracks = []
        for t in raw_tracks:
            dur = int(t.get("duration", 0))
            clean_tracks.append({
                "id": t.get("id", ""),
                "position": t.get("position", len(clean_tracks) + 1),
                "title": t.get("title", "Unknown"),
                "artist": t.get("artist", "Unknown"),
                "album": t.get("album", ""),
                "duration": AudioTrack._format_duration(dur) if dur else "",
                "duration_seconds": dur,
                "cover": t.get("cover") or "",
                "source": "apple" if "itunes" in str(t.get("id", "")) or "official" in str(t.get("id", "")) else "deezer",
                "is_album": is_album_chart or t.get("is_album", False),
                "release_date": t.get("release_date", "")
            })
        return web.json_response({
            "charts": clean_tracks,
            "title": chart_title,
            "badge": chart_badge,
            "country": country
        })
    except Exception as e:
        log.warning(f"Error fetching charts for Web Hub: {e}")
        return web.json_response({"charts": [], "title": "Trending Charts", "badge": "🔥 CHARTS", "country": "gb"})

async def api_stream(request: web.Request) -> web.StreamResponse:
    bot: discord.Client = request.app["bot"]
    guild_id = request.match_info.get("guild_id", "")
    guild, player = _get_player_and_guild(bot, guild_id)
    if not guild or not player or not player.current_track:
        return web.Response(text="No active track playing", status=404)

    stream_url = getattr(player.current_track, "stream_url", None)
    vid = getattr(player.current_track, "video_id", None)
    if not stream_url and vid:
        s_url, _ = await asyncio.to_thread(stream_service.get_stream_info, vid, "auto")
        stream_url = s_url
        if player.current_track:
            player.current_track.stream_url = s_url

    if not stream_url:
        return web.Response(text="Stream URL unavailable", status=404)

    if hasattr(player, "get_progress"):
        elapsed, _ = player.get_progress()
    else:
        elapsed = 0

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'audio/mpeg',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Connection': 'keep-alive',
        }
    )
    await response.prepare(request)

    ua_header = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
    cmd = [
        'ffmpeg',
        '-headers', ua_header,
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_on_network_error', '1',
        '-reconnect_delay_max', '5',
        '-ss', str(max(0, elapsed)),
        '-i', stream_url,
        '-vn',
        '-acodec', 'libmp3lame',
        '-b:a', '192k',
        '-f', 'mp3',
        'pipe:1'
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL
    )

    try:
        while True:
            chunk = await proc.stdout.read(16384)
            if not chunk:
                break
            await response.write(chunk)
    except (asyncio.CancelledError, ConnectionResetError):
        pass
    finally:
        try:
            proc.kill()
            await proc.wait()
        except Exception:
            pass

    return response

async def api_logs(request: web.Request) -> web.Response:
    log_type = request.query.get("type", "all").lower().strip()
    logs_dir = os.path.join(os.path.dirname(WEB_DIR), "logs")
    file_map = {
        "bot": os.path.join(logs_dir, "bot.log"),
        "search": os.path.join(logs_dir, "search.log"),
        "audio": os.path.join(logs_dir, "audio.log"),
        "errors": os.path.join(logs_dir, "errors.log"),
    }
    lines = []
    if log_type in file_map:
        target_path = file_map[log_type]
        if os.path.exists(target_path):
            try:
                with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f.readlines()[-80:] if l.strip()]
            except Exception:
                pass
    else:
        # "all" - read from all categories and merge chronologically
        merged = []
        for p in file_map.values():
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        merged.extend([l.strip() for l in f.readlines()[-60:] if l.strip()])
                except Exception:
                    pass
        merged.sort()
        lines = merged[-80:]
    return web.json_response({"logs": lines, "type": log_type})

from web.album_api import api_album_tracks

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

def create_web_app(bot: discord.Client) -> web.Application:
    from web.album_api import static_cache_control_middleware
    app = web.Application(middlewares=[static_cache_control_middleware])
    app["bot"] = bot

    # Routes
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/status", api_status)
    app.router.add_get("/api/guilds", api_status)
    app.router.add_get("/api/guild/{guild_id}", api_guild_state)
    app.router.add_post("/api/guild/{guild_id}/control", api_control)
    app.router.add_post("/api/guild/{guild_id}/feedback", api_feedback)
    app.router.add_post("/api/guild/{guild_id}/queue/{op}", api_queue_action)
    app.router.add_get("/api/search", api_search)
    app.router.add_post("/api/guild/{guild_id}/play", api_play)
    app.router.add_get("/api/charts", api_charts)
    from web.album_api import api_dna, api_discography, api_timemachine, api_radio
    app.router.add_get("/api/discography", api_discography)
    app.router.add_get("/api/album/tracks", api_album_tracks)
    app.router.add_get("/api/guild/{guild_id}/dna", api_dna)
    app.router.add_get("/api/logs", api_logs)
    app.router.add_get("/api/timemachine", api_timemachine)
    app.router.add_get("/api/radio", api_radio)
    app.router.add_get("/api/guild/{guild_id}/stream", api_stream)

    if os.path.exists(STATIC_DIR):
        app.router.add_static("/static/", STATIC_DIR)

    return app

async def start_web_server(bot: discord.Client, host: str = "127.0.0.1", port: int = 8905) -> web.AppRunner:
    app = create_web_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    log.info(f"Web Control Hub online at http://{host}:{port}")
    return runner

async def stop_web_server(runner: web.AppRunner):
    if runner:
        try:
            await runner.cleanup()
            log.info("Web Control Hub stopped cleanly.")
        except Exception as e:
            log.warning(f"Error stopping Web Control Hub: {e}")
