import asyncio
import os
import sys

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.logger import get_bot_logger, configure_discord_logging
configure_discord_logging()
log = get_bot_logger("bot")

# Windows Console UTF-8 Guardrail: Prevent charmap UnicodeEncodeErrors on emojis and international artist names
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception as _ex:
        log.debug(f'Bot notice: {_ex}')
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as _ex:
        log.debug(f'Bot notice: {_ex}')

import discord
from discord.ext import commands

# Auto-load Opus DLL on Windows for voice playback
from discord import opus
if not opus.is_loaded():
    candidates = [
        os.path.join(ROOT_DIR, "opus.dll"),
        os.path.join(os.path.dirname(discord.__file__), "bin", "opus.dll"),
        os.path.join(os.path.dirname(discord.__file__), "bin", "libopus-0.x64.dll"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            try:
                opus.load_opus(c)
                break
            except Exception as _ex:
                log.debug(f'Bot notice: {_ex}')

from core.config import BOT_TOKEN, COMMAND_PREFIX, WEB_ENABLED, WEB_HOST, WEB_PORT
from core.player import PlayerManager

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

class AlbumDiscoveryBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            help_command=None
        )
        self.player_manager = PlayerManager(self)
        self._web_runner = None

    async def setup_hook(self):
        self.loop = asyncio.get_running_loop()
        cogs = ["cogs.music", "cogs.discovery", "cogs.timemachine", "cogs.charts"]
        for cog in cogs:
            try:
                await self.load_extension(cog)
            except Exception as e:
                log.error(f"Failed to load extension {cog}: {e}")

        # Sync application slash commands with Discord
        try:
            await self.tree.sync()
        except Exception as e:
            log.error(f"Failed to sync slash commands: {e}")

    async def on_ready(self):
        # Purge duplicate guild-scoped commands so each slash command appears exactly once
        for g in self.guilds:
            try:
                self.tree.clear_commands(guild=g)
                await self.tree.sync(guild=g)
                log.info(f"Purged duplicate guild-scoped commands in: {g.name} ({g.id})")
            except Exception as e:
                log.debug(f"Guild command cleanup notice for {g.id}: {e}")
        if WEB_ENABLED and not self._web_runner:
            try:
                from web.server import start_web_server
                self._web_runner = await start_web_server(self, host=WEB_HOST, port=WEB_PORT)
            except Exception as e:
                log.critical(f"Failed to start Web Control Hub on port {WEB_PORT}: {e}")
                log.critical("Port conflict detected. Terminating process to prevent ghost bot conflicts.")
                await self.close()
                sys.exit(1)

        web_url = f"http://localhost:{WEB_PORT}" if WEB_HOST in ("0.0.0.0", "127.0.0.1") else f"http://{WEB_HOST}:{WEB_PORT}"

        print("\n" + "=" * 58)
        print("   ALBUM DISCOVERY DISCORD BOT - ONLINE")
        print(f"   Logged in as : {self.user}")
        print(f"   Servers      : {len(self.guilds)}")
        cmd_count = len(self.tree.get_commands())
        print(f"   Commands     : {cmd_count} Slash Commands Active")
        print(f"   Voice Engine : Ready (Opus 48kHz Stereo)")
        if WEB_ENABLED:
            print(f"   Web Hub      : {web_url}")
        print("=" * 58 + "\n")

        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name="/play | Album Discovery"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)
        asyncio.create_task(self._check_startup_autoplay())
        from app.services import channel_poller
        asyncio.create_task(channel_poller.start_poller_task(self))

    async def _check_startup_autoplay(self):
        """If startup_autoplay is enabled, automatically join active voice channel and begin playback."""
        await asyncio.sleep(2.0)
        for guild in self.guilds:
            try:
                player = self.player_manager.get_player(guild)
                if not getattr(player, "startup_autoplay", True):
                    log.info(f"[{guild.name}] Startup auto-play disabled by settings.")
                    continue
                if player.is_playing or (player.voice_client and player.voice_client.is_connected()):
                    continue
                target_vc = None
                for vc in guild.voice_channels:
                    human_members = [m for m in vc.members if not m.bot]
                    if len(human_members) > 0:
                        target_vc = vc
                        break
                if target_vc:
                    log.info(f"[{guild.name}] Startup auto-play detected listener(s) in '{target_vc.name}'. Connecting...")
                    connected = await player.connect(target_vc)
                    if connected and not player.is_playing:
                        player.autoplay = True
                        player._is_stopped = False
                        log.info(f"[{guild.name}] Startup auto-play: launching Brain DJ autoplay stream...")
                        asyncio.create_task(player.play_next())
            except Exception as e:
                log.warning(f"Startup autoplay notice for {guild.name}: {e}")

    async def on_voice_state_update(self, member, before, after):
        # 1. If the bot itself was disconnected from a voice channel, stop playback immediately and do not auto-reconnect
        if self.user and member.id == self.user.id and before.channel and not after.channel:
            guild = before.channel.guild
            player = self.player_manager.players.get(guild.id)
            if player:
                log.info(f"[{guild.name}] Bot was disconnected from voice channel. Stopping playback.")
                player.stop()
                await player.disconnect()
            return

        # 2. Auto-disconnect only if everyone leaves, player is idle, and Autoplay is OFF
        if before.channel and (not after.channel or before.channel.id != after.channel.id):
            guild = before.channel.guild
            player = self.player_manager.players.get(guild.id)
            if player and player.voice_client and player.voice_client.channel:
                if before.channel.id == player.voice_client.channel.id:
                    channel = player.voice_client.channel
                    non_bots = [m for m in channel.members if not m.bot]
                    if len(non_bots) == 0:
                        if not player.is_playing and not player.autoplay and len(player.queue) == 0:
                            log.info(f"[{guild.name}] Voice channel is empty, player idle, and autoplay off. Disconnecting.")
                            await player.disconnect()
                        else:
                            log.info(f"[{guild.name}] Voice channel is empty, but playback/autoplay is active. Web audio preserved.")

        # 3. Auto-join if user joins voice and bot is disconnected with startup_autoplay enabled
        if after.channel and not member.bot and (not before.channel or before.channel.id != after.channel.id):
            guild = after.channel.guild
            player = self.player_manager.get_player(guild)
            if player and not player.is_connected and not player.is_playing:
                if getattr(player, "startup_autoplay", True):
                    log.info(f"[{guild.name}] User '{member.display_name}' joined '{after.channel.name}'. Auto-joining...")
                    try:
                        connected = await player.connect(after.channel)
                        if connected and not player.is_playing:
                            player.autoplay = True
                            player._is_stopped = False
                            asyncio.create_task(player.play_next())
                    except Exception as e:
                        log.debug(f"Auto-join notice: {e}")

    async def on_guild_remove(self, guild: discord.Guild):
        log.info(f"Removed from guild {guild.name} ({guild.id}). Cleaning up player state.")
        await self.player_manager.remove_player(guild.id)

    async def close(self):
        if self._web_runner:
            try:
                from web.server import stop_web_server
                await stop_web_server(self._web_runner)
            except Exception as e:
                log.warning(f"Error shutting down web server: {e}")
        await super().close()


