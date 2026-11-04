"""Music DNA Engine - Computes real-time genre spectrum, sonic traits,
energy levels, and acoustic DNA from session playback history.
"""
import unicodedata
from collections import Counter
from typing import List, Dict, Any, Tuple

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

# Normalize string helper
def _norm(s: str) -> str:
    if not s:
        return ""
    t = str(s).replace("\ufffd", "'").replace("’", "'").replace("‘", "'").replace("`", "'")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("utf-8")
    return t.lower().strip()

# Artist to primary genre & subgenre taxonomy map
# (Genre, Sub-genre, Energy 0-100, Danceability 0-100, Acousticness 0-100)
ARTIST_GENRE_MAP: Dict[str, Tuple[str, str, int, int, int]] = {
    # --- Dance & Electronic / House / DnB / Nu-Disco ---
    "barry can't swim": ("Dance & Electronic", "Deep House / Electronic", 84, 88, 15),
    "barry cant swim": ("Dance & Electronic", "Deep House / Electronic", 84, 88, 15),
    "mild minds": ("Dance & Electronic", "Melodic House / Downtempo", 82, 85, 20),
    "two lanes": ("Dance & Electronic", "Melodic Electronic / Chill House", 80, 82, 22),
    "nora van elken": ("Dance & Electronic", "Melodic House / EDM", 86, 88, 12),
    "mathieu koss": ("Dance & Electronic", "Vocal Dance / House", 85, 88, 14),
    "svidden": ("Dance & Electronic", "Electropop / Progressive House", 88, 88, 12),
    "seeb": ("Dance & Electronic", "Tropical House / Electropop", 88, 90, 10),
    "odyssey": ("Dance & Electronic", "Dance / Club", 86, 86, 15),
    "sigma": ("Dance & Electronic", "Drum & Bass / Liquid DnB", 94, 86, 8),
    "emily makis": ("Dance & Electronic", "Drum & Bass / Vocal DnB", 92, 85, 10),
    "krasia": ("Dance & Electronic", "Drum & Bass / Neuro", 95, 84, 6),
    "eskei83": ("Dance & Electronic", "Drum & Bass / Bass Music", 96, 86, 5),
    "pirapus": ("Dance & Electronic", "Drum & Bass / Jump Up", 96, 84, 5),
    "kanine": ("Dance & Electronic", "Drum & Bass / Dancefloor", 97, 85, 4),
    "dutchican soul": ("Dance & Electronic", "Soulful House / Deep House", 86, 92, 10),
    "the vision": ("Dance & Electronic", "Nu-Disco / Classic House", 88, 92, 12),
    "moodena": ("Dance & Electronic", "Disco House / Funk", 87, 92, 12),
    "ezel": ("Dance & Electronic", "Afro House / Deep House", 85, 90, 15),
    "johnny fiasco": ("Dance & Electronic", "Chicago House / Tech House", 88, 92, 8),
    "kerri chandler": ("Dance & Electronic", "Deep House / Garage", 88, 92, 10),
    "klaus veen": ("Dance & Electronic", "UK Garage / Deep House", 90, 94, 8),
    "khamsin": ("Dance & Electronic", "Future Bass / Melodic", 84, 82, 18),
    "chase & status": ("Dance & Electronic", "Drum & Bass / Jungle", 96, 88, 4),
    "sub focus": ("Dance & Electronic", "Drum & Bass / Dancefloor", 95, 88, 5),
    "wilkinson": ("Dance & Electronic", "Drum & Bass / Liquid", 94, 86, 8),
    "dimension": ("Dance & Electronic", "Drum & Bass / Dancefloor", 95, 88, 5),
    "netsky": ("Dance & Electronic", "Drum & Bass / Liquid", 94, 86, 8),
    "fred again..": ("Dance & Electronic", "Club / UK Electronic", 88, 90, 15),
    "fred again": ("Dance & Electronic", "Club / UK Electronic", 88, 90, 15),
    "bicep": ("Dance & Electronic", "Electronic / Breakbeat", 90, 88, 10),
    "disclosure": ("Dance & Electronic", "UK Garage / House", 90, 94, 8),
    "daft punk": ("Dance & Electronic", "French House / Nu-Disco", 94, 96, 4),
    "avicii": ("Dance & Electronic", "Melodic House / Festival EDM", 92, 90, 12),
    "calvin harris": ("Dance & Electronic", "EDM / Electropop", 94, 94, 6),
    "skrillex": ("Dance & Electronic", "Dubstep / Bass Music", 96, 88, 4),
    "diplo": ("Dance & Electronic", "EDM / Dancehall", 92, 94, 6),
    "lsd": ("Dance & Electronic", "Psychedelic Pop / EDM", 90, 85, 10),
    "tiesto": ("Dance & Electronic", "EDM / Big Room", 94, 92, 6),
    "martin garrix": ("Dance & Electronic", "Festival EDM", 94, 92, 6),
    "david guetta": ("Dance & Electronic", "Dance-Pop / EDM", 92, 94, 8),
    "marshmello": ("Dance & Electronic", "Future Bass / EDM", 90, 90, 10),
    "kygo": ("Dance & Electronic", "Tropical House", 86, 88, 16),
    "rufus du sol": ("Dance & Electronic", "Live Electronic / Melodic House", 85, 86, 18),
    "camelphat": ("Dance & Electronic", "Tech House / Melodic Techno", 90, 92, 8),
    "fisher": ("Dance & Electronic", "Tech House / Club", 94, 95, 5),
    "chris lake": ("Dance & Electronic", "Tech House / Club", 93, 95, 6),
    "john summit": ("Dance & Electronic", "Tech House / Club", 93, 94, 6),
    "dom dolla": ("Dance & Electronic", "Tech House / Club", 93, 94, 6),
    "meduza": ("Dance & Electronic", "Deep House / EDM", 90, 92, 8),
    "alesso": ("Dance & Electronic", "Progressive House / EDM", 92, 90, 10),
    "galantis": ("Dance & Electronic", "Electropop / Dance", 92, 92, 8),
    "deadmau5": ("Dance & Electronic", "Progressive House / Electro", 90, 88, 10),
    "flume": ("Dance & Electronic", "Future Bass / Experimental", 88, 82, 15),
    "odesza": ("Dance & Electronic", "Chillwave / Future Bass", 86, 80, 20),
    "san holo": ("Dance & Electronic", "Future Bass / Indie Electronic", 85, 80, 22),
    "illenium": ("Dance & Electronic", "Melodic Dubstep / Future Bass", 88, 75, 18),
    "zedd": ("Dance & Electronic", "Electro House / Dance-Pop", 92, 90, 8),
    "carly rae jepsen": ("Dance & Electronic", "Synth-Pop / Dance-Pop", 88, 90, 10),
    "ava max": ("Dance & Electronic", "Electropop / Euro-Dance", 92, 94, 8),
    "olivia holt": ("Dance & Electronic", "Dance-Pop / Electropop", 86, 88, 14),

    # --- Rock & Alternative / Britpop ---
    "coldplay": ("Rock & Alternative", "Britpop / Alt-Rock", 80, 58, 35),
    "imagine dragons": ("Rock & Alternative", "Alt-Rock / Arena Rock", 88, 68, 20),
    "travis": ("Rock & Alternative", "Britpop / Post-Britpop", 74, 52, 45),
    "suede": ("Rock & Alternative", "Britpop / Glam Rock", 82, 55, 30),
    "the faim": ("Rock & Alternative", "Pop-Rock / Alt-Rock", 86, 62, 22),
    "fun.": ("Rock & Alternative", "Indie Pop / Baroque Pop", 84, 64, 25),
    "train": ("Rock & Alternative", "Roots Rock / Adult Pop", 78, 62, 35),
    "tonight": ("Rock & Alternative", "Pop-Rock / Alt-Rock", 82, 60, 28),
    "echosmith": ("Rock & Alternative", "Indie Pop / Pop-Rock", 78, 65, 30),
    "harry styles": ("Rock & Alternative", "Soft Rock / Pop-Rock", 76, 72, 34),
    "olivia rodrigo": ("Rock & Alternative", "Pop-Punk / Alt-Rock", 88, 70, 22),
    "queen": ("Rock & Alternative", "Classic Rock / Arena Rock", 90, 70, 20),
    "metallica": ("Rock & Alternative", "Heavy Metal / Thrash", 95, 50, 5),
    "nirvana": ("Rock & Alternative", "Grunge / Alt-Rock", 92, 55, 15),
    "pink floyd": ("Rock & Alternative", "Progressive Rock / Psychedelic", 70, 40, 30),
    "oasis": ("Rock & Alternative", "Britpop / Rock", 88, 55, 25),
    "blur": ("Rock & Alternative", "Britpop / Alt-Rock", 84, 62, 25),
    "radiohead": ("Rock & Alternative", "Art Rock / Alt-Rock", 76, 50, 35),
    "arctic monkeys": ("Rock & Alternative", "Indie Rock / Post-Punk", 88, 65, 20),
    "the killers": ("Rock & Alternative", "Indie Rock / Synth-Rock", 90, 68, 18),
    "muse": ("Rock & Alternative", "Space Rock / Alt-Rock", 92, 55, 15),
    "foo fighters": ("Rock & Alternative", "Post-Grunge / Hard Rock", 92, 55, 15),
    "linkin park": ("Rock & Alternative", "Nu-Metal / Alt-Rock", 94, 58, 12),
    "green day": ("Rock & Alternative", "Punk Rock / Pop-Punk", 92, 58, 15),
    "red hot chili peppers": ("Rock & Alternative", "Funk Rock / Alt-Rock", 88, 72, 20),
    "the 1975": ("Rock & Alternative", "Indie Pop / Synth-Pop", 82, 75, 25),
    "florence + the machine": ("Rock & Alternative", "Indie Rock / Baroque Pop", 85, 55, 30),
    "kings of leon": ("Rock & Alternative", "Southern Rock / Alt-Rock", 86, 60, 25),
    "the strokes": ("Rock & Alternative", "Garage Rock / Indie Rock", 88, 65, 18),
    "snow patrol": ("Rock & Alternative", "Alt-Rock / Power Ballad", 76, 48, 40),
    "keane": ("Rock & Alternative", "Piano Rock / Britpop", 75, 50, 42),
    "fall out boy": ("Rock & Alternative", "Pop-Punk / Alt-Rock", 90, 62, 15),
    "paramore": ("Rock & Alternative", "Pop-Punk / Alt-Rock", 90, 65, 18),
    "twenty one pilots": ("Rock & Alternative", "Indie Pop / Alt-Hip-Hop", 84, 75, 20),
    "u2": ("Rock & Alternative", "Post-Punk / Arena Rock", 85, 60, 25),

    # --- Indie & Folk / Acoustic ---
    "jason mraz": ("Indie & Folk", "Acoustic Pop / Singer-Songwriter", 68, 68, 60),
    "james bay": ("Indie & Folk", "Indie Singer-Songwriter / Soul", 70, 55, 55),
    "james blunt": ("Indie & Folk", "Acoustic Pop / Singer-Songwriter", 66, 52, 60),
    "dido": ("Indie & Folk", "Folk-Pop / Downtempo", 68, 60, 45),
    "bbc children in need": ("Indie & Folk", "All-Star Charity Ballad", 70, 45, 55),
    "gabrielle aplin": ("Indie & Folk", "Folk-Pop / Indie Singer", 62, 55, 55),
    "billie eilish": ("Indie & Folk", "Electropop / Alt-Pop", 65, 70, 35),
    "vance joy": ("Indie & Folk", "Indie Folk / Acoustic", 70, 65, 65),
    "george ezra": ("Indie & Folk", "Folk-Pop / Roots", 76, 70, 50),
    "dean lewis": ("Indie & Folk", "Acoustic Pop / Ballad", 68, 55, 60),
    "hozier": ("Indie & Folk", "Blues Rock / Indie Soul", 82, 62, 45),
    "mumford & sons": ("Indie & Folk", "Folk Rock / Bluegrass", 88, 60, 45),
    "the lumineers": ("Indie & Folk", "Folk Rock / Americana", 78, 62, 55),
    "passenger": ("Indie & Folk", "Folk-Pop / Acoustic", 64, 55, 70),
    "tom odell": ("Indie & Folk", "Indie Pop / Piano Ballad", 68, 48, 65),
    "jack johnson": ("Indie & Folk", "Acoustic / Surf Rock", 62, 65, 75),
    "john mayer": ("Indie & Folk", "Blues / Pop Singer-Songwriter", 74, 66, 50),
    "bon iver": ("Indie & Folk", "Indie Folk / Chamber Pop", 60, 45, 70),

    # --- R&B & Soul ---
    "the weeknd": ("R&B & Soul", "Synthwave / Dark R&B", 86, 88, 14),
    "beyonce": ("R&B & Soul", "Contemporary R&B / Pop", 84, 82, 20),
    "sza": ("R&B & Soul", "Alt-R&B / Neo-Soul", 75, 75, 30),
    "frank ocean": ("R&B & Soul", "Art Pop / Neo-Soul", 72, 65, 40),
    "alicia keys": ("R&B & Soul", "Soul / R&B Piano", 76, 68, 40),
    "john legend": ("R&B & Soul", "Neo-Soul / R&B Piano", 72, 62, 45),
    "sam smith": ("R&B & Soul", "Soul-Pop / Ballad", 74, 65, 35),
    "steve lacy": ("R&B & Soul", "Bedroom Pop / Neo-Soul", 76, 80, 25),
    "labrinth": ("R&B & Soul", "Art Pop / Soul", 78, 72, 22),
    "amy winehouse": ("R&B & Soul", "Soul / Jazz Pop", 78, 68, 35),
    "adele": ("R&B & Soul", "Soul-Pop / Power Ballad", 72, 50, 50),
    "leon bridges": ("R&B & Soul", "Retro Soul / R&B", 74, 72, 45),
    "daniel caesar": ("R&B & Soul", "Neo-Soul / R&B", 68, 65, 55),
    "giveon": ("R&B & Soul", "Baritone R&B / Soul", 70, 60, 45),

    # --- Hip-Hop & Rap ---
    "post malone": ("Hip-Hop & Rap", "Melodic Trap / Pop-Rap", 78, 80, 25),
    "drake": ("Hip-Hop & Rap", "Hip-Hop / Contemporary R&B", 78, 82, 18),
    "travis scott": ("Hip-Hop & Rap", "Psychedelic Trap", 90, 85, 10),
    "kendrick lamar": ("Hip-Hop & Rap", "Conscious Hip-Hop", 88, 82, 15),
    "j. cole": ("Hip-Hop & Rap", "Hip-Hop / Storytelling", 84, 80, 20),
    "eminem": ("Hip-Hop & Rap", "Hardcore Hip-Hop", 92, 80, 10),
    "kanye west": ("Hip-Hop & Rap", "Experimental Hip-Hop", 88, 82, 15),
    "central cee": ("Hip-Hop & Rap", "UK Drill / Trap", 88, 84, 12),
    "stormzy": ("Hip-Hop & Rap", "Grime / UK Hip-Hop", 90, 80, 15),
    "dave": ("Hip-Hop & Rap", "Conscious UK Rap", 85, 80, 20),
    "21 savage": ("Hip-Hop & Rap", "Trap / Hip-Hop", 86, 84, 12),
    "future": ("Hip-Hop & Rap", "Trap / Auto-Tune", 88, 86, 10),
    "juice wrld": ("Hip-Hop & Rap", "Emo Rap / Melodic", 84, 78, 20),
    "mac miller": ("Hip-Hop & Rap", "Jazz Rap / Alt-Hip-Hop", 78, 76, 30),

    # --- Pop & Mainstream ---
    "taylor swift": ("Pop & Mainstream", "Synth-Pop / Contemporary", 75, 78, 28),
    "dua lipa": ("Dance & Electronic", "Nu-Disco / Electropop", 88, 92, 12),
    "p!nk": ("Pop & Mainstream", "Pop-Rock / Power Pop", 86, 75, 20),
    "pink": ("Pop & Mainstream", "Pop-Rock / Power Pop", 86, 75, 20),
    "charlie puth": ("Pop & Mainstream", "Pop-Funk / Contemporary", 80, 82, 22),
    "maroon 5": ("Pop & Mainstream", "Pop-Rock / Funk-Pop", 82, 80, 20),
    "ellie goulding": ("Pop & Mainstream", "Electropop / Synth-Pop", 85, 84, 18),
    "ed sheeran": ("Pop & Mainstream", "Acoustic Pop / Pop", 74, 70, 42),
    "bruno mars": ("Pop & Mainstream", "Funk-Pop / R&B-Pop", 88, 90, 15),
    "ariana grande": ("Pop & Mainstream", "R&B / Dance-Pop", 82, 86, 18),
    "justin bieber": ("Pop & Mainstream", "Dance-Pop / R&B", 80, 82, 20),
    "katy perry": ("Pop & Mainstream", "Pop / Electropop", 88, 85, 15),
    "rihanna": ("Pop & Mainstream", "Pop / Dancehall / R&B", 86, 88, 15),
    "lady gaga": ("Pop & Mainstream", "Electropop / Dance-Pop", 90, 88, 12),
    "sabrina carpenter": ("Pop & Mainstream", "Nu-Disco Pop / Dance-Pop", 84, 86, 16),
    "chappell roan": ("Pop & Mainstream", "Synth-Pop / Glam Pop", 88, 84, 15),
    "benson boone": ("Pop & Mainstream", "Indie-Pop / Piano Ballad", 74, 60, 45),
    "one direction": ("Pop & Mainstream", "Pop-Rock / Teen Pop", 72, 70, 30),
    "sia": ("Pop & Mainstream", "Electropop / Power Pop", 85, 80, 18),
    "liam payne": ("Pop & Mainstream", "Dance-Pop / R&B", 80, 82, 15),
    "jamie miller": ("Pop & Mainstream", "Soul-Pop / Ballad", 68, 62, 40),
    "jordana bryant": ("Pop & Mainstream", "Country-Pop / Teen Pop", 70, 68, 38),
    "alex sampson": ("Pop & Mainstream", "Indie-Pop / Contemporary", 72, 74, 25),
    "the vamps": ("Pop & Mainstream", "Pop-Rock / Power Pop", 84, 76, 22),
    "alexander stewart": ("Pop & Mainstream", "Pop-Soul / Acoustic", 65, 58, 45),
    "matt hansen": ("Pop & Mainstream", "Indie-Pop / Melodic", 68, 64, 38),
    "new hope club": ("Pop & Mainstream", "Pop-Rock / Indie Pop", 78, 75, 26),
    "why don't we": ("Pop & Mainstream", "Boyband Pop / Dance-Pop", 82, 80, 18),
    "new rules": ("Pop & Mainstream", "Pop-Rock / Acoustic Pop", 76, 70, 32),
    "anne-marie": ("Pop & Mainstream", "Dance-Pop / UK Pop", 84, 82, 16),
    "lewis capaldi": ("Pop & Mainstream", "Power Ballad / Soul-Pop", 64, 45, 60),
    "selena gomez": ("Pop & Mainstream", "Dance-Pop / Synth-Pop", 80, 82, 20),
    "camila cabello": ("Pop & Mainstream", "Latin Pop / Pop", 84, 86, 18),
    "shawn mendes": ("Pop & Mainstream", "Pop-Rock / Acoustic", 76, 70, 35),
    "onerepublic": ("Pop & Mainstream", "Pop-Rock / Synth-Pop", 85, 75, 22),
    "jonas brothers": ("Pop & Mainstream", "Pop-Rock / Dance-Pop", 84, 80, 20),
    "tate mcrae": ("Pop & Mainstream", "Dance-Pop / Alt-Pop", 86, 88, 16),
    "gracie abrams": ("Indie & Folk", "Bedroom Pop / Indie", 64, 52, 60),
}


def classify_track_dna(artist: str, title: str) -> Dict[str, Any]:
    art_clean = _norm(artist)
    tit_clean = _norm(title)

    # 1. Exact or substring match in artist database
    for key, data in ARTIST_GENRE_MAP.items():
        if key == art_clean or (len(key) > 3 and key in art_clean):
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
