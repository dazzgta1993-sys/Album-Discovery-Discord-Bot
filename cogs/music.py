import asyncio
import re
import discord
from discord import app_commands
from discord.ext import commands

from app.services import deezer_api, stream_service, itunes_api
from core.config import EMBED_COLOR, MAX_QUEUE_DISPLAY
from core.player import AudioTrack
from core.logger import get_bot_logger

log = get_bot_logger("cogs.music")

class MusicCog(commands.Cog, name="Music"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_notice(self, interaction: discord.Interaction, embed: discord.Embed = None, message: str = None, delay: float = 4.0):
        """Sends an auto-expiring notification that automatically vanishes after `delay` seconds, keeping chat 100% clean."""
        try:
            if interaction.response.is_done():
                msg = await interaction.followup.send(content=message, embed=embed)
                if msg and hasattr(msg, "delete"):
                    try:
                        await msg.delete(delay=delay)
                    except Exception:
                        pass
            else:
                await interaction.response.send_message(content=message, embed=embed, delete_after=delay)
        except Exception:
            pass

    async def _send_error(self, interaction: discord.Interaction, message: str):
        await self._send_notice(interaction, message=message, delay=5.0)

    async def _ensure_voice(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await self._send_error(interaction, "❌ You must be connected to a voice channel first!")
            return False

        player = self.bot.player_manager.get_player(interaction.guild)
        voice_channel = interaction.user.voice.channel
        
        if not player.is_connected or (player.voice_client and player.voice_client.channel.id != voice_channel.id):
            connected = await player.connect(voice_channel, text_channel=interaction.channel)
            if not connected:
                await self._send_error(interaction, "❌ Failed to connect to your voice channel.")
                return False
        return True

    @app_commands.command(name="play", description="Search & stream official studio tracks, albums, or direct links")
    @app_commands.describe(
        query="Song title, artist, Deezer URL, or YouTube URL",
        source="Music service to query (Default: Auto Studio Match)"
    )
    @app_commands.choices(source=[
        app_commands.Choice(name="🌐 Multi-Engine Auto (Universal Match)", value="auto"),
        app_commands.Choice(name="🔴 YouTube Music (Official Studio)", value="ytmusic"),
        app_commands.Choice(name="▶️ YouTube Video & Live", value="youtube"),
        app_commands.Choice(name="🟣 Deezer Studio Masters", value="deezer"),
        app_commands.Choice(name="🟢 Spotify Catalog Match", value="spotify"),
        app_commands.Choice(name="🍎 Apple Music (Lossless Catalog)", value="apple"),
        app_commands.Choice(name="🟠 SoundCloud (Underground & Mixes)", value="soundcloud"),
        app_commands.Choice(name="🏛️ MusicBrainz Discography Match", value="musicbrainz"),
        app_commands.Choice(name="📊 Official Charts Top 40", value="charts"),
    ])
    async def play(self, interaction: discord.Interaction, query: str, source: app_commands.Choice[str] = None):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel
        q = re.sub(r"^(?:/(?:play|playnow)\s+|!(?:play|playnow)\s+)+", "", query.strip(), flags=re.IGNORECASE).strip()

        # Check for direct YouTube video URL
        yt_match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", q)
        if yt_match:
            vid = yt_match.group(1)
            track = AudioTrack(
                title=f"YouTube Track [{vid}]",
                cover_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                artist="YouTube",
                video_id=vid,
                requested_by=interaction.user.display_name,
                source="youtube"
            )
            pos = player.enqueue(track)
            embed = discord.Embed(
                title="➕ YouTube Track Queued",
                description=f"**[{track.title}](https://www.youtube.com/watch?v={vid})**",
                color=EMBED_COLOR
            )
            embed.set_thumbnail(url=track.cover_url)
            embed.set_footer(text=f"Position #{pos} in queue | Requested by {interaction.user.display_name}")
            await self._send_notice(interaction, embed=embed, delay=4.0)
            if not player.is_playing:
                asyncio.create_task(player.play_next())
            return

        # Check for Spotify Track, Album, or Playlist URL
        from app.services import spotify_service
        spot_match = spotify_service.match_spotify_url(q)
        if spot_match:
            ent_type, ent_id = spot_match
            spot_data = await asyncio.to_thread(spotify_service.fetch_spotify_entity, ent_type, ent_id)
            if spot_data and spot_data.get("tracks"):
                sp_tracks = spot_data["tracks"]
                q_tracks = []
                for t in sp_tracks:
                    dur = t.get("duration_seconds", 0)
                    q_tracks.append(AudioTrack(
                        title=t.get("title", "Unknown"),
                        artist=t.get("artist", "Unknown"),
                        album=t.get("album", ""),
                        duration_seconds=dur,
                        duration_str=AudioTrack._format_duration(dur) if dur > 0 else "",
                        cover_url=t.get("cover") or spot_data.get("cover") or "",
                        requested_by=interaction.user.display_name,
                        source="spotify"
                    ))
                total = player.enqueue_many(q_tracks)
                embed = discord.Embed(
                    title=f"🟢 Spotify {spot_data.get('type', 'Collection').title()} Queued",
                    description=f"Added **{len(q_tracks)} track(s)** from **{spot_data.get('name')}**",
                    color=discord.Color.from_rgb(30, 215, 96)
                )
                if spot_data.get("cover"):
                    embed.set_thumbnail(url=spot_data["cover"])
                embed.set_footer(text=f"Total in queue: {total} | Requested by {interaction.user.display_name}")
                await self._send_notice(interaction, embed=embed, delay=4.0)
                if not player.is_playing:
                    asyncio.create_task(player.play_next())
                return

        # Check for SoundCloud URL
        if "soundcloud.com/" in q.lower():
            sc_items = await asyncio.to_thread(stream_service.resolve_soundcloud_url, q)
            if sc_items:
                q_tracks = []
                for t in sc_items:
                    dur = t.get("duration_seconds", 0)
                    q_tracks.append(AudioTrack(
                        title=t.get("title", "Unknown"),
                        artist=t.get("artist", "SoundCloud"),
                        album="SoundCloud",
                        duration_seconds=dur,
                        duration_str=AudioTrack._format_duration(dur) if dur > 0 else "",
                        cover_url=t.get("cover") or "",
                        video_id=t.get("url"),
                        requested_by=interaction.user.display_name,
                        source="soundcloud"
                    ))
                total = player.enqueue_many(q_tracks)
                embed = discord.Embed(
                    title="🟠 SoundCloud Track Queued",
                    description=f"Added **{len(q_tracks)} track(s)** from SoundCloud\nFirst: **{q_tracks[0].artist} — {q_tracks[0].title}**",
                    color=discord.Color.from_rgb(255, 85, 0)
                )
                if q_tracks[0].cover_url:
                    embed.set_thumbnail(url=q_tracks[0].cover_url)
                embed.set_footer(text=f"Total in queue: {total} | Requested by {interaction.user.display_name}")
                await self._send_notice(interaction, embed=embed, delay=4.0)
                if not player.is_playing:
                    asyncio.create_task(player.play_next())
                return

        # Check for Deezer album URL
        album_match = re.search(r"deezer\.com/(?:[a-zA-Z]{2}/)?album/(\d+)", q)
        if album_match:
            album_id = int(album_match.group(1))
            album_data = await asyncio.to_thread(deezer_api.get_album, album_id)
            if album_data and album_data.get("tracks"):
                tracks = album_data.get("tracks", [])
                audio_tracks = []
                for t in tracks:
                    audio_tracks.append(AudioTrack(
                        title=t.get("title", "Unknown"),
                        artist=t.get("artist", album_data.get("artist", "Unknown")),
                        album=album_data.get("title", ""),
                        duration_seconds=t.get("duration", 0),
                        cover_url=album_data.get("cover_xl") or album_data.get("cover_medium") or "",
                        requested_by=interaction.user.display_name
                    ))
                total = player.enqueue_many(audio_tracks)
                embed = discord.Embed(
                    title="📀 Album Queued",
                    description=f"Added **{len(audio_tracks)} tracks** from **{album_data.get('title')}** by **{album_data.get('artist')}**",
                    color=EMBED_COLOR
                )
                if album_data.get("cover_medium"):
                    embed.set_thumbnail(url=album_data["cover_medium"])
                embed.set_footer(text=f"Total in queue: {total}")
                await self._send_notice(interaction, embed=embed, delay=4.0)
                if not player.is_playing:
                    asyncio.create_task(player.play_next())
                return

        # Check for Deezer track URL
        track_match = re.search(r"deezer\.com/(?:[a-zA-Z]{2}/)?track/(\d+)", q)
        if track_match:
            track_id = int(track_match.group(1))
            t_data = await asyncio.to_thread(deezer_api.get_track, track_id)
            if t_data:
                track = AudioTrack(
                    title=t_data.get("title", "Unknown"),
                    artist=t_data.get("artist", "Unknown"),
                    album=t_data.get("album", ""),
                    duration_seconds=t_data.get("duration", 0),
                    cover_url=t_data.get("cover_xl") or t_data.get("cover_medium") or "",
                    requested_by=interaction.user.display_name
                )
                was_playing = player.is_playing
                pos = player.enqueue(track)
                if was_playing:
                    embed = discord.Embed(
                        title="➕ Track Queued",
                        description=f"**{track.artist} — {track.title}**",
                        color=EMBED_COLOR
                    )
                    if track.cover_url:
                        embed.set_thumbnail(url=track.cover_url)
                    embed.set_footer(text=f"Position #{pos} in queue")
                    await self._send_notice(interaction, embed=embed, delay=4.0)
                else:
                    try:
                        await interaction.delete_original_response()
                    except Exception:
                        pass
                    asyncio.create_task(player.play_next())
                return

        # Service-Selected Search Resolution with Strict Clutter Filtering
        chosen_src = source.value if source else "auto"
        track = None

        if chosen_src == "soundcloud":
            sc_results = await asyncio.to_thread(stream_service.search_soundcloud_tracks, query=q, limit=1)
            if sc_results:
                b = sc_results[0]
                track = AudioTrack(
                    title=b.get("title", q),
                    artist=b.get("artist", "SoundCloud"),
                    album="SoundCloud",
                    duration_seconds=b.get("duration_seconds", 0),
                    cover_url=b.get("cover") or "",
                    video_id=b.get("url"),
                    requested_by=interaction.user.display_name,
                    source="soundcloud"
                )

        elif chosen_src == "spotify":
            spot_match = spotify_service.match_spotify_url(q)
            if spot_match:
                ent_type, ent_id = spot_match
                spot_data = await asyncio.to_thread(spotify_service.fetch_spotify_entity, ent_type, ent_id)
                if spot_data and spot_data.get("tracks"):
                    b = spot_data["tracks"][0]
                    track = AudioTrack(
                        title=b.get("title", q),
                        artist=b.get("artist", "Spotify"),
                        album=b.get("album", ""),
                        duration_seconds=b.get("duration_seconds", 0),
                        cover_url=b.get("cover") or spot_data.get("cover") or "",
                        requested_by=interaction.user.display_name,
                        source="spotify"
                    )

        elif chosen_src == "ytmusic":
            ytm_results = await asyncio.to_thread(stream_service.search_ytmusic_catalog, query=q, limit=1)
            if ytm_results:
                b = ytm_results[0]
                track = AudioTrack(
                    title=b.get("title", q),
                    artist=b.get("artist", "YouTube Music"),
                    album=b.get("album", ""),
                    duration_seconds=b.get("duration_seconds", 0),
                    cover_url=b.get("cover") or "",
                    video_id=b.get("video_id"),
                    requested_by=interaction.user.display_name,
                    source="ytmusic"
                )

        elif chosen_src == "apple":
            apple_results = await asyncio.to_thread(itunes_api.search_tracks, query=q, limit=1)
            if apple_results:
                b = apple_results[0]
                track = AudioTrack(
                    title=b.get("title", q),
                    artist=b.get("artist", "Unknown"),
                    album=b.get("album", ""),
                    duration_seconds=int(b.get("duration", 0)),
                    cover_url=b.get("cover") or "",
                    requested_by=interaction.user.display_name,
                    source="apple"
                )

        elif chosen_src == "youtube":
            yt_results = await asyncio.to_thread(stream_service.search_youtube_tracks, query=q, limit=1)
            if yt_results:
                b = yt_results[0]
                track = AudioTrack(
                    title=b.get("title", q),
                    artist=b.get("artist", "YouTube"),
                    album=b.get("album", ""),
                    duration_seconds=int(b.get("duration", 0)),
                    cover_url=b.get("cover") or "",
                    video_id=b.get("video_id"),
                    requested_by=interaction.user.display_name,
                    source="youtube"
                )

        elif chosen_src == "musicbrainz":
            from app.services import musicbrainz_api
            mb_data = await asyncio.to_thread(musicbrainz_api.get_artist_categorized_discography, q, limit=15)
            mb_albs = mb_data.get("albums", []) if isinstance(mb_data, dict) else []
            if mb_albs:
                top_rg = mb_albs[0]
                rg_title = top_rg.get("title", q)
                dz_match = await asyncio.to_thread(deezer_api.search_tracks, query=f"{q} {rg_title}", limit=1)
                if dz_match:
                    b = dz_match[0]
                    track = AudioTrack(
                        title=b.get("title", rg_title),
                        artist=b.get("artist", q),
                        album=rg_title,
                        duration_seconds=b.get("duration", 0),
                        cover_url=b.get("cover_xl") or b.get("cover") or "",
                        requested_by=interaction.user.display_name,
                        source="musicbrainz"
                    )

        elif chosen_src == "charts":
            from app.services import official_charts
            charts_data = await asyncio.to_thread(official_charts.get_live_official_charts, country="gb", limit=30)
            ch_list = charts_data.get("tracks", []) if isinstance(charts_data, dict) else []
            cand = next((c for c in ch_list if q.lower() in (c.get("title","") + " " + c.get("artist","")).lower()), ch_list[0] if ch_list else None)
            if cand:
                track = AudioTrack(
                    title=cand.get("title", q),
                    artist=cand.get("artist", "Chart Artist"),
                    album=cand.get("album", "Official Chart"),
                    duration_seconds=cand.get("duration", 0),
                    cover_url=cand.get("cover") or "",
                    requested_by=interaction.user.display_name,
                    source="charts"
                )

        if not track:
            # Default / Auto: Try Deezer Studio Master first
            results = await asyncio.to_thread(deezer_api.search_tracks, query=q, limit=5)
            if results:
                best = results[0]
                track = AudioTrack(
                    title=best.get("title", q),
                    artist=best.get("artist", "Unknown"),
                    album=best.get("album", ""),
                    duration_seconds=best.get("duration", 0),
                    cover_url=best.get("cover_xl") or best.get("cover") or best.get("cover_medium") or "",
                    requested_by=interaction.user.display_name
                )
            else:
                # Fallback to YouTube Music Official Topic Catalog
                ytm_fallback = await asyncio.to_thread(stream_service.search_ytmusic_catalog, query=q, limit=1)
                if ytm_fallback:
                    b = ytm_fallback[0]
                    track = AudioTrack(
                        title=b.get("title", q),
                        artist=b.get("artist", "YouTube Music"),
                        album=b.get("album", ""),
                        duration_seconds=b.get("duration_seconds", 0),
                        cover_url=b.get("cover") or "",
                        video_id=b.get("video_id"),
                        requested_by=interaction.user.display_name,
                        source="ytmusic"
                    )
                else:
                    track = AudioTrack(
                        title=q,
                        artist="Direct Query",
                        album="",
                        requested_by=interaction.user.display_name,
                        source="youtube"
                    )

        was_playing = player.is_playing
        pos = player.enqueue(track)
        if was_playing:
            embed = discord.Embed(
                title="➕ Track Queued",
                description=f"**{track.artist} — {track.title}**" + (f"\n*Album:* {track.album}" if track.album else ""),
                color=EMBED_COLOR
            )
            if track.cover_url:
                embed.set_thumbnail(url=track.cover_url)
            embed.set_footer(text=f"Position #{pos} in queue | Requested by {interaction.user.display_name}")
            await self._send_notice(interaction, embed=embed, delay=4.0)
        else:
            try:
                await interaction.delete_original_response()
            except Exception:
                pass
            asyncio.create_task(player.play_next())


    @app_commands.command(name="playnow", description="Instantly play a track right now")
    @app_commands.describe(
        query="Song title, artist, or direct link to play right now",
        source="Music service to query (Default: Auto Studio Match)"
    )
    @app_commands.choices(source=[
        app_commands.Choice(name="🌐 Multi-Engine Auto (Universal Match)", value="auto"),
        app_commands.Choice(name="🔴 YouTube Music (Official Studio)", value="ytmusic"),
        app_commands.Choice(name="▶️ YouTube Video & Live", value="youtube"),
        app_commands.Choice(name="🟣 Deezer Studio Masters", value="deezer"),
        app_commands.Choice(name="🟢 Spotify Catalog Match", value="spotify"),
        app_commands.Choice(name="🍎 Apple Music (Lossless Catalog)", value="apple"),
        app_commands.Choice(name="🟠 SoundCloud (Underground & Mixes)", value="soundcloud"),
        app_commands.Choice(name="🏛️ MusicBrainz Discography Match", value="musicbrainz"),
        app_commands.Choice(name="📊 Official Charts Top 40", value="charts"),
    ])
    async def playnow(self, interaction: discord.Interaction, query: str, source: app_commands.Choice[str] = None):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel
        q = re.sub(r"^(?:/(?:play|playnow)\s+|!(?:play|playnow)\s+)+", "", query.strip(), flags=re.IGNORECASE).strip()

        chosen_src = source.value if source else "auto"
        track = None

        # Check for direct YouTube video URL
        yt_match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", q)
        if yt_match:
            vid = yt_match.group(1)
            track = AudioTrack(
                title=f"YouTube Track [{vid}]",
                cover_url=f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                artist="YouTube",
                video_id=vid,
                requested_by=interaction.user.display_name,
                source="youtube"
            )
        elif chosen_src == "ytmusic":
            yt_res = await asyncio.to_thread(stream_service.search_ytmusic_catalog, query=q, limit=1)
            if yt_res:
                b = yt_res[0]
                track = AudioTrack(
                    title=b.get("title", q), artist=b.get("artist", "YouTube Music"),
                    album=b.get("album", ""), duration_seconds=b.get("duration_seconds", 0),
                    cover_url=b.get("cover") or "", video_id=b.get("video_id"),
                    requested_by=interaction.user.display_name, source="ytmusic"
                )
        elif chosen_src == "apple":
            from app.services import itunes_api
            it_res = await asyncio.to_thread(itunes_api.search_tracks, query=q, limit=1)
            if it_res:
                b = it_res[0]
                track = AudioTrack(
                    title=b.get("title", q), artist=b.get("artist", "Apple Music"),
                    album=b.get("album", ""), duration_seconds=b.get("duration", 0),
                    cover_url=b.get("cover") or "", requested_by=interaction.user.display_name, source="apple"
                )
        elif chosen_src == "soundcloud":
            sc_res = await asyncio.to_thread(stream_service.search_soundcloud_tracks, query=q, limit=1)
            if sc_res:
                b = sc_res[0]
                track = AudioTrack(
                    title=b.get("title", q), artist=b.get("artist", "SoundCloud"),
                    album="SoundCloud", duration_seconds=b.get("duration_seconds", 0),
                    cover_url=b.get("cover") or "", video_id=b.get("url"),
                    requested_by=interaction.user.display_name, source="soundcloud"
                )
        elif chosen_src == "youtube":
            yt_res = await asyncio.to_thread(stream_service.search_youtube_tracks, query=q, limit=1)
            if yt_res:
                b = yt_res[0]
                raw_dur = b.get("duration", 0)
                dur_int = int(raw_dur) if (isinstance(raw_dur, (int, float)) or (isinstance(raw_dur, str) and str(raw_dur).isdigit())) else 0
                track = AudioTrack(
                    title=b.get("title", q), artist=b.get("artist", "YouTube"),
                    album=b.get("album", ""), duration_seconds=dur_int,
                    cover_url=b.get("cover") or "", video_id=b.get("video_id") or b.get("id"),
                    requested_by=interaction.user.display_name, source="youtube"
                )

        if not track:
            results = await asyncio.to_thread(deezer_api.search_tracks, query=q, limit=1)
            if results:
                best = results[0]
                track = AudioTrack(
                    title=best.get("title", q),
                    artist=best.get("artist", "Unknown"),
                    album=best.get("album", ""),
                    duration_seconds=best.get("duration", 0),
                    cover_url=best.get("cover_xl") or best.get("cover") or best.get("cover_medium") or "",
                    requested_by=interaction.user.display_name,
                    source="spotify" if chosen_src == "spotify" else "deezer"
                )
            else:
                track = AudioTrack(
                    title=q,
                    artist="Direct Query",
                    requested_by=interaction.user.display_name,
                    source="youtube"
                )

        player.enqueue(track, at_front=True)
        embed = discord.Embed(
            title="⚡ Playing Now",
            description=f"**{track.artist} — {track.title}**",
            color=EMBED_COLOR
        )
        if track.cover_url:
            embed.set_thumbnail(url=track.cover_url)
        await self._send_notice(interaction, embed=embed, delay=3.5)

        if player.is_playing:
            player.skip()
        else:
            asyncio.create_task(player.play_next())

    @app_commands.command(name="skip", description="Skip the current playing track")
    async def skip(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        if not player.is_playing:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        current = player.current_track
        player.skip()
        await interaction.response.send_message(f"⏭️ Skipped **{current.title if current else 'track'}**.", delete_after=3.5)

    @app_commands.command(name="pause", description="Pause audio playback")
    async def pause(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        if player.pause():
            await interaction.response.send_message("⏸️ Paused playback.", delete_after=3.5)
        else:
            await interaction.response.send_message("❌ Audio is not playing.", ephemeral=True)

    @app_commands.command(name="resume", description="Resume audio playback")
    async def resume(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        if player.resume():
            await interaction.response.send_message("▶️ Resumed playback.", delete_after=3.5)
        else:
            await interaction.response.send_message("❌ Audio is not paused.", ephemeral=True)

    @app_commands.command(name="stop", description="Stop playback and leave voice")
    async def stop(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        player.stop()
        await player.disconnect()
        await interaction.response.send_message("⏹️ Stopped playback and disconnected from voice.", delete_after=3.5)

    @app_commands.command(name="queue", description="Display the current music queue")
    async def queue(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        embed = discord.Embed(title="📜 Music Queue", color=EMBED_COLOR)
        
        if player.current_track:
            embed.add_field(
                name="▶️ Now Playing",
                value=f"**{player.current_track.artist} — {player.current_track.title}** ({player.current_track.duration_str})\n*Requested by:* {player.current_track.requested_by or 'Unknown'}",
                inline=False
            )
        else:
            embed.description = "No track currently playing."

        if player.queue:
            q_list = list(player.queue)[:MAX_QUEUE_DISPLAY]
            lines = []
            for i, t in enumerate(q_list, 1):
                lines.append(f"{i}. **{t.artist} — {t.title}** ({t.duration_str})")
            
            remaining = len(player.queue) - len(q_list)
            if remaining > 0:
                lines.append(f"\n*...and {remaining} more tracks*")
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
        else:
            if player.current_track:
                embed.add_field(name="Up Next", value="*Queue is empty.*" + (" (Autoplay DJ enabled 🎛️)" if player.autoplay else ""), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="history", description="Show recently played songs in this server")
    async def history(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        if not player.history:
            await interaction.response.send_message("🕒 No playback history yet in this session.", ephemeral=True)
            return

        embed = discord.Embed(title="🕒 Playback History (Recent Songs)", color=EMBED_COLOR)
        lines = []
        recent_history = list(player.history)[-10:]
        recent_history.reverse()
        for idx, t in enumerate(recent_history, 1):
            lines.append(f"`#{idx}` **{t.artist} - {t.title}** ({t.duration_str})")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Total tracks in session history: {len(player.history)} • Web Hub: http://localhost:8905")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="nowplaying" , description="Show current track and controls")
    async def nowplaying(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        if not player.current_track:
            await interaction.response.send_message("❌ Nothing is currently playing.", ephemeral=True)
            return

        t = player.current_track
        prog_bar = player.get_progress_bar()
        desc_lines = [f"**Artist:** {t.artist}"]
        if t.album:
            desc_lines.append(f"**Album:** {t.album}")
        if prog_bar:
            desc_lines.append(f"\n{prog_bar}")
        embed = discord.Embed(
            title=f"🎶 {t.title}",
            description="\n".join(desc_lines)[:4000],
            color=EMBED_COLOR
        )
        if t.cover_url:
            embed.set_thumbnail(url=t.cover_url)
        queue_len = len(player.queue)
        footer_text = f"Queue: {queue_len} track{'s' if queue_len != 1 else ''} | Vol: {int(player.volume * 100)}% | Quality: {player.audio_quality.upper()}"
        if player.loop_mode != "off":
            footer_text += f" | Loop: {player.loop_mode.capitalize()}"
        if t.requested_by:
            footer_text += f" | Requested by {t.requested_by}"
        embed.set_footer(text=footer_text)
        
        from core.ui import PlayerControlsView
        view = PlayerControlsView(player)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="volume", description="Set playback volume (1-100)")
    @app_commands.describe(percent="Volume percentage (1 to 100)")
    async def volume(self, interaction: discord.Interaction, percent: int):
        player = self.bot.player_manager.get_player(interaction.guild)
        val = max(1, min(100, percent))
        player.set_volume(val / 100.0)
        try:
            from app import store
            store.save_guild_settings(str(interaction.guild.id), {"volume": player.volume})
        except Exception:
            pass
        await interaction.response.send_message(f"🔊 Volume set to **{val}%**", delete_after=3.5)

    @app_commands.command(name="quality", description="Set audio streaming bitrate quality")
    @app_commands.describe(bitrate="Select streaming audio quality (Auto, 128k, 192k, or 320k Studio)")
    @app_commands.choices(bitrate=[
        app_commands.Choice(name="🎧 Auto (Adaptive Best Quality)", value="auto"),
        app_commands.Choice(name="⚡ 128k (Standard Bandwidth)", value="128k"),
        app_commands.Choice(name="🎵 192k (High Quality)", value="192k"),
        app_commands.Choice(name="💎 320k (Studio Master Quality)", value="320k"),
    ])
    async def quality(self, interaction: discord.Interaction, bitrate: app_commands.Choice[str]):
        player = self.bot.player_manager.get_player(interaction.guild)
        player.set_quality(bitrate.value)
        try:
            from app import store
            store.save_guild_settings(str(interaction.guild.id), {"audio_quality": player.audio_quality})
        except Exception:
            pass
        await interaction.response.send_message(f"🎧 Audio quality set to **{bitrate.name}**", delete_after=3.5)

    @app_commands.command(name="shuffle", description="Shuffle the current music queue")
    async def shuffle(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        if len(player.queue) >= 2:
            player.shuffle()
            asyncio.create_task(player.update_player_message())
            await interaction.response.send_message(f"🔀 Shuffled **{len(player.queue)}** tracks in the queue!", delete_after=3.5)
        elif len(player.queue) == 0 and player.autoplay:
            player._prewarmed_autoplay_track = None
            player._deck3_autoplay_track = None
            asyncio.create_task(player._prewarm_next_track())
            await interaction.response.send_message("🔀 Re-shuffled upcoming AI Autoplay tracks on Deck 2 & Deck 3!", delete_after=3.5)
        else:
            await interaction.response.send_message("ℹ️ Not enough tracks in queue to shuffle.", ephemeral=True)

    @app_commands.command(name="loop", description="Set repeat loop mode")
    @app_commands.choices(mode=[
        app_commands.Choice(name="Off", value="off"),
        app_commands.Choice(name="Current Track", value="track"),
        app_commands.Choice(name="Entire Queue", value="queue")
    ])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = self.bot.player_manager.get_player(interaction.guild)
        player.loop_mode = mode.value
        try:
            from app import store
            store.save_guild_settings(str(interaction.guild.id), {"loop_mode": player.loop_mode})
        except Exception:
            pass
        asyncio.create_task(player.update_player_message())
        await interaction.response.send_message(f"🔁 Loop mode set to: **{mode.name}**", delete_after=3.5)

    @app_commands.command(name="dj", description="Toggle or select the AI Autoplay DJ recommendation engine")
    @app_commands.describe(engine="Select an intelligence engine to power Autoplay recommendations")
    @app_commands.choices(engine=[
        app_commands.Choice(name="🌐 Multi-Engine Auto (Smart Hybrid)", value="auto"),
        app_commands.Choice(name="🔴 YouTube Music Radio (Song Algorithm)", value="ytmusic"),
        app_commands.Choice(name="▶️ YouTube Video & Live (Concert & Sessions)", value="youtube"),
        app_commands.Choice(name="🟣 Deezer Studio (Artist Radio & Graph)", value="deezer"),
        app_commands.Choice(name="🟢 Spotify Catalog (Curated Hits)", value="spotify"),
        app_commands.Choice(name="🍎 Apple Music (Lossless Studio)", value="apple"),
        app_commands.Choice(name="🟠 SoundCloud (Underground & Mixes)", value="soundcloud"),
        app_commands.Choice(name="🏛️ MusicBrainz (Canonical Discography)", value="musicbrainz"),
        app_commands.Choice(name="📊 Official Charts (Top 40 & Billboard)", value="charts"),
    ])
    async def dj(self, interaction: discord.Interaction, engine: app_commands.Choice[str] = None):
        player = self.bot.player_manager.get_player(interaction.guild)
        from app import store
        if engine:
            player.vibe_engine_source = engine.value
            player.autoplay = True
            store.save_guild_settings(str(interaction.guild.id), {
                "autoplay": True,
                "vibe_engine_source": engine.value
            })
            asyncio.create_task(player.update_player_message())
            await interaction.response.send_message(
                f"🎛️ Autoplay DJ engine set to **{engine.name}**! Autoplay is now **ENABLED 🟢**.",
                delete_after=5.0
            )
            if not player.is_playing and len(player.queue) == 0 and player.current_track:
                asyncio.create_task(player.play_next())
            elif player.is_playing and len(player.queue) == 0:
                player._prewarmed_autoplay_track = None
                player._deck3_autoplay_track = None
                asyncio.create_task(player._prewarm_next_track())
        else:
            player.autoplay = not player.autoplay
            store.save_guild_settings(str(interaction.guild.id), {"autoplay": player.autoplay})
            asyncio.create_task(player.update_player_message())
            status = "ENABLED 🎛️" if player.autoplay else "DISABLED ⏹️"
            engine_label = getattr(player, "vibe_engine_source", "auto").upper()
            await interaction.response.send_message(f"Autoplay DJ is now **{status}** [Engine: {engine_label}]", delete_after=3.5)

    @app_commands.command(name="brain", description="Show live AI Vibe Engine status, active platform, and telemetry")
    async def brain(self, interaction: discord.Interaction):
        player = self.bot.player_manager.get_player(interaction.guild)
        engine_map = {
            "auto": "🌐 Multi-Engine Auto (Hybrid)", "ytmusic": "🔴 YouTube Music Radio",
            "youtube": "▶️ YouTube Video / Live", "deezer": "🟣 Deezer Studio",
            "spotify": "🟢 Spotify Catalog", "apple": "🍎 Apple Music",
            "soundcloud": "🟠 SoundCloud", "musicbrainz": "🏛️ MusicBrainz Archive",
            "charts": "📊 Official Charts"
        }
        current_eng = engine_map.get(getattr(player, "vibe_engine_source", "auto"), "🌐 Multi-Engine Auto")
        lines = [
            f"**Autoplay Status:** {'🟢 Active' if player.autoplay else '⚪ Disabled'}",
            f"**Engine Platform:** {current_eng}",
            f"**Vibe Mode:** {player.vibe_mode.title()}",
            f"**Drift Frequency:** Every {player.vibe_drift_freq} track(s)",
            f"**Catalog Depth:** {player.hit_depth.replace('_', ' ').title()}",
            f"**Explicit Shield:** {'🛡️ Clean Only' if player.explicit_filter == 'clean_only' else '🔓 Allowed'}",
            f"**Vibe Anchor:** {player.vibe_anchor_artist or (player.current_track.artist if player.current_track else 'None')}",
            f"**Last Decision:** {getattr(player, 'last_brain_decision', 'Online & Ready')}"
        ]
        embed = discord.Embed(
            title="🧠 Vibe Engine & AI Autoplay Telemetry",
            description="\n".join(lines),
            color=EMBED_COLOR
        )
        embed.set_footer(text="Configure anytime via /dj [engine] or at http://localhost:8905")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))