def ensure_single_instance():
    """Guarantee only one instance of bot.py runs, preventing duplicate ghost processes."""
    try:
        import psutil
        my_pid = os.getpid()
        parent_pid = os.getppid() if hasattr(os, "getppid") else None
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                p_id = proc.pid
                if p_id in (my_pid, parent_pid):
                    continue
                name = (proc.info.get("name") or "").lower()
                if "python" in name:
                    cmd = proc.info.get("cmdline") or []
                    if any("bot.py" in str(arg) for arg in cmd) and not any("-c" in str(arg) for arg in cmd):
                        log.info(f"Terminated previous bot instance (PID {p_id}) to ensure clean single-process startup.")
                        proc.kill()
                        proc.wait(timeout=2)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
    except Exception as _ex:
        log.debug(f"Single-instance check notice: {_ex}")


def main():
    ensure_single_instance()
    token = BOT_TOKEN.strip()
    if not token or token == "your_token_here":
        print("\n" + "=" * 65)
        print(" [!] DISCORD BOT TOKEN NOT CONFIGURED")
        print("=" * 65)
        print(" 1. Go to Discord Developer Portal: https://discord.com/developers/applications")
        print(" 2. Create an Application -> Click 'Bot' -> Click 'Reset Token' / 'Copy'")
        print(" 3. Open .env file in this directory and paste your token:")
        print("    DISCORD_BOT_TOKEN=your_copied_token_here")
        print(" 4. Enable 'MESSAGE CONTENT INTENT' under the Bot tab in the portal.")
        print("=" * 65 + "\n")
        sys.exit(1)

    bot = AlbumDiscoveryBot()
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
