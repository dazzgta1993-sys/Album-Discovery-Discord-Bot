"""Vibe Engine & Multi-Platform Autoplay Discovery.
Combines real-time algorithmic signals from YouTube Music, Deezer, Apple Music,
and Official Charts with intelligent anchor protection and no-kill-vibe filtering.
"""
import asyncio
import random
import re
from typing import Optional, TYPE_CHECKING
from app.utils.normalizer import is_junk_album, is_junk_artist
from app.services import deezer_api, stream_service, official_charts, itunes_api, musicbrainz_api
from core.logger import get_bot_logger

if TYPE_CHECKING:
    from core.player import AudioTrack, GuildPlayer

log = get_bot_logger("vibe_engine")

_guild_taste_store = {}

def get_guild_taste_profile(guild_id: int) -> dict:
    if guild_id not in _guild_taste_store:
        _guild_taste_store[guild_id] = {
            "likes": set(),
            "dislikes": set(),
            "track_dislikes": set(),
            "artist_scores": {}
        }
    store = _guild_taste_store[guild_id]
    return {
        "likes_count": len(store["likes"]),
        "dislikes_count": len(store["dislikes"]),
        "liked_artists": list(store["likes"]),
        "disliked_artists": list(store["dislikes"]),
        "disliked_tracks": list(store["track_dislikes"]),
        "artist_scores": dict(store["artist_scores"])
    }

def record_taste_feedback(guild_id: int, artist: str, title: str, vote: str) -> dict:
    art = str(artist or "").strip().lower()
    tit = str(title or "").strip().lower()
    if guild_id not in _guild_taste_store:
        get_guild_taste_profile(guild_id)
    store = _guild_taste_store[guild_id]
    
    if vote == "up":
        if art:
            store["likes"].add(art)
            store["dislikes"].discard(art)
            store["artist_scores"][art] = store["artist_scores"].get(art, 0) + 2
        log.info(f"[{guild_id}] Thumbs UP: '{artist}' boosted (+2 taste score)")
    elif vote == "down":
        if art:
            store["dislikes"].add(art)
            store["likes"].discard(art)
            store["artist_scores"][art] = store["artist_scores"].get(art, 0) - 10
        if tit:
            store["track_dislikes"].add(f"{art} - {tit}")
            store["track_dislikes"].add(tit)
        log.info(f"[{guild_id}] Thumbs DOWN: '{artist} - {title}' banished from session")
    
    return get_guild_taste_profile(guild_id)


def is_vibe_worthy(track_dict: dict, artist_fans: int = 0, clean_only: bool = False, disliked_artists: set = None, disliked_tracks: set = None) -> bool:
    """Shield against vibe killers: filters junk, skits, amateur spam, viral remixes, explicit tracks, and downvoted tracks."""
    title = track_dict.get("title", "")
    art = track_dict.get("artist") or track_dict.get("name", "")
    dur = track_dict.get("duration") or track_dict.get("duration_seconds", 0)
    rank = track_dict.get("rank", 0)

    # Thumbs Down / Disliked Filter
    if disliked_artists and str(art).strip().lower() in disliked_artists:
        return False
    if disliked_tracks:
        art_tit = f"{str(art).strip().lower()} - {str(title).strip().lower()}"
        if art_tit in disliked_tracks or str(title).strip().lower() in disliked_tracks:
            return False

    # 0. Explicit Content Shield (Radio Edit Clean)
    if clean_only:
        if track_dict.get("explicit_lyrics") or track_dict.get("trackExplicitness") == "explicit":
            return False
        tl = title.lower()
        if "explicit" in tl and "clean" not in tl:
            return False

    # 1. Reject junk, karaoke, tribute, sped-up, lullaby, hoodtrap, viral spam
    if is_junk_album(title, art) or is_junk_artist(art):
        return False

    combo_lower = f"{title} {art}".lower()
    for kw in ("hoodtrap", "hood trap", "type beat", "tiktok remix", "mashup", "earrape", "nightcore"):
        if kw in combo_lower:
            return False

    # 2. Dynamic Duration Guard: Reject skits (< 65s) and multi-hour podcasts/video essays (> 720s for unauthenticated).
    is_authenticated = bool(
        track_dict.get("isrc")
        or track_dict.get("mbid")
        or str(track_dict.get("source") or "").lower() in ("deezer", "spotify", "apple", "apple_music", "ytmusic")
    )
    max_duration = 1500 if is_authenticated else 480
    if dur > 0 and (dur < 65 or dur > max_duration):
        return False

    # 3. Quality threshold: avoid 0-listen amateur tracks
    if rank and rank < 80000:
        return False
    if artist_fans and artist_fans < 3000:
        return False

    # 4. Studio Autoplay Shield: Filter out live concert recordings, arena bootlegs, and live sessions
    # (Live music remains 100% playable when manually searched or queued).
    if str(art).strip().lower() != "live":
        _live_pat = re.compile(
            r"\b(live at|live from|live in|live on|live version|live recording|live acoustic|live session)\b|"
            r"[\(\[](?:19\d\d/|20\d\d/)?live\b|"
            r"\s*-\s*live\b",
            re.IGNORECASE
        )
        if _live_pat.search(title):
            return False
        alb = (track_dict.get("album") or track_dict.get("album_title") or "")
        if alb and _live_pat.search(alb):
            return False

    return True


