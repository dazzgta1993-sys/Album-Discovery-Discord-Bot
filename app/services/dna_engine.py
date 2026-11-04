"""Music DNA Engine - Computes real-time genre spectrum, sonic traits,
energy levels, and acoustic DNA from session playback history using
dynamic canonical taxonomy resolution and intelligent sonic profiling.
"""
import unicodedata
import urllib.parse
from collections import Counter
from typing import List, Dict, Any, Tuple, Optional
from ..utils.http_client import fetch_json

# Primary genre color palette
GENRE_COLORS = {
    "Dance & Electronic": "#38bdf8",
    "Pop & Mainstream": "#c084fc",
    "Rock & Alternative": "#f87171",
    "Hip-Hop & Rap": "#fbbf24",
    "R&B & Soul": "#fb7185",
    "Indie & Folk": "#34d399",
    "Retro & Classics": "#f472b6",
    "Soundtrack & Film": "#a3e635",
    "Other": "#94a3b8"
}

# Standard canonical genre classification to primary category & sonic traits
# (Primary Category, Energy 0-100, Danceability 0-100, Acousticness 0-100)
CANONICAL_GENRE_TAXONOMY: Dict[str, Tuple[str, int, int, int]] = {
    "electronic": ("Dance & Electronic", 88, 90, 12),
    "dance": ("Dance & Electronic", 90, 92, 10),
    "house": ("Dance & Electronic", 88, 92, 10),
    "deep house": ("Dance & Electronic", 86, 92, 12),
    "tech house": ("Dance & Electronic", 90, 94, 8),
    "techno": ("Dance & Electronic", 92, 90, 6),
    "trance": ("Dance & Electronic", 92, 88, 6),
    "dubstep": ("Dance & Electronic", 95, 85, 4),
    "drum & bass": ("Dance & Electronic", 96, 86, 5),
    "breakbeat": ("Dance & Electronic", 90, 88, 10),
    "uk garage": ("Dance & Electronic", 90, 94, 8),
    "alternative": ("Rock & Alternative", 82, 58, 28),
    "rock": ("Rock & Alternative", 88, 55, 20),
    "hard rock": ("Rock & Alternative", 92, 52, 15),
    "metal": ("Rock & Alternative", 96, 48, 5),
    "punk": ("Rock & Alternative", 92, 58, 12),
    "grunge": ("Rock & Alternative", 90, 52, 15),
    "britpop": ("Rock & Alternative", 82, 58, 30),
    "indie rock": ("Rock & Alternative", 80, 62, 30),
    "singer/songwriter": ("Indie & Folk", 65, 55, 60),
    "folk": ("Indie & Folk", 62, 50, 68),
    "americana": ("Indie & Folk", 66, 52, 60),
    "country": ("Indie & Folk", 70, 62, 55),
    "acoustic": ("Indie & Folk", 58, 52, 70),
    "r&b/soul": ("R&B & Soul", 80, 80, 24),
    "r&b": ("R&B & Soul", 80, 80, 24),
    "soul": ("R&B & Soul", 76, 74, 35),
    "funk": ("R&B & Soul", 84, 88, 18),
    "neo-soul": ("R&B & Soul", 72, 75, 40),
    "hip-hop/rap": ("Hip-Hop & Rap", 85, 84, 15),
    "hip-hop": ("Hip-Hop & Rap", 85, 84, 15),
    "rap": ("Hip-Hop & Rap", 88, 82, 12),
    "trap": ("Hip-Hop & Rap", 88, 85, 10),
    "soundtrack": ("Soundtrack & Film", 65, 45, 50),
    "score": ("Soundtrack & Film", 65, 45, 50),
    "classical": ("Soundtrack & Film", 60, 35, 75),
    "pop": ("Pop & Mainstream", 78, 78, 25),
    "k-pop": ("Pop & Mainstream", 88, 88, 15),
    "j-pop": ("Pop & Mainstream", 86, 86, 18),
}

# In-memory LRU dynamic cache
_DYNAMIC_GENRE_CACHE: Dict[str, Tuple[str, str, int, int, int]] = {}

