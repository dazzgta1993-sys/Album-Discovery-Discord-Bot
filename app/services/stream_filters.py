"""Stream Resolution Filters, Regex Cleaners, and Attribution Guards.
Isolates candidate classification patterns and metadata normalization
to keep the primary stream proxy engine modular and well below file ceilings.
"""
import re

_JUNK_TITLE_REGEX = re.compile(
    r"\b(reaction|reacts|reacting|how to play|guitar tab|bass tab|drum tab|piano tutorial|guitar tutorial|synthesia|"
    r"karaoke version|sing along|backing track|in the style of|tribute to|made famous by|10 hour loop|1 hour loop|"
    r"album review|song review|full podcast|podcast episode|behind the scenes of|interview with|tier list|documentary|"
    r"slowed\s*\+\s*reverb|8d audio|bass boosted|nightcore|greatest hits non stop|non stop mix|megamix|continuous mix)\b",
    re.IGNORECASE,
)

_JUNK_CHANNEL_REGEX = re.compile(
    r"\b(reactions?|tutorials?|karaoke|guitar lessons?|drum lessons?|podcast|nightcore|bass boost(?:ed)?|sped up|speed up|slowed)\b",
    re.IGNORECASE,
)

_DOT_OBFUSCATED_REGEX = re.compile(r"\b(?:[A-Za-z]\.){3,}[A-Za-z]?\b")

# Specific modifier keywords that should be rejected when appended as modifiers or brackets
_BRACKETED_MODIFIERS = (
    "cover", "acoustic cover", "piano cover", "guitar cover", "fingerstyle",
    "karaoke", "instrumental", "backing track", "minus one", "sing along",
    "sped up", "speed up", "speedup", "slowed", "slowed down", "reverb",
    "nightcore", "daycore", "chopped and screwed", "chipmunk",
    "bass boosted", "bass boost", "8d audio", "16d audio", "3d audio",
    "1 hour loop", "10 hour loop", "1 hour version", "10 hours",
    "remix", "mashup", "tiktok version", "parody", "bootleg", "fan made", "fan video", "remake"
)

# Attribution phrases that explicitly signal non-original performances
_ATTRIBUTION_PATTERNS = (
    "originally performed by", "originally by", "in the style of", "made famous by",
    "tribute to", "as made famous by", "salute to", "homage to", "backing track"
)

BAD_CHANNEL_PATTERNS = (
    "karaoke", "tribute", "cover", "instrumental", "backing track", "minus one",
    "speed up", "sped up", "slowed", "nightcore", "bass boost", "soundalike", "remakes"
)


def _is_junk_video(video_obj: dict) -> bool:
    """Evaluate candidate video title, channel, and duration against junk patterns."""
    t = video_obj.get("title") or ""
    ch = video_obj.get("channel") or ""
    dur = str(video_obj.get("duration") or "").strip()

    if _JUNK_TITLE_REGEX.search(t):
        return True
    if _JUNK_CHANNEL_REGEX.search(ch):
        return True
    if _DOT_OBFUSCATED_REGEX.search(t):
        return True

    if dur and dur.lower() in ("live", "live now", "upcoming", "premiere", "premieres"):
        return True
    if video_obj.get("is_live"):
        return True

    if dur:
        parts = dur.split(":")
        if len(parts) >= 3:
            return True  # >= 1 hour is not a single studio track
        elif len(parts) == 2:
            mins = int(parts[0]) if parts[0].isdigit() else 0
            secs = int(parts[1]) if parts[1].isdigit() else 0
            if mins == 0 and secs < 40:
                return True
            if mins > 18:
                return True
    return False


def _parse_duration_seconds(dur_str: str) -> int:
    """Parse string duration (HH:MM:SS or MM:SS) into integer total seconds."""
    if not dur_str:
        return 0
    parts = str(dur_str).strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0


def _clean_target_title(title: str) -> str:
    """Strip bracketed release tags and trailing version/remaster metadata
    while preserving explicitly requested remix/live titles.
    """
    t = (title or "").strip()
    prev = None
    while prev != t:
        prev = t
        # 1. Bracketed/parenthetical noise
        t = re.sub(
            r"[\(\[][^\)\]]*(?:remaster|deluxe|explicit|visualizer|album version|bonus track|anniversary|version|edition)[^\)\]]*[\)\]]",
            "", t, flags=re.IGNORECASE
        ).strip()
        # 2. Suffix noise after hyphens, dashes, or slashes
        t = re.sub(
            r"\s*[-–—/]\s*(?:\d{4}\s+)?(?:original\s+)?(?:digital\s+)?(?:remaster(?:ed)?|version|mono|stereo|radio edit|original mix|single version|album version)(?:\s+version|\s+edition|\s+\d{4})?.*$",
            "", t, flags=re.IGNORECASE
        ).strip()
    return t
