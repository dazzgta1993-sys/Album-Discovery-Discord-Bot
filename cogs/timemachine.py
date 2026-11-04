import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from app.services import timemachine_service, deezer_api
from core.config import EMBED_COLOR
from core.player import AudioTrack
from core.logger import get_bot_logger

log = get_bot_logger("cogs.timemachine")

class TimeMachineSelectView(discord.ui.View):
    def __init__(self, player, albums: list[dict], year: int, user_name: str):
        super().__init__(timeout=120)
        self.player = player
        self.albums = albums
        self.year = year
        self.user_name = user_name

        options = []
        for i, a in enumerate(albums[:25]):
            title = a.get("title", "Unknown")[:50]
            artist = a.get("artist", "Unknown")[:45]
            label = f"{artist} - {title}"[:100]
            desc = f"Landmark Album ({year})"
            options.append(discord.SelectOption(label=label, description=desc, value=str(i)))

        if options:
            self.select = discord.ui.Select(placeholder=f"Select an album from {year} to play...", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        idx = int(self.select.values[0])
        alb = self.albums[idx]
        alb_id = alb.get("id") or alb.get("deezer_id")
        alb_title = alb.get("title", "Unknown Album")
        alb_artist = alb.get("artist", "Unknown Artist")

        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        clean_aid = str(alb_id or "").strip()
        while clean_aid.startswith("mb_"):
            clean_aid = clean_aid[3:]

        full_alb = None
        if clean_aid.isdigit():
            full_alb = await asyncio.to_thread(deezer_api.get_album_details, clean_aid)
        if not full_alb or not full_alb.get("tracks"):
            found = await asyncio.to_thread(deezer_api.search_albums, f"{alb_artist} {alb_title}".strip(), limit=1)
            if found:
                full_alb = await asyncio.to_thread(deezer_api.get_album_details, str(found[0]["id"]))

        tracks = full_alb.get("tracks", []) if full_alb else []
        cover = (full_alb.get("cover") if full_alb else None) or alb.get("cover_xl") or alb.get("cover") or ""

        if not tracks:
            track = AudioTrack(
                title=alb_title,
                artist=alb_artist,
                album=alb_title,
                cover_url=cover,
                requested_by=self.user_name
            )
            pos = self.player.enqueue(track)
            await interaction.followup.send(f"⏳ Added **{track.artist} — {track.title}** to queue (Position #{pos})")
        else:
            q_tracks = []
            for t in tracks:
                dur = int(t.get("duration", 0))
                q_tracks.append(AudioTrack(
                    title=t.get("title", "Unknown"),
                    artist=t.get("artist", alb_artist),
                    album=alb_title,
                    duration_seconds=dur,
                    duration_str=AudioTrack._format_duration(dur),
                    cover_url=cover,
                    requested_by=self.user_name
                ))
            total = self.player.enqueue_many(q_tracks)
            await interaction.followup.send(f"⏳ Queued landmark album **{alb_artist} — {alb_title}** ({self.year})! ({len(q_tracks)} tracks, total queue: {total})")

        if not self.player.is_playing:
            asyncio.create_task(self.player.play_next())


class TimeMachineCog(commands.Cog, name="Time Machine"):
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

    @app_commands.command(name="timemachine", description="Play landmark albums by year (1960-2026)")
    @app_commands.describe(year="Year between 1960 and 2026")
    async def timemachine(self, interaction: discord.Interaction, year: int):
        if year < 1960 or year > 2026:
            await interaction.response.send_message("❌ Please specify a year between **1960** and **2026**.", ephemeral=True)
            return

        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        res = await asyncio.to_thread(timemachine_service.get_timemachine_albums, year=year, limit=20)
        albums = res.get("albums", []) if isinstance(res, dict) else []
        if not albums:
            await interaction.followup.send(f"❌ No landmark archives found for the year **{year}**.")
            return

        embed = discord.Embed(
            title=f"⏳ Time Machine: The Landmark Albums of {year}",
            description=f"Curated iconic releases that shaped musical history in **{year}**:\n",
            color=EMBED_COLOR
        )

        first_album = albums[0]
        if first_album.get("cover_xl") or first_album.get("cover") or first_album.get("cover_medium"):
            embed.set_thumbnail(url=first_album.get("cover_xl") or first_album.get("cover") or first_album.get("cover_medium"))

        lines = []
        for i, a in enumerate(albums[:8], 1):
            lines.append(f"{i}. **{a.get('artist')}** — *{a.get('title')}*")
        embed.add_field(name="Featured Albums", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"Total {len(albums)} landmarks available for {year} | Select below to play")

        view = TimeMachineSelectView(player, albums, year, interaction.user.display_name)
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(TimeMachineCog(bot))
