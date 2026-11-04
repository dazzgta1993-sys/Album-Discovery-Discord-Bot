import asyncio
from typing import List
import discord

class PlayerControlsView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)
        self.player = player

    @discord.ui.button(label="⏯️", style=discord.ButtonStyle.primary, custom_id="btn_play_pause")
    async def play_pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        if not self.player.voice_client:
            return
        if self.player.voice_client.is_paused():
            self.player.resume()
        elif self.player.voice_client.is_playing():
            self.player.pause()
        await self.player.update_player_message()

    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.secondary, custom_id="btn_skip")
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        if self.player.voice_client and (self.player.voice_client.is_playing() or self.player.voice_client.is_paused()):
            self.player.skip()

    @discord.ui.button(label="🔀", style=discord.ButtonStyle.secondary, custom_id="btn_shuffle")
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        if len(self.player.queue) >= 2:
            self.player.shuffle()
            await self.player.update_player_message()

    @discord.ui.button(label="🔁", style=discord.ButtonStyle.secondary, custom_id="btn_loop")
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modes = ["off", "track", "queue"]
        idx = (modes.index(self.player.loop_mode) + 1) % len(modes)
        self.player.loop_mode = modes[idx]
        try:
            await interaction.response.defer()
        except Exception:
            pass
        await self.player.update_player_message()

    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger, custom_id="btn_stop")
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
        except Exception:
            pass
        self.player.stop()


class AlbumSelectView(discord.ui.View):
    def __init__(self, player, album_data: dict, tracks: List[dict], user_name: str):
        super().__init__(timeout=120)
        self.player = player
        self.album_data = album_data
        self.tracks = tracks
        self.user_name = user_name

        # Add select menu with up to 25 tracks (Discord select menu limit)
        options = []
        for i, t in enumerate(tracks[:25]):
            dur = t.get("duration_str") or ""
            label = f"{i+1}. {t.get('title', 'Unknown')}"[:100]
            desc = f"{t.get('artist', '')} | {dur}"[:100] if dur else t.get("artist", "")[:100]
            options.append(discord.SelectOption(label=label, description=desc, value=str(i)))

        if options:
            self.select = discord.ui.Select(placeholder="Select a track to play...", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        from .player import AudioTrack
        idx = int(self.select.values[0])
        track_info = self.tracks[idx]

        track = AudioTrack(
            title=track_info.get("title", "Unknown"),
            artist=track_info.get("artist", self.album_data.get("artist", "Unknown")),
            album=self.album_data.get("title", ""),
            duration_seconds=track_info.get("duration", 0),
            duration_str=track_info.get("duration_str", ""),
            cover_url=self.album_data.get("cover_xl") or self.album_data.get("cover_medium") or "",
            requested_by=self.user_name
        )

        pos = self.player.enqueue(track)
        await interaction.response.send_message(f"➕ Added **{track.artist} — {track.title}** to queue (Position #{pos})", ephemeral=True)
        if not self.player.is_playing:
            asyncio.create_task(self.player.play_next())

    @discord.ui.button(label="▶️ Queue Entire Album", style=discord.ButtonStyle.success)
    async def queue_all_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        from .player import AudioTrack
        album_tracks = []
        for t in self.tracks:
            album_tracks.append(AudioTrack(
                title=t.get("title", "Unknown"),
                artist=t.get("artist", self.album_data.get("artist", "Unknown")),
                album=self.album_data.get("title", ""),
                duration_seconds=t.get("duration", 0),
                duration_str=t.get("duration_str", ""),
                cover_url=self.album_data.get("cover_xl") or self.album_data.get("cover_medium") or "",
                requested_by=self.user_name
            ))

        total = self.player.enqueue_many(album_tracks)
        await interaction.response.send_message(f"📀 Added **{len(album_tracks)} tracks** from *{self.album_data.get('title')}* to the queue! (Total in queue: {total})", ephemeral=True)
        if not self.player.is_playing:
            asyncio.create_task(self.player.play_next())


class SearchResultSelectView(discord.ui.View):
    def __init__(self, player, results: List[dict], user_name: str):
        super().__init__(timeout=60)
        self.player = player
        self.results = results
        self.user_name = user_name

        options = []
        for i, r in enumerate(results[:10]):
            title = r.get("title", "Unknown")[:50]
            artist = r.get("artist", "Unknown")[:45]
            label = f"{artist} - {title}"[:100]
            desc = f"Album: {r.get('album', '')}"[:100] if r.get("album") else "Single"
            options.append(discord.SelectOption(label=label, description=desc, value=str(i)))

        self.select = discord.ui.Select(placeholder="Choose a track to play...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        from .player import AudioTrack
        idx = int(self.select.values[0])
        item = self.results[idx]

        track = AudioTrack(
            title=item.get("title", "Unknown"),
            artist=item.get("artist", "Unknown"),
            album=item.get("album", ""),
            duration_seconds=item.get("duration", 0),
            cover_url=item.get("cover_xl") or item.get("cover") or item.get("cover_medium") or "",
            requested_by=self.user_name
        )

        pos = self.player.enqueue(track)
        await interaction.response.send_message(f"➕ Added **{track.artist} — {track.title}** to queue (Position #{pos})", ephemeral=True)
        if not self.player.is_playing:
            asyncio.create_task(self.player.play_next())
