import asyncio
import os
import collections
import random
import re
import time
from typing import Optional, List, Dict, Any
import discord

from app.services import stream_service, deezer_api, official_charts
from app.utils.normalizer import is_junk_album
from .config import DEFAULT_VOLUME, IDLE_DISCONNECT_SECONDS, AUTOPLAY_DJ, EMBED_COLOR
from core.logger import get_bot_logger

log = get_bot_logger("player")

class AudioTrack:
    def __init__(self, title: str, artist: str, album: str = "", duration_seconds: int = 0, duration_str: str = "", cover_url: str = "", video_id: Optional[str] = None, stream_url: Optional[str] = None, requested_by: Optional[str] = None, source: str = "deezer", is_autoplay: bool = False):
        self.title, self.artist, self.album = title, artist, album
        self.duration_seconds = duration_seconds
        self.duration_str = duration_str or self._format_duration(duration_seconds)
        self.cover_url, self.video_id, self.stream_url = cover_url, video_id, stream_url
        self.requested_by, self.source, self.is_autoplay = requested_by, source, is_autoplay
        self.stream_headers = {}

    @staticmethod
    def _format_duration(secs: int) -> str:
        if not secs:
            return "--:--"
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def to_dict(self) -> dict:
        return {"title": self.title, "artist": self.artist, "album": self.album, "duration": self.duration_str, "cover": self.cover_url, "requested_by": self.requested_by, "is_autoplay": getattr(self, "is_autoplay", False), "source": getattr(self, "source", "deezer")}

class AccurateAudioSource(discord.PCMVolumeTransformer):
    """Precision audio stream wrapper measuring decoded 48kHz 16-bit stereo PCM frames."""
    def __init__(self, original, volume: float = 1.0):
        super().__init__(original, volume=volume)
        self.bytes_read: int = 0
        self.first_read_time: float = 0.0

    def read(self) -> bytes:
        ret = super().read()
        if not ret: return ret
        if self.first_read_time == 0.0: self.first_read_time = time.time()
        self.bytes_read += len(ret)
        return ret

    def elapsed_seconds(self) -> float:
        return self.bytes_read / 192000.0 if self.bytes_read else 0.0

    def cleanup(self):
        try:
            if hasattr(self.original, "cleanup"):
                self.original.cleanup()
            elif hasattr(self.original, "_process") and self.original._process:
                self.original._process.kill()
        except Exception as _ex:
            log.debug(f"Source cleanup notice: {_ex}")

