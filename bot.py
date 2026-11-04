import asyncio
import os
import sys

# Windows Console UTF-8 Guardrail: Prevent charmap UnicodeEncodeErrors on emojis and international artist names
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import discord
from discord.ext import commands

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

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
            except Exception:
                pass

from core.config import BOT_TOKEN, COMMAND_PREFIX, WEB_ENABLED, WEB_HOST, WEB_PORT
from core.logger import get_bot_logger, configure_discord_logging
from core.player import PlayerManager

configure_discord_logging()
log = get_bot_logger("bot")

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
                log.error(f"Failed to start Web Control Hub: {e}")

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

    async def on_voice_state_update(self, member, before, after):
        # Auto-disconnect only if everyone leaves, player is idle, and Autoplay is OFF
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

    async def close(self):
        if self._web_runner:
            try:
                from web.server import stop_web_server
                await stop_web_server(self._web_runner)
            except Exception as e:
                log.warning(f"Error shutting down web server: {e}")
        await super().close()


def main():
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
