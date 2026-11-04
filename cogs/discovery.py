import asyncio
from typing import Optional, List
import discord
from discord import app_commands
from discord.ext import commands

from app.services import discovery, deezer_api, musicbrainz_api, stream_service, itunes_api
from core.config import EMBED_COLOR
from core.player import AudioTrack, GuildPlayer
from core.ui import AlbumSelectView, SearchResultSelectView
from core.logger import get_bot_logger

log = get_bot_logger("cogs.discovery")


async def _fetch_album_tracks(album_id: str, title: str, artist: str) -> List[dict]:
    """Fetch verified tracklist for an album via Deezer or MusicBrainz with smart fallbacks."""
    clean_aid = str(album_id or "").strip()
    while clean_aid.startswith("mb_"):
        clean_aid = clean_aid[3:]

    alb_data = None
    try:
        if clean_aid.isdigit():
            alb_data = await asyncio.to_thread(deezer_api.get_album_details, clean_aid)
        elif "-" in clean_aid or len(clean_aid) == 36:
            alb_data = await asyncio.to_thread(musicbrainz_api.get_release_group_details, clean_aid)

        if not alb_data or not alb_data.get("tracks"):
            if title:
                found = await asyncio.to_thread(deezer_api.search_albums, f"{artist} {title}".strip(), limit=1)
                if found:
                    alb_data = await asyncio.to_thread(deezer_api.get_album_details, str(found[0]["id"]))
    except Exception as e:
        log.warning(f"Error fetching album tracks for {artist} - {title} ({album_id}): {e}")

    return alb_data.get("tracks", []) if alb_data else []


