"""Universal Algorithmic String Canonicalization, Leetspeak Resolver, and Noise Filtering.
Handles stylizations (e.g. P!nk <-> Pink, Ke$ha <-> Kesha, AC/DC <-> ACDC, Run-D.M.C. <-> Run DMC,
Mötley Crüe <-> Motley Crue, Beyoncé <-> Beyonce) with zero hardcoded artist dictionaries.
"""
import re
import unicodedata
from typing import Set


def strip_accents(text: str) -> str:
    """Normalize unicode accents (e.g. Mötley Crüe -> Motley Crue, Beyoncé -> Beyonce)."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def get_canonical_variants(text: str) -> Set[str]:
    """Generate canonical algorithmic variants for a name to match all stylizations."""
    if not text:
        return set()

    clean = text.strip().lower()
    variants = {clean}

    # 1. Accent stripped
    no_accents = strip_accents(clean)
    variants.add(no_accents)

    # 2. Pure alphanumeric (strips slashes, dots, hyphens, spaces, exclamation, etc.)
    # AC/DC -> acdc, Run-D.M.C. -> rundmc, Jay-Z -> jayz, Guns N' Roses -> gunsnroses
    v_alphanum = re.sub(r"[^a-z0-9]", "", no_accents)
    if v_alphanum:
        variants.add(v_alphanum)

    # 3. Leetspeak & symbol transliteration:
    # P!nk -> pink, Ke$ha -> kesha, deadmau5 -> deadmaus, Boyz II Men -> boyz 2 men
    v_sym = (
        no_accents
        .replace("!", "i")
        .replace("$", "s")
        .replace("@", "a")
        .replace("&", "and")
        .replace("+", "and")
        .replace("5", "s")
        .replace("0", "o")
        .replace("1", "i")
        .replace("3", "e")
        .replace("4", "a")
    )
    v_sym_alpha = re.sub(r"[^a-z0-9]", "", v_sym)
    if v_sym_alpha:
        variants.add(v_sym_alpha)

    # 4. Symbol stripped without replacement (e.g. Panic! At The Disco -> panicatthedisco)
    v_stripped = (
        no_accents
        .replace("!", "")
        .replace("$", "")
        .replace("@", "")
        .replace("'", "")
        .replace('"', "")
    )
    v_stripped_alpha = re.sub(r"[^a-z0-9]", "", v_stripped)
    if v_stripped_alpha:
        variants.add(v_stripped_alpha)

    return variants


def is_canonical_match(query: str, target: str) -> bool:
    """Return True if query and target share any canonical representation."""
    q_vars = get_canonical_variants(query)
    t_vars = get_canonical_variants(target)
    return bool(q_vars & t_vars)


def canonicalize_token(text: str) -> str:
    """Single canonical token string for quick indexing."""
    if not text:
        return ""
    t = strip_accents(text.lower())
    t = t.replace("!", "i").replace("$", "s").replace("@", "a").replace("+", "and").replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", t)


def normalize_title(title: str) -> str:
    """Normalize album or track title for comparisons."""
    if not title:
        return ""
    t = strip_accents(title.lower())
    t = re.sub(r"\([^)]*\)", " ", t)
    t = re.sub(r"\[[^\]]*\]", " ", t)
    t = re.sub(r"[^\w\s]", " ", t)
    return " ".join(t.split())


# -------------------------------------------------------------
# JUNK & NOISE FILTERS (Karaoke, Tributes, Soundalikes, AI, Sped-up, Slowed)
# -------------------------------------------------------------

_JUNK_PATTERNS = [
    # Tributes & Soundalikes
    r"\btribute\s+band\b",
    r"\btribute\s+to\b",
    r"\bfemale\s+fronted\b",
    r"\bas\s+made\s+famous\s+by\b",
    r"\bin\s+the\s+style\s+of\b",
    r"\boriginally\s+performed\s+by\b",
    r"\bcover\s+band\b",
    r"\bcover\s+version\b",
    r"\bsalute\s+to\b",
    r"\bhomage\s+to\b",
    r"\bsoundalike\b",
    
    # Karaoke & Backing
    r"\bkaraoke\b",
    r"\bbacking\s+track\b",
    r"\binstrumental\s+version\b",
    r"\bsing\s*-?\s*along\b",
    r"\bminus\s+one\b",
    
    # Relaxing / Study / Lullaby
    r"\blullaby\s+version\b",
    r"\brelaxing\s+piano\b",
    r"\bstudy\s+music\b",
    r"\bsleep\s+music\b",
    r"\bsleep\s+sounds\b",
    r"\bwhite\s+noise\b",
    r"\bbrown\s+noise\b",
    r"\brain\s+sounds\b",
    r"\bambient\s+tribute\b",
    
    # AI / Speed / Sped-up / Slowed / Pitch / Boosted
    r"\bslowed\s*\+\s*reverb\b",
    r"\bslowed\s*(?:down)?\b",
    r"\bsped\s+up\b",
    r"\bspeed\s*up\b",
    r"\bnightcore\b",
    r"\bdaycore\b",
    r"\bchopped\s+and\s+screwed\b",
    r"\bchipmunk\s+(?:version|audio)?\b",
    r"\bbass\s+boost(?:ed)?\b",
    r"\b8d\s+audio\b",
    r"\b16d\s+audio\b",
    r"\b8-?bit\s+version\b",
    r"\bringtone\b",
    r"\balert\s+tone\b",
    r"\blo-?fi\s+remix\b",
    r"\blo-?fi\s+beats\b",

    # Unofficial leak/spam placeholder uploads
    r"\bhabibti\b",
    r"\bmaid of honour\b",
    r"\biceman\b",
    
    # Meme / Amateur / Viral Remix / Hoodtrap / Type Beat
    r"\bhood\s*trap\b",
    r"\bhoodtrap\b",
    r"\btype\s+beat\b",
    r"\btiktok\s+remix\b",
    r"\bamateur\s+remix\b",
    r"\bmashup\b",
]


def is_junk_album(title: str, artist: str = "") -> bool:
    """Detect if an album or track is noise/soundalike/karaoke/tribute/sped-up/slowed spam."""
    combined = f"{title} {artist}".lower()
    for pat in _JUNK_PATTERNS:
        if re.search(pat, combined, re.IGNORECASE):
            return True
    return False


def is_junk_artist(artist_name: str) -> bool:
    """Detect if an artist is a tribute act, karaoke singer, or cover band."""
    a = (artist_name or "").lower()
    for pat in (
        r"\btribute\b",
        r"\bkaraoke\b",
        r"\bcover\s*band\b",
        r"\bsoundalike\b",
        r"\blullaby\b",
        r"\bbacking\s*track\b",
        r"\bhoodtrap\b",
        r"\btype\s*beat\b",
    ):
        if re.search(pat, a, re.IGNORECASE):
            return True
    return False


def rank_artists(query: str, artists: list[dict]) -> list[dict]:
    """Smart algorithmic ranking:
    1. Filter out junk tribute/karaoke acts.
    2. Rank exact canonical matches (e.g. 'pink' <-> 'P!nk', 'acdc' <-> 'AC/DC') at Tier 1.
    3. Rank prefix/substring matches at Tier 2.
    4. Sort by global fan count within each tier so global icons always beat local cover acts.
    """
    if not artists:
        return []

    q_clean = query.strip()
    q_vars = get_canonical_variants(q_clean)

    def _score(a: dict) -> tuple:
        name = a.get("name") or ""
        fans = a.get("fans") or 0
        is_junk = is_junk_artist(name)

        # Tier 0 = Clean, Tier 1 = Junk
        junk_penalty = 1 if is_junk else 0

        # Match tier
        name_vars = get_canonical_variants(name)
        if q_vars & name_vars:
            match_tier = 1  # Exact canonical match (e.g. pink == P!nk, acdc == AC/DC)
        elif any(v in name.lower() for v in q_vars if len(v) >= 3):
            match_tier = 2  # Substring match
        elif any(name.lower() in v for v in q_vars):
            match_tier = 2  # Reverse substring
        else:
            match_tier = 3  # Loose match

        # Sort order: (no junk first, closest match tier first, highest fans first)
        return (junk_penalty, match_tier, -fans)

    sorted_artists = sorted(artists, key=_score)
    return sorted_artists

def clean_title_clutter(title: str) -> str:
    """Strips YouTube video suffixes and audio clutter (e.g. [Official Video], (4K Remaster), [Audio]).
    Preserves authentic artistic credits like (feat. Artist).
    """
    if not title:
        return ""
    t = title
    clutter_pattern = re.compile(
        r"\s*[\(\[](?:Official\s+(?:Music\s+Video|Video|Audio|Visualizer|HD\s+Video|4K\s+Video|Lyric\s+Video)|"
        r"Official|Visualizer|Audio|HD|4K|60FPS|Lyrics?|Lyric\s+Video|(?:4K\s+)?Remaster(?:ed)?(?:\s*\d{4})?|"
        r"Album\s+Version|Original\s+Version|HQ)[\)\]]",
        re.IGNORECASE
    )
    t = clutter_pattern.sub("", t).strip()
    t = re.sub(r"\s*-\s*(?:Official\s+(?:Video|Audio|Music\s+Video)|Audio|Lyrics?)\s*$", "", t, flags=re.IGNORECASE).strip()
    return t or title