async def fetch_next_vibe_track(player: 'GuildPlayer', seed_track: Optional['AudioTrack'] = None) -> Optional['AudioTrack']:
    """Multi-platform recommendation engine across YouTube Music, Deezer, and Apple Music."""
    from core.player import AudioTrack

    effective_track = seed_track or player.current_track or (player.history[-1] if getattr(player, 'history', None) else None)
    if not effective_track:
        try:
            charts_data = await asyncio.to_thread(official_charts.get_official_singles_chart, 10)
            if charts_data:
                top_c = charts_data[0]
                effective_track = AudioTrack(
                    title=top_c.get("title", "Popular Track"),
                    artist=top_c.get("artist", "Top Artists"),
                    album="Charts",
                    duration_seconds=0
                )
        except Exception as _ex:
            log.debug(f'Notice: {_ex}')
    if not effective_track:
        return None

    taste = get_guild_taste_profile(player.guild.id)
    disliked_artists = taste["disliked_artists"]
    disliked_tracks = taste["disliked_tracks"]
    liked_artists = taste["liked_artists"]

    try:
        current_art = effective_track.artist
        if current_art.lower() in ("youtube search", "youtube", "direct query"):
            parts = re.split(r"[-–—|/]| ft | feat ", effective_track.title, flags=re.IGNORECASE)
            for part in parts:
                cand = part.strip()
                if cand and len(cand) > 2 and cand.lower() not in ("hello", "official", "audio", "remix", "video"):
                    cand_artists = await asyncio.to_thread(deezer_api.search_artists, query=cand, limit=1)
                    if cand_artists:
                        current_art = cand_artists[0]["name"]
                        break

        # Split composite collaboration strings ('Calvin Harris, Ellie Goulding') into primary artist
        # so Deezer Artist Radio & Related Artists never hit a 0-fan composite stub profile.
        from app.services.discovery import split_collab_artists
        raw_anchor = (player.vibe_anchor_artist or "").strip()
        anchor_parts = split_collab_artists(raw_anchor)
        anchor_art = anchor_parts[0] if anchor_parts else raw_anchor

        seed_parts = split_collab_artists(current_art.strip())
        seed_art = seed_parts[0] if seed_parts else current_art.strip()
        target_art = seed_art

        if getattr(player, "is_anchor_locked", False):
            target_art = anchor_art or seed_art
        elif player.vibe_mode == "deep_dive":
            target_art = anchor_art or seed_art
        elif player.vibe_mode == "collabs":
            target_art = seed_art
        elif player.vibe_mode == "discovery":
            # Wild Discovery: continuous rabbit-hole exploration without snapping back to starting anchor!
            target_art = seed_art or anchor_art
        else:  # balanced (Smart Vibe)
            if anchor_art:
                drift_threshold = getattr(player, "vibe_drift_freq", 3)
                if player.consecutive_autoplay_count >= drift_threshold:
                    target_art = anchor_art
                elif player.consecutive_autoplay_count > 0 and random.random() < 0.6:
                    target_art = anchor_art
                else:
                    target_art = seed_art
            else:
                target_art = seed_art

        log.info(f"[{player.guild.name}] Multi-Platform DJ [Mode: {player.vibe_mode.upper()}] exploring for '{target_art}' (seed: '{effective_track.title}', chain: {player.consecutive_autoplay_count})...")
        clean_mode = getattr(player, "explicit_filter", "allow") == "clean_only"
        
        # Comprehensive blacklist across history, decks 1-3, and user queue
        recent_titles = {t.title.lower() for t in player.history}
        if player.current_track:
            recent_titles.add(player.current_track.title.lower())
        if player._prewarmed_autoplay_track:
            recent_titles.add(player._prewarmed_autoplay_track.title.lower())
        if player._deck3_autoplay_track:
            recent_titles.add(player._deck3_autoplay_track.title.lower())
        for qt in player.queue:
            recent_titles.add(qt.title.lower())
        if seed_track:
            recent_titles.add(seed_track.title.lower())

        cooldown_n = getattr(player, "artist_cooldown", 10)
        recent_artists = set()
        if cooldown_n > 0:
            for hist_t in list(player.history)[-cooldown_n:]:
                recent_artists.add(hist_t.artist.lower().strip())
                for cred in split_collab_artists(hist_t.artist):
                    recent_artists.add(cred.lower().strip())
        recent_artists.add(current_art.lower().strip())
        for cred in split_collab_artists(current_art):
            recent_artists.add(cred.lower().strip())
        if player._prewarmed_autoplay_track and player.vibe_mode != "deep_dive":
            recent_artists.add(player._prewarmed_autoplay_track.artist.lower().strip())
        if player._deck3_autoplay_track and player.vibe_mode != "deep_dive":
            recent_artists.add(player._deck3_autoplay_track.artist.lower().strip())

        failed_keys = getattr(player, "failed_tracks", set())

        # =====================================================================
        # 1. DEEP DIVE MODE (Same Artist Catalog via Deezer + Apple Music)
        # =====================================================================
        if player.vibe_mode == "deep_dive":
            artists = await asyncio.to_thread(deezer_api.search_artists, query=target_art, limit=1)
            if artists:
                aid = str(artists[0]["id"])
                top_limit = 30 if player.hit_depth == "deep_cuts" else 15
                artist_tracks = await asyncio.to_thread(deezer_api.get_artist_top_tracks, artist_id=aid, limit=top_limit)
                worthy_self = [
                    t for t in artist_tracks
                    if t.get("title", "").lower() not in recent_titles
                    and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)
                ]
                if worthy_self:
                    chosen = random.choice(worthy_self[:5] if player.hit_depth == "top_hits" else worthy_self)
                    track = AudioTrack(
                        title=chosen.get("title", "Unknown"),
                        artist=target_art,
                        album=chosen.get("album_title") or chosen.get("album", ""),
                        duration_seconds=chosen.get("duration", 0),
                        cover_url=chosen.get("cover") or "",
                        requested_by="Brain DJ 🧠 (Deep Dive)",
                        source="autoplay"
                    )
                    player.last_brain_decision = f"Deep Dive: Explored catalog of {target_art} -> {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track

        # =====================================================================
        # 2. COLLABS & IMMEDIATE CIRCLE MODE
        # =====================================================================
        elif player.vibe_mode == "collabs":
            artists = await asyncio.to_thread(deezer_api.search_artists, query=target_art, limit=1)
            if artists:
                aid = str(artists[0]["id"])
                related = await asyncio.to_thread(deezer_api.get_related_artists, artist_id=aid, limit=8)
                worthy_related = [r for r in related if r.get("name", "").lower() not in recent_artists]
                if worthy_related:
                    rel_chosen = random.choice(worthy_related[:4])
                    top_tracks = await asyncio.to_thread(deezer_api.get_artist_top_tracks, artist_id=rel_chosen["id"], limit=8)
                    worthy_top = [
                        t for t in top_tracks
                        if t.get("title", "").lower() not in recent_titles
                        and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)
                    ]
                    if worthy_top:
                        chosen_t = random.choice(worthy_top[:3])
                        track = AudioTrack(
                            title=chosen_t.get("title", "Unknown"),
                            artist=rel_chosen.get("name", "Related Artist"),
                            album=chosen_t.get("album_title") or chosen_t.get("album", ""),
                            duration_seconds=chosen_t.get("duration", 0),
                            cover_url=chosen_t.get("cover") or rel_chosen.get("picture_medium", ""),
                            requested_by="Brain DJ 🧠 (Circle)",
                            source="autoplay"
                        )
                        player.last_brain_decision = f"Circle Collab: Pivoted from {target_art} -> {track.artist} - {track.title}"
                        log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                        return track

        engine_src = getattr(player, "vibe_engine_source", "auto")

        # ---------------------------------------------------------------------
        # ENGINE: SOUNDCLOUD (Underground Mixes & Remixes Lock)
        # ---------------------------------------------------------------------
        if engine_src == "soundcloud":
            try:
                sc_tracks = await asyncio.to_thread(stream_service.search_soundcloud_tracks, f"{target_art} remix", limit=15)
                if not sc_tracks:
                    sc_tracks = await asyncio.to_thread(stream_service.search_soundcloud_tracks, target_art, limit=15)
                worthy_sc = [t for t in sc_tracks if t.get("title", "").lower() not in recent_titles and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)]
                if worthy_sc:
                    chosen = random.choice(worthy_sc[:5])
                    track = AudioTrack(
                        title=chosen.get("title", "Unknown"),
                        artist=chosen.get("artist", "SoundCloud Creator"),
                        album="SoundCloud",
                        duration_seconds=chosen.get("duration_seconds", 0),
                        cover_url=chosen.get("cover") or "",
                        video_id=chosen.get("video_id") or chosen.get("url"),
                        requested_by="Brain DJ 🧠 (SoundCloud)",
                        source="soundcloud"
                    )
                    player.last_brain_decision = f"SoundCloud: Picked underground vibe for {target_art} -> {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track
            except Exception as sc_err:
                log.debug(f"SoundCloud vibe notice: {sc_err}")

        # ---------------------------------------------------------------------
        # ENGINE: YOUTUBE VIDEO / LIVE (Concert, Sessions & Official Video Lock)
        # ---------------------------------------------------------------------
        if engine_src == "youtube":
            try:
                yt_vids = await asyncio.to_thread(stream_service.search_youtube_tracks, f"{target_art} official live", limit=12)
                if not yt_vids:
                    yt_vids = await asyncio.to_thread(stream_service.search_youtube_tracks, target_art, limit=12)
                worthy_ytv = [t for t in yt_vids if t.get("title", "").lower() not in recent_titles and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)]
                if worthy_ytv:
                    chosen = random.choice(worthy_ytv[:4])
                    raw_dur = chosen.get("duration", 0)
                    dur_i = int(raw_dur) if (isinstance(raw_dur, (int, float)) or (isinstance(raw_dur, str) and str(raw_dur).isdigit())) else 0
                    track = AudioTrack(
                        title=chosen.get("title", "Unknown"),
                        artist=chosen.get("artist", target_art),
                        album="YouTube Live",
                        duration_seconds=dur_i,
                        cover_url=chosen.get("cover") or "",
                        video_id=chosen.get("video_id") or chosen.get("id"),
                        requested_by="Brain DJ 🧠 (YouTube Video)",
                        source="youtube"
                    )
                    player.last_brain_decision = f"YouTube Video: Picked live track for {target_art} -> {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track
            except Exception as ytv_err:
                log.debug(f"YouTube video vibe notice: {ytv_err}")

        # ---------------------------------------------------------------------
        # ENGINE: MUSICBRAINZ TAXONOMY ARCHIVE (Deep Canonical Discography Lock)
        # ---------------------------------------------------------------------
        if engine_src == "musicbrainz":
            try:
                mb_disco = await asyncio.to_thread(musicbrainz_api.get_artist_categorized_discography, target_art, limit=30)
                mb_albums = mb_disco.get("albums", []) if isinstance(mb_disco, dict) else []
                if mb_albums:
                    studio_alb = [a for a in mb_albums if a.get("category") == "Studio Albums" or a.get("primary_type") == "Album"]
                    pool_alb = studio_alb or mb_albums
                    sel_alb = random.choice(pool_alb[:8])
                    alb_title = sel_alb.get("title", "")
                    if alb_title:
                        mb_search = await asyncio.to_thread(itunes_api.search_tracks, query=f"{target_art} {alb_title}", limit=8)
                        worthy_mb = [t for t in mb_search if t.get("title", "").lower() not in recent_titles and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)]
                        if worthy_mb:
                            chosen = random.choice(worthy_mb[:4])
                            track = AudioTrack(
                                title=chosen.get("title", "Unknown"),
                                artist=chosen.get("artist", target_art),
                                album=chosen.get("album", alb_title),
                                duration_seconds=chosen.get("duration", 0),
                                cover_url=chosen.get("cover") or "",
                                requested_by="Brain DJ 🧠 (MusicBrainz)",
                                source="autoplay"
                            )
                            player.last_brain_decision = f"MusicBrainz Archive: {target_art} [{alb_title}] -> {track.title}"
                            log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                            return track
            except Exception as mb_err:
                log.debug(f"MusicBrainz vibe discovery notice: {mb_err}")

        # ---------------------------------------------------------------------
        # ENGINE: OFFICIAL CHARTS (Radio Top 40 & Hit Rotation Lock)
        # ---------------------------------------------------------------------
        if engine_src == "charts":
            try:
                charts_data = await asyncio.to_thread(official_charts.get_live_official_charts, country="gb", limit=40)
                chart_items = (charts_data.get("tracks") or charts_data.get("items", [])) if isinstance(charts_data, dict) else []
                worthy_charts = [c for c in chart_items if c.get("title", "").lower() not in recent_titles and not is_junk_album(c.get("title", ""), c.get("artist", ""))]
                if worthy_charts:
                    chart_pick = random.choice(worthy_charts[:10])
                    track = AudioTrack(
                        title=chart_pick.get("title", "Unknown"),
                        artist=chart_pick.get("artist", "Chart Artist"),
                        album=chart_pick.get("album", "Official Chart"),
                        duration_seconds=chart_pick.get("duration", 0),
                        cover_url=chart_pick.get("cover") or "",
                        requested_by="Brain DJ 🧠 (Official Chart)",
                        source="autoplay"
                    )
                    player.last_brain_decision = f"Official Chart: Locked hit {track.artist} - {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track
            except Exception as ch_err:
                log.debug(f"Official chart lock notice: {ch_err}")

                # =====================================================================
        # 3. DEEZER SMART ARTIST RADIO & CURATED AFFINITY (PRIMARY FOR AUTO & DEEZER)
        # =====================================================================
        if engine_src in ("auto", "deezer"):
            try:
                artists = await asyncio.to_thread(deezer_api.search_artists, query=target_art, limit=1)
                if artists:
                    aid = str(artists[0]["id"])
                    radio_tracks = await asyncio.to_thread(deezer_api.get_artist_radio, artist_id=aid, limit=30)
                    worthy_radio = [
                        t for t in radio_tracks
                        if t.get("title", "").lower() not in recent_titles
                        and (t.get("artist") or "").lower() not in recent_artists
                        and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)
                    ]
                    if worthy_radio:
                        worthy_radio.sort(key=lambda x: x.get("rank", 0), reverse=True)
                        pool_limit = 12 if getattr(player, 'vibe_mode', '') == 'discovery' else 6
                        chosen = random.choice(worthy_radio[:pool_limit])
                        track = AudioTrack(
                            title=chosen.get("title", "Unknown"),
                            artist=chosen.get("artist", target_art),
                            album=chosen.get("album", ""),
                            duration_seconds=chosen.get("duration", 0),
                            cover_url=chosen.get("cover") or "",
                            requested_by="Brain DJ 🧠 (Deezer Vibe)",
                            source="autoplay"
                        )
                        player.last_brain_decision = f"Deezer Curated Radio: Anchored from {target_art} -> {track.artist} - {track.title}"
                        log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                        return track

                    # Related Artists fallback on Deezer
                    related = await asyncio.to_thread(deezer_api.get_related_artists, artist_id=aid, limit=12)
                    worthy_related = [r for r in related if r.get("name", "").lower() not in recent_artists and (r.get("fans", 0) >= 3000 or r.get("nb_fan", 0) >= 3000)]
                    if worthy_related:
                        rel_chosen = random.choice(worthy_related[:4])
                        top_tracks = await asyncio.to_thread(deezer_api.get_artist_top_tracks, artist_id=rel_chosen["id"], limit=6)
                        worthy_top = [t for t in top_tracks if t.get("title", "").lower() not in recent_titles and is_vibe_worthy(t, artist_fans=rel_chosen.get("fans", 0))]
                        if worthy_top:
                            chosen_t = random.choice(worthy_top[:3])
                            track = AudioTrack(
                                title=chosen_t.get("title", "Unknown"),
                                artist=rel_chosen.get("name", "Related Artist"),
                                album=chosen_t.get("album", ""),
                                duration_seconds=chosen_t.get("duration", 0),
                                cover_url=chosen_t.get("cover") or rel_chosen.get("picture_medium", ""),
                                requested_by="Brain DJ 🧠 (Deezer Related)",
                                source="autoplay"
                            )
                            player.last_brain_decision = f"Deezer Related Circle: Matched {track.artist} - {track.title}"
                            log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                            return track
            except Exception as dz_err:
                log.debug(f"Deezer curated vibe notice: {dz_err}")

        # =====================================================================
        # 4. YOUTUBE MUSIC ALGORITHMIC RADIO (ACTIVE IN AUTO FALLBACK & YTMUSIC LOCK)
        # =====================================================================
        if engine_src in ("auto", "ytmusic") and (player.vibe_mode in ("balanced", "discovery") or engine_src == "ytmusic"):
            try:
                # If target_art is anchor_art, query for anchor artist to prevent rabbit-hole drift!
                if anchor_art and target_art.lower() == anchor_art.lower():
                    ytm_query = f"{anchor_art} official music".strip()
                    curr_vid = ""
                else:
                    curr_vid = getattr(effective_track, "video_id", "") or ""
                    ytm_query = f"{effective_track.artist} {effective_track.title}".strip()
                
                yt_radio = await asyncio.to_thread(stream_service.get_ytmusic_related_tracks, video_id=curr_vid, query=ytm_query, limit=20)
                cooldown_n = getattr(player, "artist_cooldown", 10)
                worthy_yt = [
                    t for t in yt_radio
                    if t.get("title", "").lower() not in recent_titles
                    and f"{t.get('artist', '').lower().strip()} - {t.get('title', '').lower().strip()}" not in failed_keys
                    and (t.get("artist", "").lower().strip() not in recent_artists if cooldown_n > 0 else True)
                    and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)
                ]
                if not worthy_yt:
                    worthy_yt = [t for t in yt_radio if t.get("title", "").lower() not in recent_titles and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)]
                if worthy_yt:
                    yt_pool = 12 if getattr(player, 'vibe_mode', '') == 'discovery' else 6
                    chosen = random.choice(worthy_yt[:yt_pool])
                    track = AudioTrack(
                        title=chosen.get("title", "Unknown"),
                        artist=chosen.get("artist", "YouTube Music Radio"),
                        album=chosen.get("album", ""),
                        duration_seconds=chosen.get("duration_seconds", 0),
                        cover_url=chosen.get("cover") or "",
                        video_id=chosen.get("video_id"),
                        requested_by="Brain DJ 🧠 (YouTube Music Radio)",
                        source="autoplay"
                    )
                    player.last_brain_decision = f"YT Music Radio: Seeded from {effective_track.title} -> {track.artist} - {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track
            except Exception as ytm_err:
                log.debug(f"YTMusic autoplay discovery notice: {ytm_err}")

        # =====================================================================
        # 5. APPLE MUSIC & SPOTIFY CATALOG DISCOVERY (ACTIVE IN AUTO, SPOTIFY, APPLE)
        # =====================================================================
        if engine_src in ("auto", "spotify", "apple"):
            try:
                itunes_tracks = await asyncio.to_thread(itunes_api.search_tracks, query=target_art, limit=15)
                worthy_apple = [t for t in itunes_tracks if t.get("title", "").lower() not in recent_titles and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)]
                if worthy_apple:
                    chosen = random.choice(worthy_apple[:4])
                    brand_src = "Spotify" if engine_src == "spotify" else "Apple Music"
                    track = AudioTrack(
                        title=chosen.get("title", "Unknown"),
                        artist=chosen.get("artist", target_art),
                        album=chosen.get("album", ""),
                        duration_seconds=chosen.get("duration", 0),
                        cover_url=chosen.get("cover") or "",
                        requested_by=f"Brain DJ 🧠 ({brand_src})",
                        source="autoplay"
                    )
                    player.last_brain_decision = f"{brand_src}: Injected hit for {target_art} -> {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track
            except Exception as apple_err:
                log.debug(f"Apple/Spotify autoplay notice: {apple_err}")

        # =====================================================================
        # 6. OFFICIAL CHARTS INJECTION (SMART CASCADE ANCHOR)
        # =====================================================================
        if engine_src == "auto":
            try:
                charts_data = await asyncio.to_thread(official_charts.get_live_official_charts, country="gb", limit=30)
                chart_items = (charts_data.get("tracks") or charts_data.get("items", [])) if isinstance(charts_data, dict) else []
                worthy_charts = [
                    c for c in chart_items
                    if c.get("title", "").lower() not in recent_titles
                    and c.get("artist", "").lower() not in recent_artists
                    and not is_junk_album(c.get("title", ""), c.get("artist", ""))
                ]
                if worthy_charts:
                    chart_pick = random.choice(worthy_charts[:10])
                    track = AudioTrack(
                        title=chart_pick.get("title", "Unknown"),
                        artist=chart_pick.get("artist", "Chart Artist"),
                        album=chart_pick.get("album", "Official Chart"),
                        duration_seconds=chart_pick.get("duration", 0),
                        cover_url=chart_pick.get("cover") or "",
                        requested_by="Autoplay DJ 🎛️ (Official Chart)",
                        source="autoplay"
                    )
                    player.last_brain_decision = f"Official Chart: Injected hit {track.artist} - {track.title}"
                    log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                    return track
            except Exception as chart_err:
                log.debug(f"Official chart autoplay injection notice: {chart_err}")

        # =====================================================================
        # 7. FALLBACK TO ANCHOR ARTIST CLASSIC REPERTOIRE
        # =====================================================================
        fallback_target = player.vibe_anchor_artist or current_art
        tracks = await asyncio.to_thread(deezer_api.search_tracks, query=fallback_target, limit=20)
        if tracks:
            candidates = [
                t for t in tracks
                if t.get("title", "").lower() not in recent_titles
                and f"{t.get('artist', '').lower().strip()} - {t.get('title', '').lower().strip()}" not in failed_keys
                and is_vibe_worthy(t, clean_only=clean_mode, disliked_artists=disliked_artists, disliked_tracks=disliked_tracks)
            ]
            if candidates:
                chosen = random.choice(candidates[:5])
                track = AudioTrack(
                    title=chosen.get("title", ""),
                    artist=chosen.get("artist", fallback_target),
                    album=chosen.get("album", ""),
                    duration_seconds=chosen.get("duration", 0),
                    cover_url=chosen.get("cover") or chosen.get("cover_medium") or "",
                    requested_by="Autoplay DJ 🎛️ (Anchor)",
                    source="autoplay"
                )
                player.last_brain_decision = f"Anchor Fallback: Selected {track.artist} - {track.title}"
                log.info(f"[{player.guild.name}] {player.last_brain_decision}")
                return track

    except Exception as e:
        log.error(f"[{player.guild.name}] Autoplay Vibe Engine critical exception: {e}", exc_info=True)

    return None
