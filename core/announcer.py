"""Album Discovery - Channel Announcer & Live Player Card Manager.
Binds a designated Discord text channel to maintain a live, interactive 
Now Playing card with real-time in-place updates across song transitions.
"""
import asyncio
import discord
from typing import Optional
from core.logger import get_bot_logger

log = get_bot_logger("announcer")


def get_bound_channel_id(player) -> Optional[str]:
    """Retrieve the bound text channel ID for this player's guild."""
    if not player or not player.guild:
        return None
    val = getattr(player, "bound_channel_id", None)
    if val:
        return str(val)
    try:
        from app import store
        settings = store.load_guild_settings(str(player.guild.id))
        stored_id = settings.get("bound_channel_id")
        if stored_id:
            player.bound_channel_id = str(stored_id)
            return str(stored_id)
    except Exception as e:
        log.debug(f"Store lookup notice: {e}")
    return None


def get_target_channel(player) -> Optional[discord.TextChannel]:
    """Resolve the active Discord text channel for announcements."""
    if not player or not player.guild:
        return None
    ch_id = get_bound_channel_id(player)
    if ch_id:
        try:
            ch = player.guild.get_channel(int(ch_id))
            if hasattr(ch, "send"):
                player.text_channel = ch
                return ch
        except (ValueError, TypeError):
            pass
    return player.text_channel


def set_bound_channel(player, channel_id: Optional[str]) -> bool:
    """Set or clear the bound text channel for this guild."""
    if not player or not player.guild:
        return False
    clean_id = str(channel_id).strip() if channel_id else None
    if clean_id in ("", "none", "null", "clear", "0"):
        clean_id = None

    player.bound_channel_id = clean_id
    if clean_id:
        try:
            player.text_channel = player.guild.get_channel(int(clean_id))
        except Exception:
            pass
    else:
        player.text_channel = None

    try:
        from app import store
        store.save_guild_settings(str(player.guild.id), {"bound_channel_id": clean_id})
        return True
    except Exception as e:
        log.warning(f"Failed to persist bound channel: {e}")
        return False


async def announce_track(player, track) -> None:
    """Send or edit the live interactive Now Playing card in the bound channel."""
    if not player or not track:
        return
    channel = get_target_channel(player)
    if not channel:
        return

    try:
        from core.ui import PlayerControlsView
        embed = player._build_now_playing_embed(track)
        view = PlayerControlsView(player)

        # Recovery: Look for an existing bot player card in recent history
        if not player.current_message:
            try:
                async for m in channel.history(limit=20):
                    if m.author == player.bot.user and m.embeds and m.components:
                        player.current_message = m
                        break
            except Exception as _ex:
                log.debug(f"History scan notice: {_ex}")

        # Check drift if other members chatted in the channel
        drifted = False
        if not player.current_message:
            drifted = True
        else:
            try:
                drift_count = 0
                async for _ in channel.history(limit=12, after=player.current_message):
                    drift_count += 1
                    if drift_count >= 8:
                        drifted = True
                        break
            except (discord.NotFound, discord.HTTPException):
                drifted = True

        if drifted:
            if player.current_message:
                try:
                    await player.current_message.delete()
                except (discord.NotFound, discord.HTTPException):
                    pass
            player.current_message = await channel.send(embed=embed, view=view)
        else:
            try:
                await player.current_message.edit(embed=embed, view=view)
            except discord.NotFound:
                player.current_message = await channel.send(embed=embed, view=view)
    except Exception as e:
        log.warning(f"Announcer failed to post Now Playing card: {e}")


async def clear_announced_card(player) -> None:
    """Cleanly delete the live card on stop or disconnect."""
    msg = getattr(player, "current_message", None)
    if msg:
        try:
            await msg.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        player.current_message = None
