"""AI Radio DJ Host Service for Album Discovery Discord Bot.
Generates authentic, punchy (3-5 second) broadcast radio DJ voice intros and segues
using Microsoft Edge Neural studio voices (edge-tts) with automated gTTS fallback,
resampled to Discord's native 48kHz Stereo format.
"""

import asyncio
import os
import random
import subprocess
import logging
from typing import Optional

log = logging.getLogger("dj_host")

# Studio Neural Radio Personalities
DJ_VOICES = {
    "classic_fm": "en-US-ChristopherNeural",   # Warm, deep, energetic American FM host
    "hype_club": "en-US-GuyNeural",            # High-energy festival / club hype host
    "late_night": "en-US-EricNeural",          # Smooth, laid-back late night broadcast
    "bbc_radio": "en-GB-RyanNeural",           # Crisp UK BBC Radio 1 style host
}

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "dj_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Curated, punchy 3-5 second radio segues
SHORT_SEGUES = [
    "Up next on Album Discovery, keeping the vibe rolling with {artist}!",
    "You're locked into the mix. Coming up next: {artist} with '{title}'!",
    "Taking the energy up a notch right now, here is {artist}!",
    "Keeping that rhythm moving for you. Next up in the chute, {artist}!",
    "Smooth transitions all day on Discovery. Here comes {artist}!",
    "You're tuned into the groove. Up next, it's {artist}!",
    "Turning up the sound right here. Coming up next: {artist} with '{title}'!",
    "That was great! Now staying locked in the mix, here is {artist}!",
]

def build_dj_script(next_artist: str, next_title: str, prev_artist: Optional[str] = None) -> str:
    """Builds a concise, broadcast-ready 1-sentence radio DJ intro (3-5s)."""
    clean_title = next_title.split("(")[0].split("[")[0].split("feat.")[0].split("ft.")[0].strip()
    clean_artist = next_artist.split(",")[0].split("&")[0].split("feat.")[0].strip()
    
    if prev_artist and prev_artist.lower() != clean_artist.lower() and random.random() < 0.35:
        clean_prev = prev_artist.split(",")[0].split("&")[0].strip()
        templates = [
            f"That was {clean_prev}! Coming up next on Discovery, here's {clean_artist}!",
            f"From {clean_prev} straight into {clean_artist} with '{clean_title}', let's go!",
            f"Keeping the momentum going from {clean_prev}. Up next: {clean_artist}!",
        ]
        return random.choice(templates)
        
    template = random.choice(SHORT_SEGUES)
    return template.format(artist=clean_artist, title=clean_title)

async def generate_dj_drop(
    guild_id: str,
    next_artist: str,
    next_title: str,
    prev_artist: Optional[str] = None,
    personality: str = "classic_fm"
) -> Optional[str]:
    """Generates a pristine 48kHz Stereo MP3 DJ drop with edge-tts and gTTS fallback."""
    script = build_dj_script(next_artist, next_title, prev_artist)
    voice = DJ_VOICES.get(personality, DJ_VOICES["classic_fm"])
    
    raw_path = os.path.join(CACHE_DIR, f"{guild_id}_raw.mp3")
    dest_path = os.path.join(CACHE_DIR, f"{guild_id}_drop.mp3")
    
    generated = False
    
    # 1. Primary Engine: Microsoft Edge Neural Studio Voices
    try:
        import edge_tts
        communicate = edge_tts.Communicate(script, voice, rate="+6%")
        await communicate.save(raw_path)
        if os.path.exists(raw_path) and os.path.getsize(raw_path) > 1000:
            generated = True
    except Exception as e:
        log.debug(f"[DJ Host] edge-tts notice: {e}, falling back to gTTS...")
    
    # 2. Rock-solid Fallback Engine: gTTS
    if not generated:
        try:
            from gtts import gTTS
            tts = gTTS(text=script, lang="en", tld="com")
            await asyncio.to_thread(tts.save, raw_path)
            if os.path.exists(raw_path) and os.path.getsize(raw_path) > 1000:
                generated = True
        except Exception as e:
            log.warning(f"[DJ Host] gTTS fallback failed: {e}")
            
    # 3. Resample into Discord's native 48,000 Hz Stereo format via FFmpeg
    if generated and os.path.exists(raw_path):
        try:
            cmd = [
                "ffmpeg", "-y", "-i", raw_path,
                "-af", "loudnorm=I=-12:TP=-0.5:LRA=6,volume=2.2",
                "-ar", "48000", "-ac", "2", "-b:a", "192k",
                dest_path
            ]
            await asyncio.to_thread(subprocess.run, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 1000:
                log.info(f"[DJ Host] Generated 48kHz Stereo drop: \"{script}\"")
                return dest_path
        except Exception as e:
            log.warning(f"[DJ Host] FFmpeg resampling failed: {e}")
            
    return None