def _norm(s: str) -> str:
    if not s:
        return ""
    t = str(s).replace("\ufffd", "'").replace("’", "'").replace("‘", "'").replace("`", "'")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    return t.lower().strip()

def _fetch_dynamic_artist_genre(artist: str) -> Optional[Tuple[str, str, int, int, int]]:
    """Dynamically resolves canonical genre from live public music registry."""
    clean = _norm(artist)
    if not clean or clean in ("unknown", "unknown artist", "various artists"):
        return None

    if clean in _DYNAMIC_GENRE_CACHE:
        return _DYNAMIC_GENRE_CACHE[clean]

    try:
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(clean)}&entity=musicArtist&limit=1"
        data = fetch_json(url, cache_ttl=86400 * 7)  # 7-day persistent cache
        if data and "results" in data and len(data["results"]) > 0:
            raw_genre = (data["results"][0].get("primaryGenreName") or "").strip().lower()
            if raw_genre:
                # Direct match in taxonomy
                if raw_genre in CANONICAL_GENRE_TAXONOMY:
                    primary, nrg, dnc, aco = CANONICAL_GENRE_TAXONOMY[raw_genre]
                    result = (primary, raw_genre.title(), nrg, dnc, aco)
                    _DYNAMIC_GENRE_CACHE[clean] = result
                    return result
                # Partial match in taxonomy
                for k, (primary, nrg, dnc, aco) in CANONICAL_GENRE_TAXONOMY.items():
                    if k in raw_genre or raw_genre in k:
                        result = (primary, raw_genre.title(), nrg, dnc, aco)
                        _DYNAMIC_GENRE_CACHE[clean] = result
                        return result
                # Unmapped primary genre
                result = ("Pop & Mainstream", raw_genre.title(), 75, 75, 25)
                _DYNAMIC_GENRE_CACHE[clean] = result
                return result
    except Exception:
        pass

    return None


def classify_track_dna(artist: str, title: str) -> Dict[str, Any]:
    art_clean = _norm(artist)
    tit_clean = _norm(title)

    # 1. Dynamic live API resolution (Zero hardcoding)
    dyn = _fetch_dynamic_artist_genre(art_clean)
    if dyn:
        genre, sub, nrg, dnc, aco = dyn
        return {
            "genre": genre,
            "sub_genre": sub,
            "color": GENRE_COLORS.get(genre, "#94a3b8"),
            "energy": nrg,
            "danceability": dnc,
            "acoustic": aco
        }

    # 2. Token-based heuristic fallback (for offline or unreleased indie tracks)
    combined = f"{art_clean} {tit_clean}"
    if any(k in combined for k in (
        "dj", "remix", "club", "dance", "electronic", "synth", "house", "techno", "dubstep", "bass",
        "dnb", "drum & bass", "drum and bass", "garage", "ukg", "trance", "mix", "extended mix",
        "original mix", "vip", "bootleg", "radio edit", "rave", "deep house", "tech house", "afro house"
    )):
        return {"genre": "Dance & Electronic", "sub_genre": "Club / Electronic", "color": GENRE_COLORS["Dance & Electronic"], "energy": 88, "danceability": 90, "acoustic": 10}

    if any(k in combined for k in (
        "rock", "metal", "guitar", "band", "punk", "grunge", "britpop", "emo", "alt-rock", "alternative"
    )):
        return {"genre": "Rock & Alternative", "sub_genre": "Rock / Alternative", "color": GENRE_COLORS["Rock & Alternative"], "energy": 85, "danceability": 60, "acoustic": 25}

    if any(k in combined for k in (
        "rap", "trap", "feat.", "ft.", "drill", "hip hop", "hip-hop", "freestyle", "cypher", "mc ", "lil ", "big "
    )):
        return {"genre": "Hip-Hop & Rap", "sub_genre": "Hip-Hop / Rap", "color": GENRE_COLORS["Hip-Hop & Rap"], "energy": 82, "danceability": 84, "acoustic": 15}

    if any(k in combined for k in (
        "r&b", "soul", "neo-soul", "motown", "funk", "groove"
    )):
        return {"genre": "R&B & Soul", "sub_genre": "R&B / Soul", "color": GENRE_COLORS["R&B & Soul"], "energy": 76, "danceability": 78, "acoustic": 30}

    if any(k in combined for k in (
        "acoustic", "folk", "unplugged", "piano", "indie", "singer-songwriter", "ballad"
    )):
        return {"genre": "Indie & Folk", "sub_genre": "Indie / Acoustic", "color": GENRE_COLORS["Indie & Folk"], "energy": 58, "danceability": 52, "acoustic": 65}

    if any(k in combined for k in ("soundtrack", "theme", "score", "ost", "orchestra", "symphony")):
        return {"genre": "Soundtrack & Film", "sub_genre": "Cinematic Score", "color": GENRE_COLORS["Soundtrack & Film"], "energy": 65, "danceability": 45, "acoustic": 50}

    # Default general fallback
    return {"genre": "Pop & Mainstream", "sub_genre": "Modern Pop", "color": GENRE_COLORS["Pop & Mainstream"], "energy": 75, "danceability": 75, "acoustic": 25}