class GuildPlayer:
    def __init__(self, bot: discord.Client, guild: discord.Guild):
        self.bot = bot
        self.guild = guild
        self.voice_client: Optional[discord.VoiceClient] = None
        self.text_channel: Optional[discord.TextChannel] = None
        
        self.queue: collections.deque[AudioTrack] = collections.deque()
        self.history: collections.deque[AudioTrack] = collections.deque(maxlen=50)
        self.current_track: Optional[AudioTrack] = None
        
        self.volume: float = DEFAULT_VOLUME
        self.loop_mode: str = "off"  # "off", "track", "queue"
        self.autoplay: bool = AUTOPLAY_DJ
        self.audio_quality: str = "auto"
        
        self._is_playing: bool = False
        self.play_start_time: float = 0.0
        self.total_paused_time: float = 0.0
        self.pause_start_time: float = 0.0
        self._progress_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._active_source: Optional[AccurateAudioSource] = None
        self.current_message: Optional[discord.Message] = None
        self._prewarmed_autoplay_track: Optional[AudioTrack] = None
        self._deck3_autoplay_track: Optional[AudioTrack] = None
        self.vibe_anchor_artist: Optional[str] = None
        self.is_anchor_locked: bool = False
        self.consecutive_autoplay_count: int = 0
        self.failed_tracks: set[str] = set()
        self._consecutive_resolve_failures: int = 0

        # Brain Hub & Autoplay Control Engine
        self.vibe_mode: str = "balanced"  # "deep_dive", "collabs", "balanced", "discovery"
        self.vibe_drift_freq: int = 1     # Songs to stay before drifting (Default 1: Fresh artist every track)
        self.hit_depth: str = "balanced"  # "top_hits", "balanced", "deep_cuts"
        self.deck2_enabled: bool = True   # Deck 2 standby zero-gap preloader
        self.deck3_enabled: bool = True   # Deck 3 pipeline preloader
        self._was_manually_skipped: bool = False
        self.explicit_filter: str = "allow" # "allow", "clean_only"
        self.artist_cooldown: int = 10     # Authentic radio: 10 songs before an artist can repeat
        self.era_filter: str = "all"       # "all", "2020s", "2010s", "2000s", "classics"
        self.vibe_energy: str = "auto"     # "auto", "high", "chill"
        self.vibe_engine_source: str = "auto" # "auto", "ytmusic", "deezer", "spotify", "musicbrainz"

        # Load saved persistent brain configuration & playback history from SQLite store
        try:
            from app import store
            saved_hist = store.load_playback_history(str(self.guild.id), limit=50)
            for td in saved_hist:
                self.history.append(AudioTrack(
                    title=td.get("title", "Unknown"), artist=td.get("artist", "Unknown"),
                    album=td.get("album", ""), duration_seconds=int(td.get("duration_seconds") or 0),
                    cover_url=td.get("cover") or td.get("cover_url") or "", requested_by="Played", source=td.get("source", "history")
                ))
            saved = store.load_guild_settings(str(self.guild.id))
            if saved:
                if "vibe_mode" in saved: self.vibe_mode = str(saved["vibe_mode"])
                if "vibe_drift_freq" in saved: self.vibe_drift_freq = int(saved["vibe_drift_freq"])
                if "hit_depth" in saved: self.hit_depth = str(saved["hit_depth"])
                if "deck2_enabled" in saved: self.deck2_enabled = bool(saved["deck2_enabled"])
                if "deck3_enabled" in saved: self.deck3_enabled = bool(saved["deck3_enabled"])
                if "explicit_filter" in saved: self.explicit_filter = str(saved["explicit_filter"])
                if "artist_cooldown" in saved: self.artist_cooldown = int(saved["artist_cooldown"])
                if "era_filter" in saved: self.era_filter = str(saved["era_filter"])
                if "vibe_energy" in saved: self.vibe_energy = str(saved["vibe_energy"])
                if "vibe_engine_source" in saved: self.vibe_engine_source = str(saved["vibe_engine_source"])
                if "autoplay" in saved: self.autoplay = bool(saved["autoplay"])
                if "audio_quality" in saved and str(saved["audio_quality"]) in ("auto", "128k", "192k", "320k"):
                    self.audio_quality = str(saved["audio_quality"])
                if "loop_mode" in saved and str(saved["loop_mode"]) in ("off", "track", "queue"):
                    self.loop_mode = str(saved["loop_mode"])
                if "volume" in saved:
                    try: self.volume = max(0.0, min(1.0, float(saved["volume"])))
                    except Exception as _ex: log.debug(f'Player setting notice: {_ex}')
                if "is_anchor_locked" in saved: self.is_anchor_locked = bool(saved["is_anchor_locked"])
        except Exception as _ex:
            log.debug(f'Player notice: {_ex}')
        self.last_brain_decision: str = "Brain System Online • Standby"

    @property
    def is_playing(self) -> bool:
        if getattr(self, "_is_stopped", False):
            return False
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            return True
        return bool(getattr(self, "_is_playing", False))

    @is_playing.setter
    def is_playing(self, value: bool):
        self._is_playing = bool(value)

    def _cleanup_active_source(self):
        src = self._active_source
        self._active_source = None
        if src and hasattr(src, "cleanup"):
            try:
                src.cleanup()
            except Exception as _ex:
                log.debug(f"Source cleanup notice: {_ex}")

    @property
    def is_connected(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    def get_progress(self) -> tuple[int, int]:
        """Returns smooth, sample-synchronized (elapsed_seconds, total_seconds).
        Prioritizes continuous wall-clock time so audio buffer bursts never cause elapsed jumps.
        """
        if not self.current_track:
            return 0, 0
        if self.play_start_time > 0:
            if self.pause_start_time > 0:
                elapsed = int(self.pause_start_time - self.play_start_time - self.total_paused_time)
            else:
                elapsed = int(time.time() - self.play_start_time - self.total_paused_time)
        elif getattr(self, "_active_source", None) and hasattr(self._active_source, "elapsed_seconds"):
            elapsed = int(self._active_source.elapsed_seconds)
        else:
            elapsed = 0

        elapsed = max(0, elapsed)
        total = self.current_track.duration_seconds
        if total > 0 and elapsed > total:
            elapsed = total
        return elapsed, total

    def get_progress_bar(self, bar_length: int = 10) -> str:
        """Returns an authentic, sleek VLC-style live scrubber with clear filled track and knob."""
        if not self.current_track:
            return ""
        elapsed, total = self.get_progress()
        is_paused = bool(self.voice_client and self.voice_client.is_paused())
        status_icon = "⏸️" if is_paused else "▶️"
        el_str = AudioTrack._format_duration(elapsed)

        if not total or total <= 0:
            return f"{status_icon} `{el_str}` ──────────🔘 *(Live)*"

        tot_str = AudioTrack._format_duration(total)
        fraction = min(1.0, max(0.0, elapsed / total))
        dot_pos = int(round(fraction * bar_length))
        dot_pos = max(0, min(bar_length, dot_pos))

        # Real media player track:
        # Left side is bold solid filled track (━)
        # Knob is active scrubber handle (🔘)
        # Right side is light groove (─)
        left = "━" * dot_pos
        right = "─" * (bar_length - dot_pos)
        bar = f"{left}🔘{right}"

        if is_paused:
            return f"{status_icon} `{el_str}` {bar} `{tot_str}` *(Paused)*"

        return f"{status_icon} `{el_str}` {bar} `{tot_str}`"

    def _start_progress_task(self):
        self._cancel_progress_task()
        async def _progress_loop():
            try:
                loop_count = 0
                last_bar_text = ""
                while self.is_playing and self.voice_client and self.voice_client.is_connected():
                    # 15s interval respects Discord API message edit rate limits while pre-warming upcoming decks
                    await asyncio.sleep(15.0)
                    if not self.is_playing or not self.voice_client or not self.voice_client.is_connected():
                        break
                    if self.voice_client.is_paused():
                        continue
                    loop_count += 1
                    asyncio.create_task(self._prewarm_next_track())
                    cur_bar = self.get_progress_bar()
                    if cur_bar != last_bar_text:
                        last_bar_text = cur_bar
                        await self.update_player_message()
            except asyncio.CancelledError:
                pass
            except discord.HTTPException:
                await asyncio.sleep(2.5)
            except Exception as e:
                log.debug(f"Progress loop notice: {e}")
        self._progress_task = asyncio.create_task(_progress_loop())

    def _cancel_progress_task(self):
        if self._progress_task and not self._progress_task.done():
            self._progress_task.cancel()
            self._progress_task = None

    async def connect(self, channel: discord.VoiceChannel, text_channel: Optional[discord.TextChannel] = None) -> bool:
        if text_channel:
            self.text_channel = text_channel
            
        # Check active voice client on player or guild
        existing_vc = self.voice_client or self.guild.voice_client
        if existing_vc and existing_vc.is_connected():
            self.voice_client = existing_vc
            if self.voice_client.channel.id != channel.id:
                await self.voice_client.move_to(channel)
            self._cancel_idle_timer()
            return True
        try:
            self.voice_client = await channel.connect(timeout=45.0, reconnect=True, self_deaf=True)
            self._cancel_idle_timer()
            return True
        except discord.ClientException:
            # Already connected in guild, bind existing client
            if self.guild.voice_client and self.guild.voice_client.is_connected():
                self.voice_client = self.guild.voice_client
                if self.voice_client.channel.id != channel.id:
                    await self.voice_client.move_to(channel)
                self._cancel_idle_timer()
                return True
            return False
        except Exception as e:
            log.error(f"Failed to connect to voice channel in {self.guild.name}: {e}")
            return False

    @property
    def deck2_track(self) -> Optional[AudioTrack]:
        if len(self.queue) > 0:
            return self.queue[0]
        if self.autoplay and self._prewarmed_autoplay_track:
            return self._prewarmed_autoplay_track
        return None

    @property
    def deck3_track(self) -> Optional[AudioTrack]:
        if len(self.queue) > 1:
            return self.queue[1]
        if len(self.queue) == 1 and self.autoplay:
            return self._prewarmed_autoplay_track
        if len(self.queue) == 0 and self.autoplay:
            return self._deck3_autoplay_track
        return None

    async def _prewarm_track(self, target: Optional[AudioTrack]) -> bool:
        if not target or target.stream_url:
            return False
        try:
            if not target.video_id:
                if target.source == "youtube":
                    yt_tracks = await asyncio.to_thread(stream_service.search_youtube_tracks, target.title, limit=1)
                    if yt_tracks:
                        raw_vid = yt_tracks[0].get("video_id") or yt_tracks[0].get("id", "")
                        target.video_id = raw_vid.replace("yt_", "")
                        if yt_tracks[0].get("duration") and not target.duration_seconds:
                            target.duration_seconds = int(yt_tracks[0]["duration"])
                            target.duration_str = AudioTrack._format_duration(target.duration_seconds)
                else:
                    res = await asyncio.to_thread(stream_service.resolve_track_stream, artist=target.artist, title=target.title, album=target.album, duration=target.duration_seconds)
                    if res and res.get("id"):
                        target.video_id = res["id"]
                        if res.get("duration"):
                            try:
                                dur = int(res["duration"])
                                if not target.duration_seconds or target.duration_seconds <= 0:
                                    target.duration_seconds = dur
                                target.duration_str = AudioTrack._format_duration(dur)
                            except Exception as _ex:
                                log.debug(f'Player notice: {_ex}')
            if target.video_id and not target.stream_url:
                s_url, hdrs = await asyncio.to_thread(stream_service.get_stream_info, target.video_id, self.audio_quality)
                if s_url:
                    target.stream_url = s_url
                    return True
        except Exception as e:
            log.debug(f"Prewarm track notice: {e}")
        return False

    async def _prewarm_next_track(self):
        """Preloads Deck 2 (Next Up) and Deck 3 (In The Chute) for zero-buffer transitions."""
        if not self.deck2_enabled and not self.deck3_enabled:
            return
        try:
            # 1. Deck 2 Target (Next In Line)
            if self.deck2_enabled:
                t2 = None
                if len(self.queue) > 0:
                    t2 = self.queue[0]
                elif self.autoplay and self.current_track:
                    if not self._prewarmed_autoplay_track:
                        self._prewarmed_autoplay_track = await self._fetch_autoplay_vibe_track(seed_track=self.current_track)
                        if self._prewarmed_autoplay_track:
                            self._prewarmed_autoplay_track.is_autoplay = True
                    t2 = self._prewarmed_autoplay_track

                if t2:
                    ready2 = await self._prewarm_track(t2)
                    if ready2:
                        log.info(f"[{self.guild.name}] Deck 2 Ready: {t2.artist} - {t2.title}")

# 2. Deck 3 Target (Two Steps Ahead, seeded by Deck 2 for harmonic progression)
            if self.deck3_enabled:
                t3 = None
                if len(self.queue) > 1:
                    t3 = self.queue[1]
                elif len(self.queue) == 1 and self.autoplay:
                    if not self._deck3_autoplay_track:
                        self._deck3_autoplay_track = await self._fetch_autoplay_vibe_track(seed_track=self.queue[0])
                        if self._deck3_autoplay_track:
                            self._deck3_autoplay_track.is_autoplay = True
                    t3 = self._deck3_autoplay_track
                elif len(self.queue) == 0 and self.autoplay and self.current_track:
                    if not self._deck3_autoplay_track:
                        deck3_seed = self._prewarmed_autoplay_track or self.current_track
                        self._deck3_autoplay_track = await self._fetch_autoplay_vibe_track(seed_track=deck3_seed)
                        if self._deck3_autoplay_track:
                            self._deck3_autoplay_track.is_autoplay = True
                    t3 = self._deck3_autoplay_track

                if t3:
                    ready3 = await self._prewarm_track(t3)
                    if ready3:
                        log.info(f"[{self.guild.name}] Deck 3 Cued: {t3.artist} - {t3.title}")

            asyncio.create_task(self.update_player_message())
        except Exception as e:
            log.debug(f"Deck pipeline prewarm notice: {e}")

    def enqueue(self, track: AudioTrack, at_front: bool = False) -> int:
        self._is_stopped = False
        self._cancel_idle_timer()
        self._prewarmed_autoplay_track = None
        self._deck3_autoplay_track = None
        if at_front:
            self.queue.appendleft(track)
            pos = 1
        else:
            self.queue.append(track)
            pos = len(self.queue)
        is_auto = bool(
            getattr(track, "is_autoplay", False)
            or (track.requested_by and any(k in track.requested_by.lower() for k in ("autoplay", "brain dj")))
            or getattr(track, "source", "") == "autoplay"
        )
        if not is_auto:
            self.vibe_anchor_artist = track.artist
            self.consecutive_autoplay_count = 0
        log.info(f"[{self.guild.name}] Enqueued track '{track.artist} - {track.title}' (Position: {pos})")
        asyncio.create_task(self.update_player_message())
        if self.is_playing:
            asyncio.create_task(self._prewarm_next_track())
        return pos

    def enqueue_many(self, tracks: List[AudioTrack], at_front: bool = False) -> int:
        self._is_stopped = False
        self._cancel_idle_timer()
        self._prewarmed_autoplay_track = None
        self._deck3_autoplay_track = None
        if at_front:
            for t in reversed(tracks):
                self.queue.insert(0, t)
        else:
            for t in tracks:
                self.queue.append(t)
        log.info(f"[{self.guild.name}] Enqueued {len(tracks)} tracks (at_front={at_front}). Total queue length: {len(self.queue)}")
        asyncio.create_task(self.update_player_message())
        if self.is_playing:
            asyncio.create_task(self._prewarm_next_track())
        return len(self.queue)

    async def play_next(self):
        if getattr(self, "_is_stopped", False):
            self.is_playing = False
            return
        async with self._lock:
            now = time.time()
            if not getattr(self, "_was_manually_skipped", False) and getattr(self, "_last_play_start_time", 0.0) > 0:
                if now - self._last_play_start_time < 0.8:
                    log.debug(f"[{self.guild.name}] play_next throttled to prevent rapid-skip cascade.")
                    return
            if getattr(self, "_is_stopped", False):
                self.is_playing = False
                return
            was_skipped = getattr(self, "_was_manually_skipped", False)
            self._was_manually_skipped = False
            # Sync voice client state with discord guild
            if not self.voice_client or not self.voice_client.is_connected():
                if self.guild.voice_client and self.guild.voice_client.is_connected():
                    self.voice_client = self.guild.voice_client
                else:
                    for _ in range(5):
                        await asyncio.sleep(0.5)
                        if self.guild.voice_client and self.guild.voice_client.is_connected():
                            self.voice_client = self.guild.voice_client
                            break
                        if self.voice_client and self.voice_client.is_connected():
                            break

            if getattr(self, "_is_stopped", False):
                self.is_playing = False
                return

            if not self.voice_client or not self.voice_client.is_connected():
                target_channel = getattr(self.voice_client, "channel", None) or (self.guild.voice_channels[0] if self.guild.voice_channels else None)
                if target_channel:
                    log.info(f"[{self.guild.name}] Reconnecting voice client to '{target_channel.name}' to continue playback/autoplay...")
                    connected = await self.connect(target_channel)
                    if not connected:
                        log.warning(f"[{self.guild.name}] play_next aborted: could not reconnect voice client.")
                        self.is_playing = False
                        return
                else:
                    log.warning(f"[{self.guild.name}] play_next aborted: voice client disconnected.")
                    self.is_playing = False
                    return

            if self.loop_mode == "track" and self.current_track:
                next_track = self.current_track
            elif len(self.queue) > 0:
                if self.loop_mode == "queue" and self.current_track:
                    self.queue.append(self.current_track)
                next_track = self.queue.popleft()
            else:
                if self.autoplay:
                    if self._prewarmed_autoplay_track:
                        next_track = self._prewarmed_autoplay_track
                        self._prewarmed_autoplay_track = self._deck3_autoplay_track
                        self._deck3_autoplay_track = None
                    elif self._deck3_autoplay_track:
                        next_track = self._deck3_autoplay_track
                        self._deck3_autoplay_track = None
                    else:
                        seed = self.current_track or (self.history[-1] if self.history else None)
                        next_track = await self._fetch_autoplay_vibe_track(seed_track=seed)
                    if not next_track:
                        self.current_track = None
                        self.is_playing = False
                        self._start_idle_timer()
                        return
                else:
                    self.current_track = None
                    self.is_playing = False
                    self._start_idle_timer()
                    return

            self.current_track = next_track
            if next_track not in self.history:
                self.history.append(next_track)
                try:
                    from app import store
                    store.save_playback_history(str(self.guild.id), next_track.to_dict())
                except Exception as _ex:
                    log.debug(f'Player notice: {_ex}')
            is_auto = bool(
                getattr(next_track, "is_autoplay", False)
                or (next_track.requested_by and any(k in next_track.requested_by.lower() for k in ("autoplay", "brain dj")))
                or getattr(next_track, "source", "") == "autoplay"
            )
            if is_auto:
                self.consecutive_autoplay_count += 1
            else:
                self.vibe_anchor_artist = next_track.artist
                self.consecutive_autoplay_count = 0

            # Resolve streaming URL if needed
            stream_url = next_track.stream_url
            if not stream_url:
                try:
                    if not next_track.video_id:
                        # Always prefer 6-pass YouTube Music studio resolver unless explicit live/remix/DJ set query
                        q_combined = f"{next_track.artist} {next_track.title}".lower()
                        is_explicit_video_query = bool(re.search(
                            r"\b(live|concert|session|boiler room|tiny desk|remix|bootleg|mashup|dj set|full set|cover)\b",
                            q_combined
                        ))
                        if not is_explicit_video_query:
                            res = await asyncio.to_thread(
                                stream_service.resolve_track_stream,
                                artist=next_track.artist,
                                title=next_track.title,
                                album=next_track.album,
                                duration=next_track.duration_seconds
                            )
                            if res and res.get("id"):
                                next_track.video_id = res["id"]
                                if res.get("duration"):
                                    try:
                                        dur = int(res["duration"])
                                        if not next_track.duration_seconds or next_track.duration_seconds <= 0:
                                            next_track.duration_seconds = dur
                                        next_track.duration_str = AudioTrack._format_duration(dur)
                                    except Exception as _ex:
                                        log.debug(f'Player notice: {_ex}')

                        if not next_track.video_id:
                            yt_q = f"{next_track.artist} {next_track.title}".strip() if next_track.artist not in ("YouTube Search", "Direct Query", "YouTube") else next_track.title
                            yt_tracks = await asyncio.to_thread(stream_service.search_youtube_tracks, yt_q, limit=1)
                            if yt_tracks:
                                raw_vid = yt_tracks[0].get("video_id") or yt_tracks[0].get("id", "")
                                next_track.video_id = raw_vid.replace("yt_", "")
                                next_track.title = yt_tracks[0].get("title", next_track.title)
                                if yt_tracks[0].get("artist") and next_track.artist in ("YouTube Search", "Direct Query"):
                                    next_track.artist = yt_tracks[0].get("artist")
                                if yt_tracks[0].get("cover") and not next_track.cover_url:
                                    next_track.cover_url = yt_tracks[0].get("cover")
                                raw_dur = yt_tracks[0].get("duration", 0)
                                if isinstance(raw_dur, (int, float)) or (isinstance(raw_dur, str) and str(raw_dur).isdigit()):
                                    next_track.duration_seconds = int(raw_dur)
                                    next_track.duration_str = AudioTrack._format_duration(int(raw_dur))
                                else:
                                    next_track.duration_str = str(raw_dur)

                    if next_track.video_id:
                        s_url, hdrs = await asyncio.to_thread(stream_service.get_stream_info, next_track.video_id, self.audio_quality)
                        stream_url = s_url
                        next_track.stream_url = s_url
                        next_track.stream_headers = hdrs or {}
                        self._enrich_track_metadata(next_track)
                except Exception as e:
                    log.error(f"Error resolving stream for {next_track.artist} - {next_track.title}: {e}")

            if not stream_url:
                log.info(f"Stream unavailable for {next_track.artist} - {next_track.title}. Skipping to next.")
                # Blacklist unresolvable track for session to prevent infinite Autoplay retry loops
                t_key = f"{next_track.artist.lower().strip()} - {next_track.title.lower().strip()}"
                self.failed_tracks.add(t_key)
                self.history.append(next_track)
                self._consecutive_resolve_failures = getattr(self, "_consecutive_resolve_failures", 0) + 1
                if self._consecutive_resolve_failures >= 3:
                    log.warning(f"[{self.guild.name}] Multiple consecutive stream resolution failures. Resetting autoplay anchor.")
                    self.vibe_anchor_artist = None
                    self._consecutive_resolve_failures = 0

                if self.text_channel:
                    try:
                        await self.text_channel.send(f"⚠️ Unable to stream **{next_track.artist} - {next_track.title}**. Skipping to next track.", delete_after=6.0)
                    except Exception as _ex:
                        log.debug(f'Player notice: {_ex}')
                asyncio.create_task(self.play_next())
                return
            else:
                self._consecutive_resolve_failures = 0

            try:
                headers_dict = getattr(next_track, "stream_headers", None) or {}
                if headers_dict:
                    hdr_lines = "".join(f"{k}: {v}\r\n" for k, v in headers_dict.items() if k.lower() in ("user-agent", "accept", "accept-language"))
                else:
                    hdr_lines = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36\r\n"
                ffmpeg_before_opts = f'-headers "{hdr_lines}" -reconnect 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 -probesize 65536 -analyzeduration 100000 -nostdin'
                bitrate_flag = {"128k": " -b:a 128k", "192k": " -b:a 192k", "320k": " -b:a 320k"}.get(self.audio_quality, "")
                ffmpeg_opts = f"-vn -af afade=t=in:ss=0:d=0.03,volume=0.95{bitrate_flag}"
                
                audio_source = discord.FFmpegPCMAudio(
                    stream_url,
                    before_options=ffmpeg_before_opts,
                    options=ffmpeg_opts
                )
                transformed_source = AccurateAudioSource(audio_source, volume=self.volume)
                self._cleanup_active_source()
                self._active_source = transformed_source
                self._cancel_progress_task()
                self.play_start_time = time.time()
                self.total_paused_time = 0.0
                self.pause_start_time = 0.0

                def _after_play(error, expected_source=transformed_source):
                    if error:
                        log.error(f"Playback error in {self.guild.name}: {error}")
                    if self._active_source is not expected_source:
                        return
                    if getattr(self, "_suppress_after", False) or getattr(self, "_is_stopped", False):
                        self._suppress_after = False
                        return
                    self._cancel_progress_task()
                    self._cleanup_active_source()
                    self.is_playing = False
                    loop = getattr(self.bot, 'loop', None) or asyncio.get_event_loop()
                    if loop and loop.is_running():
                        fut = asyncio.run_coroutine_threadsafe(self.play_next(), loop)
                        def _done(f):
                            try:
                                f.result()
                            except Exception as err:
                                log.error(f"Error in play_next task: {err}")
                        fut.add_done_callback(_done)

                if self.voice_client.is_playing() or self.voice_client.is_paused():
                    try:
                        self._suppress_after = True
                        self.voice_client.stop()
                    except Exception as _ex:
                        log.debug(f'Player notice: {_ex}')
                    await asyncio.sleep(0.08)

                self._suppress_after = False
                self._last_play_start_time = time.time()
                self.voice_client.play(transformed_source, after=_after_play)
                self.is_playing = True
                self._start_progress_task()
                log.info(f"[{self.guild.name}] Now Playing: {next_track.artist} - {next_track.title}")
                asyncio.create_task(self._prewarm_next_track())

                # Enrich metadata and official studio cover art
                self._enrich_track_metadata(next_track)

                # Send Now Playing embed
                await self._send_now_playing_message(next_track)
                asyncio.create_task(self._update_channel_status_and_message(next_track))

            except Exception as e:
                log.error(f"Error starting playback in {self.guild.name}: {e}")
                self.is_playing = False
                await asyncio.sleep(1.0)
                asyncio.create_task(self.play_next())

    def _enrich_track_metadata(self, track: AudioTrack):
        """Enriches tracks with real studio titles, artists, high-res covers, and durations across Discord & Web."""
        if not track:
            return
        if track.video_id and (track.source == "youtube" or track.artist in ("YouTube", "YouTube Search", "Direct Query")):
            meta = stream_service.get_video_metadata(track.video_id)
            if meta:
                raw_title = meta.get("title") or track.title
                if " - " in raw_title:
                    parts = raw_title.split(" - ", 1)
                    track.artist = parts[0].strip()
                    clean_sub = re.sub(r"\s*[\(\[](?:Official\s+(?:Video|Audio|Music\s+Video|HD\s+Video)|HD|4K|Lyrics|Audio|Visualizer|Remastered)[\)\]]", "", parts[1], flags=re.IGNORECASE).strip()
                    track.title = clean_sub or parts[1].strip()
                else:
                    track.title = raw_title
                    if meta.get("artist") and track.artist in ("YouTube", "YouTube Search", "Direct Query"):
                        track.artist = meta.get("artist")

                if meta.get("thumbnail") and not track.cover_url:
                    track.cover_url = meta.get("thumbnail")
                if meta.get("duration") and (not track.duration_seconds or track.duration_seconds == 0):
                    try:
                        dur = int(meta["duration"])
                        track.duration_seconds = dur
                        track.duration_str = AudioTrack._format_duration(dur)
                    except Exception as _ex:
                        log.debug(f'Player notice: {_ex}')

        # Universal High-Resolution Studio Artwork Resolver (Offloaded to background async worker so event loop never stalls)
        if not track.cover_url or "coverartarchive.org" in track.cover_url or "ytimg.com" in track.cover_url or not track.duration_seconds or track.duration_seconds <= 0:
            clean_art = track.artist.strip() if track.artist not in ("YouTube", "YouTube Search", "Direct Query") else ""
            query = f"{clean_art} {track.title}".strip()
            if query:
                asyncio.create_task(self._fetch_studio_artwork_async(track, query, clean_art))

    async def _fetch_studio_artwork_async(self, track: AudioTrack, query: str, clean_art: str):
        try:
            found_trk = await asyncio.to_thread(deezer_api.search_tracks, query, limit=1)
            if found_trk:
                dz_t = found_trk[0]
                dz_art = (dz_t.get("artist") or "").lower()
                dz_title = (dz_t.get("title") or "").lower()
                t_art = clean_art.lower()
                t_title = track.title.lower()
                if (not t_art or t_art in dz_art or dz_art in t_art) and (t_title in dz_title or dz_title in t_title):
                    dz_cover = dz_t.get("cover_xl") or dz_t.get("cover_big") or dz_t.get("cover_medium") or dz_t.get("cover")
                    if dz_cover and (not track.cover_url or "coverartarchive.org" in track.cover_url or "ytimg.com" in track.cover_url):
                        track.cover_url = dz_cover
                    if not track.album and dz_t.get("album"):
                        track.album = dz_t.get("album")
                    if (not track.duration_seconds or track.duration_seconds <= 0) and dz_t.get("duration"):
                        track.duration_seconds = int(dz_t["duration"])
                        track.duration_str = AudioTrack._format_duration(track.duration_seconds)
                    await self.update_player_message()
        except Exception as _ex:
            log.debug(f'Player notice: {_ex}')

    def _build_now_playing_embed(self, track: AudioTrack) -> discord.Embed:
        embed = discord.Embed(
            title=f"🎶 {track.title}"[:250],
            description=(f"**Artist:** {track.artist[:200]}\n" + (f"**Album:** {track.album[:200]}\n" if track.album else "") + f"\n{self.get_progress_bar()}")[:4000],
            color=EMBED_COLOR
        )
        if track.cover_url:
            embed.set_thumbnail(url=track.cover_url)
        queue_len = len(self.queue)
        footer_text = f"Queue: {queue_len} track{'s' if queue_len != 1 else ''} | Vol: {int(self.volume * 100)}% | Quality: {self.audio_quality.upper()}"
        if self.loop_mode != "off":
            footer_text += f" | Loop: {self.loop_mode.capitalize()}"
        if track.requested_by:
            footer_text += f" | Requested by {track.requested_by}"
        embed.set_footer(text=footer_text)
        return embed

    async def _send_now_playing_message(self, track: AudioTrack):
        if not self.text_channel:
            return
        try:
            from .ui import PlayerControlsView
            embed = self._build_now_playing_embed(track)
            view = PlayerControlsView(self)

            # Reconnection / Post-Restart Recovery: Search recent history for previous bot player card
            if not self.current_message and self.text_channel:
                try:
                    async for m in self.text_channel.history(limit=25):
                        if m.author == self.bot.user and m.embeds and m.components:
                            self.current_message = m
                            break
                except Exception as ex:
                    log.debug(f"History search notice: {ex}")

            # Resilient Drift & In-Place Edit Handler
            drifted = False

            if not self.current_message:
                drifted = True
            else:
                try:
                    drift_count = 0
                    async for _ in self.text_channel.history(limit=15, after=self.current_message):
                        drift_count += 1
                        if drift_count >= 10:
                            drifted = True
                            break
                except (discord.NotFound, discord.HTTPException):
                    # Card was manually deleted or message ID is invalid
                    drifted = True

            if drifted:
                if self.current_message:
                    try:
                        await self.current_message.delete()
                    except (discord.NotFound, discord.HTTPException):
                        pass
                self.current_message = await self.text_channel.send(embed=embed, view=view)
            else:
                try:
                    await self.current_message.edit(embed=embed, view=view)
                except discord.NotFound:
                    # Card was removed between check and edit; spawn a replacement
                    self.current_message = await self.text_channel.send(embed=embed, view=view)
        except Exception as e:
            log.warning(f"Failed to send Now Playing embed: {e}")

    async def _update_channel_status_and_message(self, track: AudioTrack):
        """Updates Voice Channel Status topic without sending any chat messages."""
        vc = getattr(self.voice_client, "channel", None)
        if vc:
            try:
                status_text = f"🎶 {track.artist} - {track.title}"[:500]
                route = discord.http.Route("PUT", "/channels/{channel_id}/voice-status", channel_id=vc.id)
                await self.bot.http.request(route, json={"status": status_text})
            except Exception as ex:
                log.debug(f"Voice status notice: {ex}")

    async def _clear_voice_channel_status(self):
        """Clears the voice channel status when playback is stopped."""
        vc = getattr(self.voice_client, "channel", None)
        if vc:
            try:
                route = discord.http.Route("PUT", "/channels/{channel_id}/voice-status", channel_id=vc.id)
                await self.bot.http.request(route, json={"status": ""})
            except Exception as ex:
                log.debug(f"Voice status clear notice: {ex}")

    async def update_player_message(self):
        """Live-updates the existing Now Playing deck with fresh title, artwork, queue count, volume, loop, and quality."""
        if not self.current_message or not self.current_track:
            return
        if getattr(self, "_updating_message", False):
            return
        self._updating_message = True
        try:
            embed = self._build_now_playing_embed(self.current_track)
            self.current_message = await self.current_message.edit(embed=embed)
        except (discord.NotFound, discord.HTTPException) as e:
            if getattr(e, "status", None) == 429:
                log.debug(f"Discord 429 edit backoff: {e}")
            elif getattr(e, "status", None) in (400, 404) or isinstance(e, discord.NotFound):
                self.current_message = None
        except Exception as e:
            log.debug(f"Live-update player card notice: {e}")
        finally:
            self._updating_message = False

    def _is_vibe_worthy(self, track_dict: dict, artist_fans: int = 0) -> bool:
        """Shield against vibe killers: filters junk, skits, and low-energy amateur spam."""
        from core import vibe_engine
        return vibe_engine.is_vibe_worthy(track_dict, artist_fans)

    async def _fetch_autoplay_vibe_track(self, seed_track: Optional[AudioTrack] = None) -> Optional[AudioTrack]:
        """Multi-platform recommendation engine across YouTube Music, Deezer, and Apple Music."""
        from core import vibe_engine
        return await vibe_engine.fetch_next_vibe_track(self, seed_track=seed_track)

    def pause(self) -> bool:
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            if self.pause_start_time == 0.0:
                self.pause_start_time = time.time()
            asyncio.create_task(self.update_player_message())
            return True
        return False

    def resume(self) -> bool:
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            if self.pause_start_time > 0.0:
                self.total_paused_time += time.time() - self.pause_start_time
                self.pause_start_time = 0.0
            asyncio.create_task(self.update_player_message())
            return True
        return False

    def skip(self) -> bool:
        now = time.time()
        if now - getattr(self, "_last_skip_time", 0.0) < 0.6:
            return False
        self._last_skip_time = now
        self._is_stopped = False
        self._cancel_progress_task()
        self._was_manually_skipped = True
        self._cleanup_active_source()
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self._suppress_after = True
            try:
                self.voice_client.stop()
            except Exception as _ex:
                log.debug(f'Player notice: {_ex}')
            asyncio.create_task(self.play_next())
            return True
        elif not self.is_playing:
            asyncio.create_task(self.play_next())
            return True
        return False

    def stop(self):
        self._is_stopped = True
        asyncio.create_task(self._clear_voice_channel_status())
        self._suppress_after = True
        self.is_playing = False
        self._cancel_progress_task()
        self._cleanup_active_source()
        self.play_start_time = 0.0
        self.pause_start_time = 0.0
        self.total_paused_time = 0.0
        self.queue.clear()
        self.current_track = None
        self._prewarmed_autoplay_track = None
        self._deck3_autoplay_track = None
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            try:
                self.voice_client.stop()
            except Exception as _ex:
                log.debug(f'Player notice: {_ex}')
        self._start_idle_timer()

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(1.0, vol))
        if self._active_source and hasattr(self._active_source, "volume"):
            self._active_source.volume = self.volume
        if self.voice_client and self.voice_client.source and hasattr(self.voice_client.source, "volume"):
            self.voice_client.source.volume = self.volume
        asyncio.create_task(self.update_player_message())

    def set_quality(self, quality: str):
        self.audio_quality = str(quality).lower()
        self._prewarmed_autoplay_track = None
        self._deck3_autoplay_track = None
        asyncio.create_task(self.update_player_message())

    def shuffle(self):
        if len(self.queue) > 1:
            q_list = list(self.queue)
            random.shuffle(q_list)
            self.queue = collections.deque(q_list)

    def _start_idle_timer(self):
        self._cancel_idle_timer()
        self._prewarmed_autoplay_track = None
        self._deck3_autoplay_track = None
        async def _idle_disconnect():
            await asyncio.sleep(IDLE_DISCONNECT_SECONDS)
            if not self.is_playing and len(self.queue) == 0:
                log.info(f"[{self.guild.name}] Idle timeout reached. Disconnecting.")
                await self.disconnect()
                if self.text_channel:
                    try:
                        await self.text_channel.send("👋 Left the voice channel due to inactivity.")
                    except Exception as _ex:
                        log.debug(f'Player notice: {_ex}')
        self._idle_task = asyncio.create_task(_idle_disconnect())

    def _cancel_idle_timer(self):
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

    def handle_feedback(self, artist: str, title: str, vote: str) -> dict:
        from core.vibe_engine import record_taste_feedback
        profile = record_taste_feedback(self.guild.id, artist, title, vote)
        if vote == "down":
            art_lower = str(artist or "").strip().lower()
            if self._prewarmed_autoplay_track and str(self._prewarmed_autoplay_track.artist).strip().lower() == art_lower:
                self._prewarmed_autoplay_track = None
                self._prewarm_task = None
                self._schedule_prewarm_next(delay=0.1)
            if self._deck3_autoplay_track and str(self._deck3_autoplay_track.artist).strip().lower() == art_lower:
                self._deck3_autoplay_track = None
                self._schedule_deck3_cue(delay=0.5)
        return profile

    async def disconnect(self):
        self.stop()
        self._cancel_idle_timer()
        self._prewarmed_autoplay_track = None
        self._deck3_autoplay_track = None
        if self.voice_client:
            try:
                await self.voice_client.disconnect(force=True)
            except Exception as _ex:
                log.debug(f"Voice disconnect notice: {_ex}")
            self.voice_client = None
        if hasattr(self.bot, "player_manager") and not self.queue:
            self.bot.player_manager.players.pop(self.guild.id, None)

class PlayerManager:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.players: Dict[int, GuildPlayer] = {}

    def get_player(self, guild: discord.Guild) -> GuildPlayer:
        if guild.id not in self.players:
            self.players[guild.id] = GuildPlayer(self.bot, guild)
        return self.players[guild.id]

    async def remove_player(self, guild_id: int):
        if guild_id in self.players:
            player = self.players.pop(guild_id)
            await player.disconnect()
