import asyncio
import discord
from discord import app_commands
from discord.ext import commands

from app.services import official_charts
from core.config import EMBED_COLOR
from core.player import AudioTrack
from core.logger import get_bot_logger

log = get_bot_logger("cogs.charts")

class ChartsCog(commands.Cog, name="Charts & Radio"):
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

    @app_commands.command(name="charts", description="Play official UK, US, or Global charts")
    @app_commands.choices(country=[
        app_commands.Choice(name="🇬🇧 UK Official Top 40", value="gb"),
        app_commands.Choice(name="🇺🇸 Billboard / US Top Hits", value="us"),
        app_commands.Choice(name="🌍 Global Apple Music Top 100", value="global")
    ])
    @app_commands.describe(limit="Number of chart tracks to queue (default: 20)")
    async def charts(self, interaction: discord.Interaction, country: app_commands.Choice[str], limit: int = 20):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        capped_limit = max(1, min(50, limit))
        c_code = "gb" if country.value == "global" else country.value
        data = await asyncio.to_thread(official_charts.get_live_official_charts, country=c_code, limit=capped_limit)
        tracks = data.get("tracks", []) if isinstance(data, dict) else []

        if not tracks:
            await interaction.followup.send(f"❌ Could not retrieve chart data for {country.name}.")
            return

        audio_tracks = []
        for t in tracks[:capped_limit]:
            audio_tracks.append(AudioTrack(
                title=t.get("title", "Unknown"),
                artist=t.get("artist", "Unknown"),
                album=t.get("album", ""),
                duration_seconds=t.get("duration", 0),
                cover_url=t.get("cover") or t.get("cover_xl") or "",
                requested_by=f"{interaction.user.display_name} ({country.name})"
            ))

        total = player.enqueue_many(audio_tracks)
        embed = discord.Embed(
            title=f"🏆 {country.name} Countdown Queued",
            description=f"Added **{len(audio_tracks)} chart tracks** to the queue!\nFirst track: **{audio_tracks[0].artist} — {audio_tracks[0].title}**",
            color=EMBED_COLOR
        )
        if audio_tracks[0].cover_url:
            embed.set_thumbnail(url=audio_tracks[0].cover_url)
        embed.set_footer(text=f"Total in queue: {total}")
        await interaction.followup.send(embed=embed)

        if not player.is_playing:
            asyncio.create_task(player.play_next())

    @app_commands.command(name="radio", description="Stream live DJ and genre stations")
    async def radio(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass
        if not await self._ensure_voice(interaction):
            return

        player = self.bot.player_manager.get_player(interaction.guild)
        player.text_channel = interaction.channel

        stations = await asyncio.to_thread(official_charts.get_live_dj_stations, limit=25)
        if not stations:
            await interaction.followup.send("❌ No radio stations currently available.")
            return

        # Pick top 25 stations for select menu
        options = []
        for i, s in enumerate(stations[:25]):
            name = s.get("title") or s.get("name") or "Radio Station"
            genre = s.get("genre") or s.get("category") or "Vibes"
            options.append(discord.SelectOption(label=name[:100], description=genre[:100], value=str(s.get("id", i))))

        view = discord.ui.View(timeout=60)
        select = discord.ui.Select(placeholder="Choose a radio station to tune into...", options=options)

        async def select_radio_callback(sel_interaction: discord.Interaction):
            radio_id = select.values[0]
            chosen_station = next((s for s in stations if str(s.get("id")) == str(radio_id) or str(s.get("radio_id")) == str(radio_id)), stations[0])
            st_name = chosen_station.get("title") or chosen_station.get("name") or "Station"
            
            await sel_interaction.response.defer(ephemeral=True)
            tracks = chosen_station.get("singles", [])
            if not tracks:
                actual_rid = chosen_station.get("radio_id") or chosen_station.get("id") or radio_id
                tracks = await asyncio.to_thread(official_charts.get_live_radio_tracks, radio_id=str(actual_rid), limit=20)
            if not tracks:
                await sel_interaction.followup.send(f"⚠️ Station **{st_name}** is currently offline.")
                return

            q_tracks = []
            for t in tracks:
                dur = int(t.get("duration") or t.get("dur") or 0)
                q_tracks.append(AudioTrack(
                    title=t.get("title", "Unknown"),
                    artist=t.get("artist", "Unknown"),
                    album=t.get("album", ""),
                    duration_seconds=dur,
                    duration_str=AudioTrack._format_duration(dur) if dur > 0 else "",
                    cover_url=t.get("cover") or "",
                    requested_by=f"Radio: {st_name}"
                ))

            total = player.enqueue_many(q_tracks)
            await sel_interaction.followup.send(f"📻 Tuned into **{st_name}**! Queued **{len(q_tracks)} tracks** (Total in queue: {total})")
            if not player.is_playing:
                asyncio.create_task(player.play_next())

        select.callback = select_radio_callback
        view.add_item(select)

        embed = discord.Embed(
            title="📻 Studio Cloud Radio",
            description="Select a live station from the menu below to start streaming continuous music:",
            color=EMBED_COLOR
        )
        await interaction.followup.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChartsCog(bot))
