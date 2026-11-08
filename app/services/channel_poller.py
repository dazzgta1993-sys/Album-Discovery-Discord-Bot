"""Automatic background poller for subscribed YouTube channels, playlists, and artist feeds."""

import asyncio
import logging
import time
from typing import Optional
import discord
from app import store
from core.player import AudioTrack

log = logging.getLogger("channel_poller")


async def sync_subscription(guild_id: str, sub: dict, bot: Optional[discord.Client] = None) -> int:
    """Sync a single channel or playlist feed into its target Crate playlist."""
    import yt_dlp
    gid = str(guild_id)
    url = sub.get("source_url", "")
    target_pl = sub.get("target_playlist", "Favorites")
    feed_id = sub.get("feed_id", "")
    if not url:
        return 0

    ydl_opts = {"quiet": True, "extract_flat": True, "skip_download": True, "playlistend": 35}
    entries = []
    try:
        def _fetch():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return list(info.get("entries", [])) if info else []
        entries = await asyncio.to_thread(_fetch)
    except Exception as e:
        log.warning(f"Failed to fetch feed {url}: {e}")
        return 0

    added_count = 0
    new_track_names = []
    for e in entries:
        title = e.get("title")
        vid = e.get("id")
        dur = e.get("duration") or 0
        if not title or not vid or dur > 2400:
            continue

        artist = sub.get("display_name") or "Uploader"
        track_title = title
        if " - " in title:
            parts = title.split(" - ", 1)
            artist = parts[0].strip()
            track_title = parts[1].strip()

        thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        payload = {
            "title": track_title,
            "artist": artist,
            "album": target_pl,
            "duration": AudioTrack._format_duration(dur) if dur else "--:--",
            "duration_seconds": int(dur),
            "cover": thumb,
            "video_id": vid,
            "source": "youtube",
        }
        res = store.add_to_crate(gid, payload, playlist_name=target_pl)
        if res.get("added"):
            added_count += 1
            if len(new_track_names) < 3:
                new_track_names.append(f"{artist} - {track_title}")

    if feed_id:
        store.update_crate_subscription_sync(gid, feed_id)

    if added_count > 0:
        log.info(f"[{gid}] Auto-poller synced '{target_pl}': {added_count} new track(s) added from {url}")
        if bot:
            try:
                g = bot.get_guild(int(gid))
                if g:
                    p = bot.player_manager.get_player(g) if hasattr(bot, "player_manager") else None
                    ch = (p.text_channel if p and p.text_channel else None) or g.system_channel
                    if ch:
                        embed = discord.Embed(
                            title="🔔 New Music Added to Crate!",
                            description=f"Auto-poller detected **{added_count} new upload(s)** for **{target_pl}**:\n" + "\n".join(f"• `{t}`" for t in new_track_names),
                            color=0x9d4edd
                        )
                        embed.set_footer(text=f"Auto-sync feed • {sub.get('display_name', 'Uploader')}")
                        await ch.send(embed=embed)
            except Exception as _ex:
                log.debug(f"Poller discord notify notice: {_ex}")

    return added_count


async def sync_all_subscriptions(bot: Optional[discord.Client] = None, guild_id: Optional[str] = None) -> dict:
    """Sync all subscriptions for a guild or all guilds."""
    guild_ids = [guild_id] if guild_id else []
    if not guild_ids and bot:
        guild_ids = [str(g.id) for g in bot.guilds]

    total_added = 0
    results = {}
    for gid in guild_ids:
        subs = store.get_crate_subscriptions(gid)
        guild_added = 0
        for s in subs:
            if s.get("auto_sync", 1):
                c = await sync_subscription(gid, s, bot)
                guild_added += c
        results[gid] = {"synced_feeds": len(subs), "new_tracks": guild_added}
        total_added += guild_added

    return {"status": "ok", "total_new_tracks": total_added, "guilds": results}


async def start_poller_task(bot: discord.Client, interval_seconds: int = 7200):
    """Background task running periodically to keep Crate feeds synchronized."""
    log.info("Channel poller background engine initialized (interval: %ds).", interval_seconds)
    await asyncio.sleep(25.0)
    while not bot.is_closed():
        try:
            log.info("Running scheduled auto-sync for all Crate subscriptions...")
            res = await sync_all_subscriptions(bot)
            log.info("Scheduled Crate auto-sync complete: %s", res.get("total_new_tracks", 0))
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("Channel poller cycle error: %s", e)
        await asyncio.sleep(interval_seconds)
