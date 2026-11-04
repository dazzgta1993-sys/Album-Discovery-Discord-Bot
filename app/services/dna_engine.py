"""Music DNA Engine - Computes real-time genre spectrum, sonic traits,
energy levels, and acoustic DNA from session playback history.
"""
from collections import Counter
from typing import List, Dict, Any

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

# Artist to primary genre & subgenre taxonomy map
ARTIST_GENRE_MAP = {
    # Pop / Dance / Nu-Disco
    "dua lipa": ("Dance & Electronic", "Nu-Disco / Electropop", 88, 92, 12),
    "taylor swift": ("Pop & Mainstream", "Synth-Pop / Contemporary", 75, 78, 28),
    "one direction": ("Pop & Mainstream", "Pop-Rock / Teen Pop", 72, 70, 30),
    "lsd": ("Dance & Electronic", "Psychedelic Pop / EDM", 90, 85, 10),
    "sia": ("Pop & Mainstream", "Electropop / Power Pop", 85, 80, 18),
    "diplo": ("Dance & Electronic", "EDM / Dancehall", 92, 94, 6),
    "labrinth": ("R&B & Soul", "Art Pop / Soul", 78, 72, 22),
    "p!nk": ("Pop & Mainstream", "Pop-Rock / Power Pop", 86, 75, 20),
    "liam payne": ("Pop & Mainstream", "Dance-Pop / R&B", 80, 82, 15),
    "carly rae jepsen": ("Dance & Electronic", "Synth-Pop / Dance-Pop", 88, 90, 10),
    "benson boone": ("Pop & Mainstream", "Indie-Pop / Piano Ballad", 74, 60, 45),
    "jamie miller": ("Pop & Mainstream", "Soul-Pop / Ballad", 68, 62, 40),
    "jordana bryant": ("Pop & Mainstream", "Country-Pop / Teen Pop", 70, 68, 38),
    "alex sampson": ("Pop & Mainstream", "Indie-Pop / Contemporary", 72, 74, 25),
    "the vamps": ("Pop & Mainstream", "Pop-Rock / Power Pop", 84, 76, 22),
    "alexander stewart": ("Pop & Mainstream", "Pop-Soul / Acoustic", 65, 58, 45),
    "matt hansen": ("Pop & Mainstream", "Indie-Pop / Melodic", 68, 64, 38),
    "new hope club": ("Pop & Mainstream", "Pop-Rock / Indie Pop", 78, 75, 26),
    "olivia holt": ("Dance & Electronic", "Dance-Pop / Electropop", 86, 88, 14),
    "gabrielle aplin": ("Indie & Folk", "Folk-Pop / Indie Singer", 62, 55, 55),
    "why don't we": ("Pop & Mainstream", "Boyband Pop / Dance-Pop", 82, 80, 18),
    "ava max": ("Dance & Electronic", "Electropop / Euro-Dance", 92, 94, 8),
    "new rules": ("Pop & Mainstream", "Pop-Rock / Acoustic Pop", 76, 70, 32),
    "anne-marie": ("Pop & Mainstream", "Dance-Pop / UK Pop", 84, 82, 16),
    "lewis capaldi": ("Pop & Mainstream", "Power Ballad / Soul-Pop", 64, 45, 60),
    "the weeknd": ("R&B & Soul", "Synthwave / Dark R&B", 86, 88, 14),
    "ariana grande": ("Pop & Mainstream", "R&B / Dance-Pop", 82, 86, 18),
    "billie eilish": ("Indie & Folk", "Electropop / Alt-Pop", 65, 70, 35),
    "harry styles": ("Rock & Alternative", "Soft Rock / Pop-Rock", 76, 72, 34),
    "ed sheeran": ("Pop & Mainstream", "Acoustic Pop / Folk-Pop", 72, 68, 48),
    "olivia rodrigo": ("Rock & Alternative", "Pop-Punk / Alt-Rock", 88, 70, 22),
    "post malone": ("Hip-Hop & Rap", "Melodic Trap / Pop-Rap", 78, 80, 25),
    "drake": ("Hip-Hop & Rap", "Hip-Hop / Contemporary R&B", 78, 82, 18),
    "travis scott": ("Hip-Hop & Rap", "Psychedelic Trap", 90, 85, 10),
    "queen": ("Rock & Alternative", "Classic Rock / Arena Rock", 90, 70, 20),
    "metallica": ("Rock & Alternative", "Heavy Metal / Thrash", 95, 50, 5),
    "nirvana": ("Rock & Alternative", "Grunge / Alt-Rock", 92, 55, 15),
    "pink floyd": ("Rock & Alternative", "Progressive Rock / Psychedelic", 70, 40, 30),
    "daft punk": ("Dance & Electronic", "French House / Nu-Disco", 94, 96, 4),
    "avicii": ("Dance & Electronic", "Melodic House / Festival EDM", 92, 90, 12),
    "calvin harris": ("Dance & Electronic", "EDM / Electropop", 94, 94, 6),
    "skrillex": ("Dance & Electronic", "Dubstep / Bass Music", 96, 88, 4),
}

def classify_track_dna(artist: str, title: str) -> Dict[str, Any]:
    art_clean = (artist or "").lower().strip()
    tit_clean = (title or "").lower().strip()

    # 1. Exact or partial match in artist database
    for key, data in ARTIST_GENRE_MAP.items():
        if key == art_clean or key in art_clean:
            genre, sub, nrg, dnc, aco = data
            return {
                "genre": genre,
                "sub_genre": sub,
                "color": GENRE_COLORS.get(genre, "#94a3b8"),
                "energy": nrg,
                "danceability": dnc,
                "acoustic": aco
            }

    # 2. Heuristic fallback based on title / artist tokens
    combined = f"{art_clean} {tit_clean}"
    if any(k in combined for k in ("dj", "remix", "club", "dance", "electronic", "synth", "house", "techno", "dubstep", "bass")):
        return {"genre": "Dance & Electronic", "sub_genre": "Club / Dance", "color": GENRE_COLORS["Dance & Electronic"], "energy": 88, "danceability": 90, "acoustic": 10}
    if any(k in combined for k in ("rock", "metal", "guitar", "band", "punk", "orchestra", "symphony")):
        return {"genre": "Rock & Alternative", "sub_genre": "Rock / Alternative", "color": GENRE_COLORS["Rock & Alternative"], "energy": 85, "danceability": 60, "acoustic": 25}
    if any(k in combined for k in ("rap", "trap", "feat.", "ft.", "lil", "mc", "drill", "hip hop", "hip-hop")):
        return {"genre": "Hip-Hop & Rap", "sub_genre": "Hip-Hop / Rap", "color": GENRE_COLORS["Hip-Hop & Rap"], "energy": 82, "danceability": 84, "acoustic": 15}
    if any(k in combined for k in ("acoustic", "folk", "unplugged", "piano", "indie")):
        return {"genre": "Indie & Folk", "sub_genre": "Indie / Acoustic", "color": GENRE_COLORS["Indie & Folk"], "energy": 55, "danceability": 50, "acoustic": 70}
    if any(k in combined for k in ("soundtrack", "theme", "score", "ost")):
        return {"genre": "Soundtrack & Film", "sub_genre": "Cinematic Score", "color": GENRE_COLORS["Soundtrack & Film"], "energy": 65, "danceability": 45, "acoustic": 50}

    # Default to Pop & Mainstream
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