class DiscographySelectView(discord.ui.View):
    """Interactive select menu to pick an album from an artist's classified discography."""
    def __init__(self, player, albums: List[dict], artist_name: str, category_name: str, user_name: str):
        super().__init__(timeout=180)
        self.player = player
        self.albums = albums[:25]
        self.artist_name = artist_name
        self.category_name = category_name
        self.user_name = user_name

        options = []
        for i, a in enumerate(self.albums):
            title = a.get("title", "Unknown Album")[:50]
            year = str(a.get("year") or a.get("release_date") or "")[:4]
            tracks_count = a.get("tracks_count") or a.get("nb_tracks") or 0
            cat = a.get("category") or category_name

            label = f"{title}"
            if year:
                label = f"{title} ({year})"
            label = label[:100]

            desc_parts = []
            if cat:
                desc_parts.append(cat)
            if tracks_count:
                desc_parts.append(f"{tracks_count} tracks")
            desc = " • ".join(desc_parts)[:100]

            options.append(discord.SelectOption(
                label=label,
                description=desc if desc else None,
                value=str(i),
                emoji="💿" if "Studio" in cat else ("📀" if "EP" in cat else "📦")
            ))

        if options:
            self.select = discord.ui.Select(
                placeholder=f"Select an album from {artist_name} to browse & queue...",
                options=options
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        idx = int(self.select.values[0])
        selected_alb = self.albums[idx]
        alb_id = str(selected_alb.get("id") or "")
        title = selected_alb.get("title", "Unknown Album")
        artist = selected_alb.get("artist", self.artist_name)

        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        full_album = None
        if alb_id and not alb_id.startswith("mb_"):
            full_album = await asyncio.to_thread(deezer_api.get_album_details, alb_id)
        if not full_album or not full_album.get("tracks"):
            raw_tracks = await _fetch_album_tracks(alb_id, title, artist)
            full_album = {
                "title": title,
                "artist": artist,
                "cover_xl": selected_alb.get("cover") or "",
                "release_date": selected_alb.get("year") or "",
                "tracks": raw_tracks
            }

        tracks = full_album.get("tracks", [])
        year = str(full_album.get("release_date") or selected_alb.get("year") or "")[:4]
        cover_url = full_album.get("cover_xl") or full_album.get("cover_medium") or selected_alb.get("cover") or ""
        cat = selected_alb.get("category", "Studio Album")

        embed = discord.Embed(
            title=f"💿 {title} ({year})" if year else f"💿 {title}",
            description=f"**Artist:** {artist}\n**Category:** {cat}\n**Tracks:** {len(tracks)}",
            color=EMBED_COLOR
        )
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        lines = []
        for i, t in enumerate(tracks[:6], 1):
            dur = t.get("duration") or 0
            dur_text = f" ({AudioTrack._format_duration(dur)})" if dur else ""
            lines.append(f"{i}. {t.get('title', 'Unknown')}{dur_text}")
        if len(tracks) > 6:
            lines.append(f"*...and {len(tracks) - 6} more tracks*")

        if lines:
            embed.add_field(name="Tracklist Preview", value="\n".join(lines), inline=False)

        view = AlbumSelectView(self.player, full_album, tracks, self.user_name)
        await interaction.followup.send(embed=embed, view=view)


class ArtistProfileView(discord.ui.View):
    """Interactive profile view with dropdown menus & quick action buttons for Studio Albums and Popular Hits."""
    def __init__(
        self,
        bot: commands.Bot,
        artist_name: str,
        artist_pic: str,
        studio_albums: List[dict],
        top_tracks: List[dict],
        all_albums: List[dict],
        user_name: str
    ):
        super().__init__(timeout=240)
        self.bot = bot
        self.artist_name = artist_name
        self.artist_pic = artist_pic
        self.studio_albums = studio_albums
        self.top_tracks = top_tracks
        self.all_albums = all_albums
        self.user_name = user_name

        # Row 0: Top Studio Albums Select Menu (up to 25)
        if self.studio_albums:
            alb_options = []
            for i, a in enumerate(self.studio_albums[:25]):
                title = (a.get("title") or "Unknown Album")[:50]
                year = str(a.get("year") or a.get("release_date") or "")[:4]
                tracks_count = a.get("tracks_count") or a.get("nb_tracks") or 0
                label = f"{title} ({year})" if year else title
                label = label[:100]

                desc_parts = []
                if tracks_count:
                    desc_parts.append(f"{tracks_count} tracks")
                desc_parts.append(self.artist_name)
                desc = " • ".join(desc_parts)[:100]

                alb_options.append(discord.SelectOption(
                    label=label,
                    description=desc,
                    value=str(i),
                    emoji="💿"
                ))

            self.album_select = discord.ui.Select(
                placeholder=f"💿 Pick a Studio Album to play ({len(self.studio_albums)} available)...",
                options=alb_options,
                row=0
            )
            self.album_select.callback = self.album_select_callback
            self.add_item(self.album_select)

        # Row 1: Most Popular Tracks Select Menu (up to 10)
        if self.top_tracks:
            track_options = []
            for i, t in enumerate(self.top_tracks[:10]):
                title = (t.get("title") or "Unknown Track")[:50]
                dur_secs = t.get("duration", 0)
                dur_str = AudioTrack._format_duration(dur_secs) if dur_secs else ""
                album_name = t.get("album_title") or ""

                label = f"{i+1}. {title}"[:100]
                desc_parts = []
                if dur_str:
                    desc_parts.append(dur_str)
                if album_name:
                    desc_parts.append(f"from {album_name}")
                desc = " • ".join(desc_parts)[:100] if desc_parts else self.artist_name

                track_options.append(discord.SelectOption(
                    label=label,
                    description=desc if desc else None,
                    value=str(i),
                    emoji="🔥"
                ))

            self.track_select = discord.ui.Select(
                placeholder="🔥 Pick a Popular Track to play...",
                options=track_options,
                row=1
            )
            self.track_select.callback = self.track_select_callback
            self.add_item(self.track_select)

        # Row 2: Action Buttons
        if self.top_tracks:
            top_hit_title = self.top_tracks[0].get("title", "Top Hit")[:18]
            self.btn_top_hit = discord.ui.Button(
                label=f"Play Hit: {top_hit_title}",
                style=discord.ButtonStyle.success,
                emoji="▶️",
                row=2
            )
            self.btn_top_hit.callback = self.play_top_hit_callback
            self.add_item(self.btn_top_hit)

            self.btn_mix = discord.ui.Button(
                label="Mix Top Hits",
                style=discord.ButtonStyle.primary,
                emoji="🔀",
                row=2
            )
            self.btn_mix.callback = self.mix_top_hits_callback
            self.add_item(self.btn_mix)

        if self.studio_albums:
            latest_title = self.studio_albums[0].get("title", "Latest")[:18]
            self.btn_latest = discord.ui.Button(
                label=f"Play Latest: {latest_title}",
                style=discord.ButtonStyle.secondary,
                emoji="💿",
                row=2
            )
            self.btn_latest.callback = self.play_latest_album_callback
            self.add_item(self.btn_latest)

        self.btn_disco = discord.ui.Button(
            label="Full Discography",
            style=discord.ButtonStyle.secondary,
            emoji="📂",
            row=2
        )
        self.btn_disco.callback = self.discography_callback
        self.add_item(self.btn_disco)

    async def _ensure_voice(self, interaction: discord.Interaction) -> Optional[GuildPlayer]:
        if not interaction.user.voice or not interaction.user.voice.channel:
            msg = "❌ You must be connected to a voice channel first!"
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return None

        player = self.bot.player_manager.get_player(interaction.guild)
        voice_channel = interaction.user.voice.channel
        if not player.is_connected or (player.voice_client and player.voice_client.channel.id != voice_channel.id):
            connected = await player.connect(voice_channel, text_channel=interaction.channel)
            if not connected:
                msg = "❌ Failed to connect to your voice channel."
                if not interaction.response.is_done():
                    await interaction.response.send_message(msg, ephemeral=True)
                else:
                    await interaction.followup.send(msg, ephemeral=True)
                return None
        player.text_channel = interaction.channel
        return player

    async def album_select_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = await self._ensure_voice(interaction)
        if not player:
            return

        idx = int(self.album_select.values[0])
        selected_alb = self.studio_albums[idx]
        alb_id = str(selected_alb.get("id") or "")
        alb_title = selected_alb.get("title", "Unknown Album")
        alb_cover = selected_alb.get("cover") or self.artist_pic

        raw_tracks = await _fetch_album_tracks(alb_id, alb_title, self.artist_name)
        if not raw_tracks:
            raw_tracks = [{"title": alb_title, "artist": self.artist_name, "duration": 0}]

        tracks = []
        for t in raw_tracks:
            dur = int(t.get("duration", 0))
            t_art = t.get("artist") or self.artist_name
            if isinstance(t_art, dict):
                t_art = t_art.get("name", self.artist_name)
            tracks.append(AudioTrack(
                title=t.get("title") or "Unknown Track",
                artist=t_art,
                album=alb_title,
                duration_seconds=dur,
                duration_str=AudioTrack._format_duration(dur),
                cover_url=alb_cover,
                requested_by=interaction.user.display_name
            ))

        total = player.enqueue_many(tracks)
        await interaction.followup.send(
            f"💿 Added **{len(tracks)} tracks** from *{alb_title}* to the queue! (Total in queue: {total})",
            ephemeral=True
        )
        if not player.is_playing:
            asyncio.create_task(player.play_next())

    async def track_select_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = await self._ensure_voice(interaction)
        if not player:
            return

        idx = int(self.track_select.values[0])
        t = self.top_tracks[idx]
        title = t.get("title", "Unknown Track")
        artist = t.get("artist", self.artist_name)
        album = t.get("album_title", "")
        dur = int(t.get("duration", 0))
        cover = t.get("cover") or self.artist_pic

        track = AudioTrack(
            title=title,
            artist=artist,
            album=album,
            duration_seconds=dur,
            duration_str=AudioTrack._format_duration(dur),
            cover_url=cover,
            requested_by=interaction.user.display_name
        )

        pos = player.enqueue(track)
        await interaction.followup.send(
            f"🔥 Added **{artist} — {title}** to the queue (Position #{pos})",
            ephemeral=True
        )
        if not player.is_playing:
            asyncio.create_task(player.play_next())

    async def play_top_hit_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = await self._ensure_voice(interaction)
        if not player or not self.top_tracks:
            return

        t = self.top_tracks[0]
        title = t.get("title", "Unknown Track")
        artist = t.get("artist", self.artist_name)
        album = t.get("album_title", "")
        dur = int(t.get("duration", 0))
        cover = t.get("cover") or self.artist_pic

        track = AudioTrack(
            title=title,
            artist=artist,
            album=album,
            duration_seconds=dur,
            duration_str=AudioTrack._format_duration(dur),
            cover_url=cover,
            requested_by=interaction.user.display_name
        )

        pos = player.enqueue(track)
        await interaction.followup.send(
            f"▶️ Playing top hit **{artist} — {title}**! (Queue #{pos})",
            ephemeral=True
        )
        if not player.is_playing:
            asyncio.create_task(player.play_next())

    async def mix_top_hits_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = await self._ensure_voice(interaction)
        if not player or not self.top_tracks:
            return

        tracks = []
        for t in self.top_tracks:
            dur = int(t.get("duration", 0))
            tracks.append(AudioTrack(
                title=t.get("title", "Unknown Track"),
                artist=t.get("artist", self.artist_name),
                album=t.get("album_title", ""),
                duration_seconds=dur,
                duration_str=AudioTrack._format_duration(dur),
                cover_url=t.get("cover") or self.artist_pic,
                requested_by=interaction.user.display_name
            ))

        total = player.enqueue_many(tracks)
        await interaction.followup.send(
            f"🔀 Mixed **{len(tracks)} top hits** from **{self.artist_name}** into the queue! (Total in queue: {total})",
            ephemeral=True
        )
        if not player.is_playing:
            asyncio.create_task(player.play_next())

    async def play_latest_album_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = await self._ensure_voice(interaction)
        if not player or not self.studio_albums:
            return

        selected_alb = self.studio_albums[0]
        alb_id = str(selected_alb.get("id") or "")
        alb_title = selected_alb.get("title", "Unknown Album")
        alb_cover = selected_alb.get("cover") or self.artist_pic

        raw_tracks = await _fetch_album_tracks(alb_id, alb_title, self.artist_name)
        if not raw_tracks:
            raw_tracks = [{"title": alb_title, "artist": self.artist_name, "duration": 0}]

        tracks = []
        for t in raw_tracks:
            dur = int(t.get("duration", 0))
            t_art = t.get("artist") or self.artist_name
            if isinstance(t_art, dict):
                t_art = t_art.get("name", self.artist_name)
            tracks.append(AudioTrack(
                title=t.get("title") or "Unknown Track",
                artist=t_art,
                album=alb_title,
                duration_seconds=dur,
                duration_str=AudioTrack._format_duration(dur),
                cover_url=alb_cover,
                requested_by=interaction.user.display_name
            ))

        total = player.enqueue_many(tracks)
        await interaction.followup.send(
            f"💿 Added latest album **{alb_title}** ({len(tracks)} tracks) to queue! (Total: {total})",
            ephemeral=True
        )
        if not player.is_playing:
            asyncio.create_task(player.play_next())

    async def discography_callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        player = self.bot.player_manager.get_player(interaction.guild)
        albums_to_show = self.all_albums or self.studio_albums
        embed = discord.Embed(
            title=f"🗂️ {self.artist_name} — Complete Discography",
            description=f"Showing **{len(albums_to_show[:25])}** releases. Choose an album from the dropdown below to preview its tracklist and queue it:",
            color=EMBED_COLOR
        )
        if self.artist_pic:
            embed.set_thumbnail(url=self.artist_pic)

        view = DiscographySelectView(player, albums_to_show, self.artist_name, "Catalog", interaction.user.display_name)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class DiscoveryCog(commands.Cog, name="Discovery"):
    """Music Discovery commands powered by Deezer, MusicBrainz, and Apple iTunes."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_error(self, interaction: discord.Interaction, message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

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

    @app_commands.command(name="album", description="Search albums with canonical classification and browse tracklists")
    @app_commands.describe(query="Artist and Album title (e.g. 'Pink Floyd Dark Side of the Moon')")
    async def album(self, interaction: discord.Interaction, query: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        albums = await asyncio.to_thread(deezer_api.search_albums, query=query.strip(), limit=5)
        if not albums:
            await interaction.followup.send(f"❌ No albums found matching: **{query}**")
            return

        top_album = albums[0]
        album_id = top_album.get("id")

        # Use canonical deterministic resolution (Deezer + MusicBrainz + iTunes)
        canonical = await asyncio.to_thread(
            discovery.resolve_album_canonical,
            deezer_album_id=str(album_id),
            fallback_artist=top_album.get("artist", ""),
            fallback_title=top_album.get("title", "")
        )

        full_album = await asyncio.to_thread(deezer_api.get_album_details, str(album_id))
        if not full_album or not full_album.get("tracks"):
            full_album = top_album

        tracks = full_album.get("tracks", [])
        if not tracks and album_id:
            tracks = await _fetch_album_tracks(str(album_id), top_album.get("title", ""), top_album.get("artist", ""))

        title = canonical.get("title") or canonical.get("canonical_title") or full_album.get("title", top_album.get("title", "Unknown Album"))
        artist = canonical.get("artist") or canonical.get("canonical_artist") or full_album.get("artist", top_album.get("artist", "Unknown Artist"))
        year = str(canonical.get("year") or canonical.get("canonical_year") or full_album.get("release_date") or full_album.get("year") or "")[:4]
        category = canonical.get("category") or canonical.get("primary_type") or full_album.get("record_type") or "Studio Album"
        cover_url = canonical.get("itunes_artwork") or canonical.get("cover_1400") or full_album.get("cover_xl") or full_album.get("cover_medium") or full_album.get("cover") or ""
        label = canonical.get("label") or full_album.get("label") or ""

        meta_parts = []
        if category:
            meta_parts.append(f"💿 **{category.title()}**")
        if year:
            meta_parts.append(f"📅 **{year}**")
        if label:
            meta_parts.append(f"🏷️ **{label}**")
        meta_parts.append(f"🎵 **{len(tracks)} tracks**")

        embed = discord.Embed(
            title=f"💿 {title}",
            description=f"**Artist:** {artist}\n" + " • ".join(meta_parts),
            color=EMBED_COLOR
        )
        if cover_url:
            embed.set_thumbnail(url=cover_url)

        preview_lines = []
        for i, t in enumerate(tracks[:6], 1):
            dur = t.get("duration") or 0
            dur_text = f" ({AudioTrack._format_duration(dur)})" if dur else ""
            preview_lines.append(f"{i}. {t.get('title', 'Unknown')}{dur_text}")

        if len(tracks) > 6:
            preview_lines.append(f"*...and {len(tracks) - 6} more tracks below*")

        if preview_lines:
            embed.add_field(name="Tracklist Preview", value="\n".join(preview_lines), inline=False)

        view = AlbumSelectView(player, full_album, tracks, interaction.user.display_name)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="discography", description="Browse an artist's full classified discography by category")
    @app_commands.describe(
        artist="Artist name (e.g. 'Daft Punk', 'Queen', 'Radiohead')",
        category="Filter releases (default: Studio Albums)"
    )
    @app_commands.choices(category=[
        app_commands.Choice(name="💿 Studio Albums", value="Studio Albums"),
        app_commands.Choice(name="📀 EPs & Singles", value="EPs"),
        app_commands.Choice(name="📦 Compilations & Box Sets", value="Compilations"),
        app_commands.Choice(name="🎸 Live Albums", value="Live Albums"),
        app_commands.Choice(name="🌐 All Releases", value="All"),
    ])
    async def discography(
        self,
        interaction: discord.Interaction,
        artist: str,
        category: Optional[app_commands.Choice[str]] = None
    ):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        clean_artist = artist.strip()
        artists = await asyncio.to_thread(deezer_api.search_artists, query=clean_artist, limit=1)
        if not artists:
            await interaction.followup.send(f"❌ Artist not found: **{clean_artist}**")
            return

        art = artists[0]
        art_id = str(art.get("id"))
        art_name = art.get("name") or clean_artist

        # Fetch categorized master discography
        disco_data = await asyncio.to_thread(discovery.get_artist_albums, art_id, art_name, limit=100)
        all_albums = disco_data.get("albums", [])
        counts = disco_data.get("counts", {})

        chosen_cat = category.value if category else "Studio Albums"

        if chosen_cat == "All":
            filtered_albums = all_albums
        elif chosen_cat == "EPs":
            filtered_albums = [a for a in all_albums if a.get("category") in ("EPs", "Singles", "Singles & Remixes")]
        else:
            filtered_albums = [a for a in all_albums if a.get("category") == chosen_cat]

        # If chosen category is empty, fall back to all albums
        if not filtered_albums:
            filtered_albums = all_albums
            chosen_cat = "All Releases"

        stat_parts = []
        for cat_name, cnt in counts.items():
            stat_parts.append(f"**{cat_name}:** {cnt}")
        stats_text = " • ".join(stat_parts) if stat_parts else "Catalog assembled."

        embed = discord.Embed(
            title=f"📚 {art_name} — {chosen_cat}",
            description=f"Showing **{len(filtered_albums[:25])}** releases in this category.\n\n📊 **Catalog Breakdown:**\n{stats_text}",
            color=EMBED_COLOR
        )
        pic = art.get("picture_big") or art.get("picture_medium") or art.get("picture")
        if pic:
            embed.set_thumbnail(url=pic)

        view = DiscographySelectView(player, filtered_albums, art_name, chosen_cat, interaction.user.display_name)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="artist", description="Lookup an artist profile, taxonomy stats, and top hits")
    @app_commands.describe(name="Artist name")
    async def artist(self, interaction: discord.Interaction, name: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        clean_name = name.strip()
        artists = await asyncio.to_thread(deezer_api.search_artists, query=clean_name, limit=1)
        if not artists:
            await interaction.followup.send(f"❌ Artist not found: **{clean_name}**")
            return

        art = artists[0]
        art_id = str(art.get("id"))
        art_name = art.get("name") or clean_name

        disco_data = await asyncio.to_thread(discovery.get_artist_albums, art_id, art_name, limit=50)
        counts = disco_data.get("counts", {})
        albums = disco_data.get("albums", [])
        top_tracks = await asyncio.to_thread(deezer_api.get_artist_top_tracks, art_id, limit=5)

        studio_albums = [a for a in albums if (a.get("category") or "") == "Studio Albums"]

        count_parts = []
        if counts.get("Studio Albums"):
            count_parts.append(f"💿 {counts['Studio Albums']} Studio Albums")
        if counts.get("EPs") or counts.get("Singles"):
            total_eps = counts.get("EPs", 0) + counts.get("Singles", 0)
            count_parts.append(f"📀 {total_eps} EPs & Singles")
        if counts.get("Compilations"):
            count_parts.append(f"📦 {counts['Compilations']} Compilations")
        if counts.get("Live Albums"):
            count_parts.append(f"🎸 {counts['Live Albums']} Live Albums")

        desc_lines = [
            f"👥 **Fans:** {art.get('fans', 0):,}",
            f"🗂️ **Discography:** {' • '.join(count_parts) if count_parts else 'Complete catalog'}"
        ]

        embed = discord.Embed(
            title=f"🎤 {art_name}",
            description="\n".join(desc_lines),
            color=EMBED_COLOR
        )
        pic = art.get("picture_big") or art.get("picture_medium") or art.get("picture")
        if pic:
            embed.set_thumbnail(url=pic)

        if studio_albums:
            alb_lines = []
            for i, a in enumerate(studio_albums[:5], 1):
                yr = str(a.get("year") or a.get("release_date") or "")[:4]
                yr_str = f" ({yr})" if yr else ""
                alb_lines.append(f"{i}. **{a.get('title', 'Unknown')}**{yr_str}")
            embed.add_field(name="💿 Top Studio Albums", value="\n".join(alb_lines), inline=False)

        if top_tracks:
            track_lines = [f"{i}. **{t.get('title')}**" for i, t in enumerate(top_tracks, 1)]
            embed.add_field(name="🔥 Most Popular Tracks", value="\n".join(track_lines), inline=False)

        embed.set_footer(text="💡 Pick an album or track below, or mix all hits directly!")

        view = ArtistProfileView(
            bot=self.bot,
            artist_name=art_name,
            artist_pic=pic or "",
            studio_albums=studio_albums,
            top_tracks=top_tracks,
            all_albums=albums,
            user_name=interaction.user.display_name
        )
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="search", description="Search tracks across providers and pick from a list")
    @app_commands.describe(
        query="Song or artist name",
        source="Service to search (Default: All Sources Universal)"
    )
    @app_commands.choices(source=[
        app_commands.Choice(name="🌐 Multi-Engine Auto (Universal Match)", value="auto"),
        app_commands.Choice(name="🔴 YouTube Music (Official Studio)", value="ytmusic"),
        app_commands.Choice(name="▶️ YouTube Video & Live", value="youtube"),
        app_commands.Choice(name="🟣 Deezer Studio Masters", value="deezer"),
        app_commands.Choice(name="🟢 Spotify Catalog Match", value="spotify"),
        app_commands.Choice(name="🍎 Apple Music / iTunes", value="apple"),
        app_commands.Choice(name="🟠 SoundCloud (Underground & Mixes)", value="soundcloud"),
        app_commands.Choice(name="🏛️ MusicBrainz Discography", value="musicbrainz"),
        app_commands.Choice(name="📊 Official Charts Top 40", value="charts"),
    ])
    async def search(self, interaction: discord.Interaction, query: str, source: app_commands.Choice[str] = None):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        src_val = source.value if source else "auto"
        results = []
        if src_val == "auto":
            t_dz, t_yt = await asyncio.gather(
                asyncio.to_thread(deezer_api.search_tracks, query=query.strip(), limit=5),
                asyncio.to_thread(stream_service.search_ytmusic_catalog, query=query.strip(), limit=5),
                return_exceptions=True
            )
            dz_items = t_dz if isinstance(t_dz, list) else []
            yt_items = t_yt if isinstance(t_yt, list) else []
            seen = set()
            for it in dz_items:
                k = f"{it.get('artist','').lower()} - {it.get('title','').lower()}"
                if k not in seen:
                    seen.add(k)
                    results.append(it)
            for it in yt_items:
                k = f"{it.get('artist','').lower()} - {it.get('title','').lower()}"
                if k not in seen:
                    seen.add(k)
                    results.append({
                        "title": it.get("title", "Unknown"),
                        "artist": it.get("artist", "YouTube Music"),
                        "album": it.get("album", ""),
                        "duration": int(it.get("duration_seconds", 0)),
                        "cover": it.get("cover", ""),
                        "source": "ytmusic"
                    })
        elif src_val == "ytmusic":
            yt_res = await asyncio.to_thread(stream_service.search_ytmusic_catalog, query=query.strip(), limit=10)
            for it in yt_res:
                results.append({
                    "title": it.get("title", "Unknown"),
                    "artist": it.get("artist", "YouTube Music"),
                    "album": it.get("album", ""),
                    "duration": int(it.get("duration_seconds", 0)),
                    "cover": it.get("cover", ""),
                    "source": "ytmusic"
                })
        elif src_val == "apple":
            results = await asyncio.to_thread(itunes_api.search_tracks, query=query.strip(), limit=10)
        elif src_val == "youtube":
            yt_res = await asyncio.to_thread(stream_service.search_youtube_tracks, query=query.strip(), limit=10)
            for it in yt_res:
                raw_dur = it.get("duration", 0)
                dur_i = int(raw_dur) if (isinstance(raw_dur, (int, float)) or (isinstance(raw_dur, str) and str(raw_dur).isdigit())) else 0
                results.append({
                    "title": it.get("title", "Unknown"),
                    "artist": it.get("artist", "YouTube"),
                    "album": "YouTube",
                    "duration": dur_i,
                    "cover": it.get("cover", ""),
                    "video_id": it.get("video_id") or it.get("id"),
                    "source": "youtube"
                })
        elif src_val == "soundcloud":
            sc_res = await asyncio.to_thread(stream_service.search_soundcloud_tracks, query=query.strip(), limit=10)
            for it in sc_res:
                results.append({
                    "title": it.get("title", "Unknown"),
                    "artist": it.get("artist", "SoundCloud"),
                    "album": "SoundCloud",
                    "duration": int(it.get("duration_seconds", 0)),
                    "cover": it.get("cover", ""),
                    "video_id": it.get("url"),
                    "source": "soundcloud"
                })
        elif src_val == "musicbrainz":
            from app.services import musicbrainz_api
            mb_items = await asyncio.to_thread(musicbrainz_api.search_release_groups, query.strip(), limit=10)
            if not mb_items:
                mb_data = await asyncio.to_thread(musicbrainz_api.get_artist_categorized_discography, query.strip(), limit=10)
                mb_items = mb_data.get("albums") or []
            for a in mb_items:
                results.append({
                    "title": a.get("title", "Unknown Release"),
                    "artist": a.get("artist", query.strip()),
                    "album": (a.get("category") or a.get("record_type") or "Album").title(),
                    "duration": 0,
                    "cover": a.get("cover", ""),
                    "source": "musicbrainz"
                })
        elif src_val == "charts":
            from app.services import official_charts
            charts_data = await asyncio.to_thread(official_charts.get_live_official_charts, country="gb", limit=30)
            q_clean = query.strip().lower()
            q_words = [w for w in q_clean.split() if len(w) > 1]
            matches = []
            for c in (charts_data.get("tracks") or []):
                haystack = f"{c.get('title', '')} {c.get('artist', '')}".lower()
                if not q_words or any(w in haystack for w in q_words):
                    matches.append({
                        "title": c.get("title", "Unknown"),
                        "artist": c.get("artist", "Chart Artist"),
                        "album": c.get("album", "Official Chart"),
                        "duration": int(c.get("duration", 0)),
                        "cover": c.get("cover", ""),
                        "source": "charts"
                    })
            if not matches:
                for c in (charts_data.get("tracks") or [])[:10]:
                    matches.append({
                        "title": c.get("title", "Unknown"),
                        "artist": c.get("artist", "Chart Artist"),
                        "album": c.get("album", "Official Trending Chart"),
                        "duration": int(c.get("duration", 0)),
                        "cover": c.get("cover", ""),
                        "source": "charts"
                    })
            results.extend(matches)
        else:
            results = await asyncio.to_thread(deezer_api.search_tracks, query=query.strip(), limit=10)

        if not results:
            await interaction.followup.send(f"❌ No tracks found for: **{query}**")
            return

        embed = discord.Embed(
            title=f"🔍 Search Results for: {query}",
            description="Use the dropdown menu below to select and queue a track:",
            color=EMBED_COLOR
        )
        view = SearchResultSelectView(player, results, interaction.user.display_name)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="newreleases", description="Browse fresh studio drops and editorial new releases this week")
    @app_commands.describe(limit="Number of releases to display (default: 10)")
    async def newreleases(self, interaction: discord.Interaction, limit: Optional[int] = 10):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        clean_limit = min(max(5, limit or 10), 25)
        res = await asyncio.to_thread(discovery.get_new_releases, limit=clean_limit)
        albums = res.get("albums", []) if isinstance(res, dict) else []
        if not albums:
            await interaction.followup.send("❌ Unable to fetch new release drops right now.")
            return

        embed = discord.Embed(
            title="✨ Fresh Album Drops & New Releases This Week",
            description="Curated fresh studio releases from editorial radar:\n",
            color=EMBED_COLOR
        )
        first = albums[0]
        if first.get("cover"):
            embed.set_thumbnail(url=first.get("cover"))

        lines = []
        for i, a in enumerate(albums[:8], 1):
            lines.append(f"{i}. **{a.get('artist')}** — *{a.get('title')}*")
        embed.description += "\n".join(lines)

        view = DiscographySelectView(player, albums, "New Releases", "Fresh Drops", interaction.user.display_name)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(DiscoveryCog(bot))