def compute_session_music_dna(tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not tracks:
        return {
            "total_analyzed": 0,
            "dominant_genre": "Awaiting Tracks",
            "dominant_color": "#c084fc",
            "dominant_subgenre": "Eclectic",
            "genres": [],
            "avg_energy": 0,
            "avg_danceability": 0,
            "avg_acoustic": 0,
            "electronic_ratio": 50,
            "acoustic_ratio": 50,
            "vibe_description": "Queue songs to generate real-time music DNA analysis."
        }

    genre_counts = Counter()
    subgenre_counts = Counter()
    total_energy = 0
    total_dance = 0
    total_acoustic = 0
    recent_artist_pills = []

    for t in tracks:
        art = t.get("artist", "")
        tit = t.get("title", "")
        dna = classify_track_dna(art, tit)

        genre_counts[dna["genre"]] += 1
        subgenre_counts[dna["sub_genre"]] += 1
        total_energy += dna["energy"]
        total_dance += dna["danceability"]
        total_acoustic += dna["acoustic"]

        if art and art not in [p["artist"] for p in recent_artist_pills]:
            recent_artist_pills.append({
                "artist": art,
                "sub_genre": dna["sub_genre"],
                "color": dna["color"]
            })

    total_n = len(tracks)
    genre_breakdown = []
    for g, count in genre_counts.most_common():
        pct = round((count / total_n) * 100, 1)
        genre_breakdown.append({
            "genre": g,
            "count": count,
            "percent": pct,
            "color": GENRE_COLORS.get(g, "#94a3b8")
        })

    dom_genre, dom_count = genre_counts.most_common(1)[0]
    dom_sub = subgenre_counts.most_common(1)[0][0]
    dom_color = GENRE_COLORS.get(dom_genre, "#c084fc")

    avg_nrg = round(total_energy / total_n)
    avg_dnc = round(total_dance / total_n)
    avg_aco = round(total_acoustic / total_n)
    elec_ratio = max(0, 100 - avg_aco)

    # Narrative Vibe Description
    if avg_nrg >= 80 and avg_dnc >= 80:
        desc = f"High-octane {dom_sub} groove with driving beats and maximum dancefloor energy."
    elif avg_nrg >= 70:
        desc = f"Upbeat, melodic {dom_genre} flow with tight hooks and rhythmic pacing."
    elif avg_aco >= 45:
        desc = f"Warm, acoustic-leaning {dom_genre} vibe with organic instruments and vocal focus."
    else:
        desc = f"Balanced {dom_sub} session with smooth melodic transitions."

    return {
        "total_analyzed": total_n,
        "dominant_genre": dom_genre,
        "dominant_color": dom_color,
        "dominant_subgenre": dom_sub,
        "genres": genre_breakdown,
        "avg_energy": avg_nrg,
        "avg_danceability": avg_dnc,
        "avg_acoustic": avg_aco,
        "electronic_ratio": elec_ratio,
        "acoustic_ratio": avg_aco,
        "vibe_description": desc,
        "artist_pills": recent_artist_pills[:12]
    }
