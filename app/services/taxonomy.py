"""Canonical Music Taxonomy, Deduplication, and Master Release Grouping Engine.

Handles canonical category normalization (Studio Albums, Singles, EPs, Live, Compilations,
Remixes, Soundtracks, Duets), algorithmic master title cleaning, and deduplication of
multiple digital release editions into consolidated parent albums.
"""
import re
from . import deezer_api
from .. import store

def clean_master_title(title: str) -> str:

    """Robust title cleaner handling bracketed and unbracketed edition suffixes,

    Apple Music spatial audio / master badges, and deluxe reissue tags.

    """

    t = (title or "").strip()

    # Normalize unicode apostrophes, quotes, and replacement characters

    t = t.replace("\ufffd", "'").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')

    # Normalize letter/number boundaries: LP2 -> LP 2

    t = re.sub(r"(\b[A-Za-z]+)(\d+)\b", r"\1 \2", t)

    # 1. Bracketed or parenthesized tags (Apple Digital Master, Spatial Audio, Dolby Atmos, Deluxe, Remastered, Bonus Tracks)

    t = re.sub(

        r"[\(\[][^\)\]]*(?:"

        r"apple digital master|spatial audio|dolby atmos|atmos|"

        r"scary hours|deluxe|anniversary|expanded|complete|collector|bonus tracks?|bonus version|"

        r"remaster(?:ed)?|edition|special|version|instrumental|acapella|remix|mourner|epilogue|prologue|"

        r"international|uk version|us version"

        r")[^\)\]]*[\)\]]",

        "",

        t,

        flags=re.IGNORECASE

    )

    # 2. Date spans after colons/dashes: : 1993-2005, - 1990-1999

    t = re.sub(r"[:\-–]\s*(?:\d{4}\s*[\-–]\s*\d{4}|\d{4})\b.*$", "", t)

    # 3. Universal edition sub-titles after colons or dashes

    t = re.sub(

        r"[:\-–]\s*(?:"

        r"refill|re-?up|side\s+[ab0-9]+|scary hours.*|expanded.*|deluxe.*|bonus.*|mourner.*|epilogue.*|prologue.*|"

        r"edition.*|version.*|vol(?:ume)?\.?\s*\d+.*|part\s+\d+.*|pt\.?\s*\d+.*|chapter\s+\d+.*|"

        r"apple digital master.*|spatial audio.*|anniversary.*|collector'?s?.*|complete.*|reissue.*|remaster.*"

        r")[^\)]*\b.*$",

        "",

        t,

        flags=re.IGNORECASE

    )

    # 4. Universal unbracketed edition suffixes
    t = re.sub(
        r"\b(?:"
        r"scary hours|deluxe(?: edition)?|anniversary(?: edition)?|expanded(?: edition)?|complete(?: edition)?|"
        r"collector'?s?(?: edition)?|bonus tracks?(?: version)?|bonus track version|"
        r"remaster(?:ed)?|refill|side [ab0-9]+|tour edition|"
        r"apple digital master|spatial audio|"
        r"(?:platinum|diamond|gold|limited|special|alternate|international|uk|us)(?:\s+[a-z0-9]+)?\s+(?:edition|version|release|reissue)"
        r")\b.*$",
        "",
        t,
        flags=re.IGNORECASE
    )

    # 5. Trailing hyphen separators: "Trouble - Deluxe"

    t = re.sub(r"\s+-\s+.*$", "", t)

    # Strip any trailing punctuation (colons, dashes, commas, semicolons)

    t = re.sub(r"[\s:;,\-\–]+$", "", t)

    return re.sub(r"\s+", " ", t).strip()

def _clean_for_lookup(title: str) -> str:

    """Normalized alphanumeric key for loose cross-catalog release matching (e.g. Vol. 1 <-> Volume 1)."""

    t = clean_master_title(title).lower()

    t = re.sub(r"\bvol(?:ume)?\.?\s*", "volume", t)

    return re.sub(r"[^a-z0-9]", "", t)

def _norm_group_key_title(title: str) -> str:

    """Normalized base key for master release grouping, collapsing leading 'The' and combined reissue titles."""

    base = clean_master_title(title).lower()

    base = re.sub(r"^the\s+", "", base)

    base = re.sub(r"/.*$", "", base)

    return re.sub(r"\s+", " ", base).strip()

_BUDGET_COMPILATION_PATTERNS = (
    r"\b("
    r"greatest hits|the essential|anthology|best of|collection|the hits|definitive|"
    r"golden hits|favorites|anniversary collection|portrait of|classic dolly|classic [a-z0-9]+|"
    r"super hits|platinum collection|songbook|master series|budget series|"
    r"ultimate|great songs|\d+\s+great songs|\d+\s+all-time|\d+\s+hits|\d+\s+classics|"
    r"the great (?:hits|collection|anthology|classics)|hits made famous|"
    r"songs of faith|faith & inspiration|gospel favorites|reader's digest|"
    r"millennium collection|20th century masters|heritage series|"
    r"re-recordings?|re-recorded|rerecorded|newly recorded|"
    r"box set|rarities|b-sides|outtakes|unreleased|leftovers|extra credit|vault|"
    r"complete sessions|rare and unreleased|vol(?:ume)?\.?\s*\d+|r\.?i\.?p\.?|various artists|"
    r"love songs|songs of love|with love|greatest love songs|\d+\s+very special love songs|romance|romantic hits|love ballads|"
    r"i will always love you|unforgettable|a contribution|"
    r"ten years of gold|twenty years of|golden legends|classic country|country classics|gold series|"
    r"ruby,? don'?t take (?:your )?love to town|tell it all,? brother|"
    r"christmas with [a-z0-9\s]+|christmas wishes|christmas favorites|christmas collection|at christmas|"
    r"vote for love\s*2|vote for love\s*ii|"
    r"me and bobby mcgee|love is what we make it|sunshine"
    r")\b"
)

_COLLAB_DUET_PATTERNS = (
    r"\b("
    r"porter & dolly|porter 'n' dolly|porter wayne|just between you and me|"
    r"two of a kind|together always|we found it|say forever you'll be mine|"
    r"love and music|once upon a christmas|the winning hand|honky tonk angels|"
    r"always, always|the right combination|once more|just the two of us|"
    r"kenny & dottie|kenny and dottie|every time two fools collide|classics|time and tide|"
    r"duets?|collaborations?|and friends|with [a-z\s]+"
    r")\b"
)

def _is_collaborative_release(album_artist: str, target_artist: str, title: str = "") -> bool:

    """Detect if a release is a collaborative, duet, or multi-artist project."""

    a_norm = _normalize_name_for_match(album_artist)

    tgt_norm = _normalize_name_for_match(target_artist)

    t = (title or "").lower()

    if re.search(_COLLAB_DUET_PATTERNS, t) or re.match(r"^trio(?:\s+[ivx]+|\s+ii|\s+iii)?$", t):

        return True

    if not a_norm or not tgt_norm:

        return False

    if a_norm == tgt_norm:

        return False

    if tgt_norm in a_norm:

        collab_markers = ["and", "with", "feat", "featuring", "duet", "presents", "x"]

        if any(m in a_norm for m in collab_markers) or len(a_norm) >= len(tgt_norm) + 4:

            return True

    return False

def _normalize_category(cat: str, title: str = "", track_count: int = 0) -> str:

    c = (cat or "").strip().lower()

    t = (title or "").strip().lower()

    if re.search(r"\b(instrumental|instrumentals|acapella|a cappella|acapellas|karaoke|interview|interviews|collaborators|commentary|radio show|spoken word|sampler|snippet)\b", t) or "interview" in c:

        return "Other"

    if re.search(r"\b(remix|remixes|remixed|reconfigured|r3c0nf1gur3d|club mix|dub mix|megamix|mashup)\b", t) or "remix" in c:

        return "Remixes"

    if re.search(r"\b(soundtrack|motion picture|original score|original soundtrack|\bost\b|music from the motion picture|music from the film)\b", t) or "soundtrack" in c:

        if (0 < track_count <= 2) or "single" in c or t.endswith(" - single"):

            return "Singles"

        return "Soundtracks"

    if re.search(r"\b(live|concert|in concert|live at|live from|live in|unplugged|broadcast|sessions?|acoustic live|bbc live|tour)\b", t) or "live" in c:

        return "Live Albums"

    if (

        re.search(_BUDGET_COMPILATION_PATTERNS, t)

        or "compilation" in c

        or "compile" in c

        or "presents" in t

    ):

        return "Compilations"

    if re.search(_COLLAB_DUET_PATTERNS, t) or re.match(r"^trio(?:\s+[ivx]+|\s+ii|\s+iii)?$", t):

        return "Collaborative / Duets"

    if "ep" in c or t.endswith(" - ep") or " ep" in t or (3 <= track_count <= 5 and not t.endswith(" - single")):

        return "EPs"

    if "single" in c or t.endswith(" - single") or (0 < track_count <= 2):

        return "Singles"

    if 0 < track_count < 6:

        return "EPs" if track_count >= 3 else "Singles"

    return "Studio Albums"

def _classify_album_with_taxonomy(item: dict, mb_map: dict = None, target_artist: str = "") -> str:

    """Strictly classify album into canonical category with MusicBrainz authority and strict gates.

    Hierarchy:

    1. MusicBrainz is the SOLE authority for release categorization (Taxonomy).

       Never let a commercial record_type=='album' override a canonical MusicBrainz classification.

    2. Strict Studio Album Gate:

       An item may ONLY be classified under 'Studio Albums' if:

       - MusicBrainz Primary Type is 'Album'

       - MusicBrainz Secondary Types is EMPTY (no Compilation, Live, Remix, Soundtrack, Spokenword, etc.)

       - The release has only ONE primary artist credit matching searched artist (no 'with', '&', 'feat', or multi-artist credits).

    3. Universal Category Routing:

       - Multi-artist projects & joint records -> 'Collaborative / Duets'

       - Secondary Type contains 'Live' or title matches \\b(live|concert|tour)\\b -> 'Live Albums'

       - Secondary Type contains 'Compilation' or title matches reissue keywords -> 'Compilations'

       - Secondary Type contains 'Soundtrack' AND tracks > 2 -> 'Soundtracks'

       - Tracks <= 2 or Primary Type 'Single' -> 'Singles' (with badges for OST/Remixes)

    """

    t = (item.get("title") or "").strip().lower()

    rec_t = (item.get("record_type") or "").strip().lower()

    trk_cnt = int(item.get("nb_tracks") or item.get("tracks_count") or item.get("track_count") or 0)

    target_lower = (target_artist or "").strip().lower()

    alb_artist = (item.get("artist") or item.get("artist_name") or "").strip()

    # Step 1: MusicBrainz Authoritative Catalog Resolution

    if mb_map:

        lookup_k = _clean_for_lookup(item.get("title") or "")

        base_k = clean_master_title(item.get("title") or "").lower()

        norm_group_k = _norm_group_key_title(item.get("title") or "")

        mb_entry = mb_map.get(lookup_k) or mb_map.get(base_k) or mb_map.get(norm_group_k)

        if mb_entry:

            mb_cat = mb_entry.get("category")

            if mb_entry.get("is_soundtrack"):

                item["is_soundtrack"] = True

                item["badge"] = "Soundtrack"

            if mb_entry.get("is_collaborative"):

                item["is_collaborative"] = True

            # Physical Sanity Check: 1-2 tracks is a Single even if MB matched an album of same title
            if trk_cnt in (1, 2) and mb_cat == "Studio Albums":
                return "Singles"

            # Physical Sanity Check: 7+ tracks is an Album even if MB matched a lead single
            if trk_cnt >= 7 and mb_cat == "Singles":
                mb_cat = "Studio Albums"

            # If MusicBrainz says Studio Albums, apply the Strict Studio Album Gate:

            if mb_cat == "Studio Albums":

                s_types = mb_entry.get("secondary_types") or []

                if len(s_types) > 0:

                    if any(x.title() in ("Live",) for x in s_types):

                        return "Live Albums"

                    if any(x.title() in ("Remix",) for x in s_types):

                        return "Remixes"

                    if any(x.title() in ("Soundtrack",) for x in s_types):
                        return "Soundtracks"
                    if any(x.lower() in ("mixtape/street", "mixtape", "street") for x in s_types):
                        return "Mixtapes & Street"
                    return "Compilations"

                if mb_entry.get("is_collaborative") or _is_collaborative_release(alb_artist, target_artist, t):

                    return "Collaborative / Duets"

                return "Studio Albums"

            # MusicBrainz is SOLE authority: never allow commercial record_type == "album" to override

            return mb_cat

    # Step 2: Universal Category Routing (Fallback heuristics)

    # A. Spoken Word / Interviews / Instrumentals / Demos -> Other

    if re.search(r"\b(instrumental|instrumentals|acapella|a cappella|acapellas|karaoke|interview|interviews|collaborators|commentary|radio show|spoken word|sampler|snippet)\b", t):

        return "Other"

    # B. Collaborative / Duets Validation

    if _is_collaborative_release(alb_artist, target_artist, t):

        return "Collaborative / Duets"

    # C. Remixes

    if re.search(r"\b(remix|remixes|remixed|reconfigured|r3c0nf1gur3d|club mix|dub mix|megamix|mashup)\b", t) or "remix" in rec_t:

        return "Remixes"

    # D. Soundtracks vs. Singles routing:

    has_soundtrack_kw = bool(

        re.search(r"\b(soundtrack|motion picture|original score|original soundtrack|\bost\b|music from the motion picture|music from the film)\b", t)

        or "soundtrack" in rec_t

    )

    if has_soundtrack_kw:

        if (0 < trk_cnt <= 2) or rec_t == "single" or t.endswith(" - single"):

            item["is_soundtrack"] = True

            item["badge"] = "Soundtrack"

            return "Singles"

        return "Soundtracks"

    # E. Live Albums

    if re.search(r"\b(live|concert|in concert|live at|live from|live in|unplugged|broadcast|sessions?|acoustic live|bbc live|tour)\b", t) or "live" in rec_t:

        return "Live Albums"

    # F. Expanded Compilation & Budget Release Blacklist

    artist_budget_match = False

    if target_lower and len(target_lower) >= 3:

        artist_budget_match = bool(re.search(r"\b(?:the great|i am)\s+" + re.escape(target_lower) + r"\b", t))

        if target_lower == "kenny rogers" and re.search(r"\b(faith|ruby|after all)\b", t):

            artist_budget_match = True

    if (

        re.search(_BUDGET_COMPILATION_PATTERNS, t)

        or artist_budget_match

        or "compilation" in rec_t

        or "compile" in rec_t

        or " presents " in t

        or t.endswith(" presents")

        or re.search(r"^[a-z0-9\s]+ presents\b", t)

    ):

        return "Compilations"

    # G. Physical Track Count Sanity Overrides:
    # 7+ tracks is physically an Album (never a Single)
    if trk_cnt >= 7:
        return "Studio Albums"

    # 1-2 tracks is physically a Single
    if 0 < trk_cnt <= 2 or t.endswith(" - single") or rec_t == "single":
        return "Singles"

    # 3-6 tracks is physically an EP
    if (0 < trk_cnt < 7) or t.endswith(" - ep") or rec_t == "ep":
        return "EPs"

    # Fallback by record_type
    if rec_t in ("album", "lp"):
        return "Studio Albums"

    return "Studio Albums" 

def build_mb_map(mb_albums: list[dict]) -> dict:
    """Build canonical MusicBrainz lookup map with strict priority:
    Studio Albums (4) > EPs (3) > Original Singles (2) > Compilations (1) > Remixes/Other (0).
    Ensures standard original releases are never overwritten or hijacked by remix editions.
    """
    mb_map = {}
    if not mb_albums:
        return mb_map

    for a in mb_albums:
        base = clean_master_title(a.get("title") or "").lower()
        lookup_k = _clean_for_lookup(a.get("title") or "")
        is_clean = len(a.get("secondary_types") or []) == 0
        cat = a.get("category")

        prio = 4 if cat == "Studio Albums" else (
            3 if cat == "EPs" else (
                2 if (cat == "Singles" and is_clean) else (
                    1 if is_clean else 0
                )
            )
        )

        for k in (base, lookup_k):
            if not k:
                continue
            existing = mb_map.get(k)
            if existing:
                ex_cat = existing.get("category")
                ex_clean = len(existing.get("secondary_types") or []) == 0
                ex_prio = 4 if ex_cat == "Studio Albums" else (
                    3 if ex_cat == "EPs" else (
                        2 if (ex_cat == "Singles" and ex_clean) else (
                            1 if ex_clean else 0
                        )
                    )
                )
                if prio > ex_prio:
                    mb_map[k] = a
            else:
                mb_map[k] = a

    return mb_map


def consolidate_master_release_groups(albums: list[dict], mb_map: dict = None) -> list[dict]:

    """Consolidate multiple digital editions, reissues, and deluxe packages

    into a single Master Release Group card.

    Sets the canonical year to the earliest release date (e.g., 2004 for Trouble, 2006 for Konvicted).

    Defaults to the Original/Standard edition for pure, non-duplicated tracklists.

    Preserves all editions inside album['editions'] for the edition dropdown selector.

    """

    master_groups = {}

    for alb in albums:

        cat = alb.get("category") or "Studio Albums"

        base_title = clean_master_title(alb.get("title") or "")

        base_lower = base_title.lower()

        group_title_key = _norm_group_key_title(base_title)

        lookup_k = _clean_for_lookup(alb.get("title") or "")

        # If canonical Studio Album in mb_map, align master card

        if mb_map:

            mb_entry = mb_map.get(lookup_k) or mb_map.get(base_lower)

            if mb_entry and mb_entry.get("category") == "Studio Albums":

                rec_t = (alb.get("record_type") or "").lower()

                if rec_t in ("album", ""):

                    if cat not in ("Live Albums", "Compilations", "Remixes", "Soundtracks", "Other", "EPs", "Singles", "Collaborative / Duets"):

                        cat = "Studio Albums"

                        alb["category"] = "Studio Albums"

            elif mb_entry and mb_entry.get("category") == "Collaborative / Duets":

                cat = "Collaborative / Duets"

                alb["category"] = "Collaborative / Duets"

            elif mb_entry and mb_entry.get("category") == "Compilations":

                cat = "Compilations"

                alb["category"] = "Compilations"

        group_key = (group_title_key, cat)

        if group_key not in master_groups:

            master_groups[group_key] = {

                "base_title": base_title,

                "category": cat,

                "editions": []

            }

        master_groups[group_key]["editions"].append(alb)

    # Ensure all canonical Studio Albums from MusicBrainz authority are represented!

    if mb_map:

        for base_lower, mb_album in mb_map.items():

            cat = mb_album.get("category") or "Studio Albums"

            group_title_key = _norm_group_key_title(mb_album.get("title") or base_lower)

            group_key = (group_title_key, cat)

            yr = str(mb_album.get("year") or "").strip()

            mb_tit = (mb_album.get("title") or "").lower()

            # Disallow live concert venues, tour dates, and fan bootlegs from being classified as Studio Albums

            is_bootleg_or_live = (

                re.search(r"\b(bootleg|unreleased|unmastered|prank|leak|demo|promo|sampler|acetate|fan\s*club|white\s*label)\b", mb_tit)

                or re.search(r"\b(ballroom|stadium|arena|dome|theatre|theater|pavilion|auditorium|academy|field|hall|bowl|tour|concert|showdown|project)\b", mb_tit)

                or re.search(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", mb_tit)

                or re.search(r"\b\d{4}[-_/]\d{2}[-_/]\d{2}\b", mb_tit)

            )

            is_valid_studio_lp = (

                cat == "Studio Albums"

                and len(yr) == 4

                and yr.isdigit()

                and not is_bootleg_or_live

                and not re.search(_BUDGET_COMPILATION_PATTERNS, mb_tit)

                # CRITICAL: Do NOT promote unverified MusicBrainz-only entries that lack official streaming presence & cover art

                and not (mb_album.get("source") == "MusicBrainz" and "coverartarchive.org" in (mb_album.get("cover") or ""))

            )

            if is_valid_studio_lp:

                lookup_k = _clean_for_lookup(mb_album.get("title") or base_lower)

                already_present = any(

                    k[0] == group_title_key or _clean_for_lookup(k[0]) == lookup_k

                    for k in master_groups.keys()

                )

                if not already_present and group_key not in master_groups:

                    master_groups[group_key] = {

                        "base_title": mb_album.get("title") or base_lower.title(),

                        "category": cat,

                        "editions": [mb_album]

                    }

    consolidated = []

    for (base_lower, cat), group in master_groups.items():

        editions = sorted(
            group["editions"],
            key=lambda x: (
                0 if (x.get("record_type") or "").lower() == "album" else (1 if (x.get("record_type") or "").lower() == "ep" else 2),
                0 if int(x.get("tracks_count") or x.get("nb_tracks") or 0) >= 4 else 1,
                1 if re.search(r"\b(remix|remixes|remixed|edit|dub|vip|mix|karaoke|instrumental)\b", (x.get("title") or "").lower()) else 0,
                str(x.get("full_release_date") or x.get("release_date") or x.get("year") or "9999")
            )
        )

        primary = editions[0]
        mb_entry = mb_map.get(base_lower) if mb_map else None

        candidates = []
        if mb_entry and mb_entry.get("year"):
            y_str = str(mb_entry["year"])[:4]
            if y_str.isdigit() and len(y_str) == 4:
                candidates.append(y_str)

        for e in editions:
            ey = str(e.get("year") or e.get("release_date") or e.get("full_release_date") or "")[:4]
            if ey.isdigit() and len(ey) == 4:
                candidates.append(ey)

        earliest_year = min(candidates) if candidates else str(primary.get("year") or primary.get("release_date") or primary.get("full_release_date") or "")[:4]

        master_album = dict(primary)

        master_album["title"] = group["base_title"] or primary.get("title", "")

        master_album["year"] = earliest_year

        master_album["release_date"] = earliest_year

        master_album["category"] = cat

        # Propagate soundtrack single badge if any edition has it

        if any(e.get("is_soundtrack") for e in editions):

            master_album["is_soundtrack"] = True

            master_album["badge"] = "Soundtrack"

        edition_list = []

        for e in editions:

            e_year = str(e.get("release_date") or e.get("full_release_date") or "")[:4]

            edition_list.append({

                "id": str(e.get("id", "")),

                "title": e.get("title", ""),

                "year": e_year,

                "tracks_count": e.get("tracks_count", 0),

                "cover": e.get("cover", ""),

                "is_default": (str(e.get("id")) == str(primary.get("id")))

            })

        master_album["editions"] = edition_list

        consolidated.append(master_album)

    # Sort albums: newest year descending

    consolidated.sort(key=lambda x: str(x.get("year") or "0000"), reverse=True)

    return consolidated

def get_album_editions(artist_id: str, current_album_id: str, title: str) -> list[dict]:

    """Find other editions of the same master album (standard, deluxe, anniversary) for dropdown selector."""

    aid = str(artist_id or "").strip()

    if not aid:

        return []

    base_title = clean_master_title(title).lower()

    if not base_title:

        return []

    cache_key = f"editions:{aid}:{base_title}"

    try:

        cached = store.get_api_cache(cache_key)

        if cached:

            return cached

    except Exception:

        pass

    try:

        disc = deezer_api.get_artist_discography(aid, limit=80)

        matching = []

        for alb in disc:

            alb_base = clean_master_title(alb.get("title") or "").lower()

            if alb_base == base_title:

                matching.append(alb)

        if len(matching) <= 1:

            return []

        matching.sort(key=lambda x: str(x.get("release_date") or x.get("full_release_date") or "9999"))

        editions = []

        for m in matching:

            m_id = str(m.get("id", ""))

            m_yr = str(m.get("release_date") or m.get("full_release_date") or "")[:4]

            m_title = m.get("title", "")

            tc = m.get("tracks_count", 0)

            if not tc:

                d = deezer_api.get_album_details(m_id)

                if d and not d.get("error"):

                    tc = len(d.get("tracks", []))

            label = m_title

            if tc:

                label = f"{label} [{tc} Tracks]"

            if m_yr:

                label = f"{label} ({m_yr})"

            editions.append({

                "id": m_id,

                "title": m_title,

                "label": label,

                "year": m_yr,

                "tracks_count": tc,

                "is_current": (m_id == str(current_album_id))

            })

        try:

            store.set_api_cache(cache_key, editions, ttl_seconds=86400 * 7, namespace="editions")

        except Exception:

            pass

        return editions

    except Exception:

        return []

def _normalize_name_for_match(s: str) -> str:

    _q_chars = "\'\"`\u2018\u2019\u201c\u201d"

    s = (s or "").lower().strip().strip(_q_chars)

    if s.startswith("the "):

        s = s[4:].strip()

    s = s.replace("!", "i").replace("$", "s").replace("@", "a").replace("&", "and").replace("+", "and")

    return re.sub(r"[^a-z0-9]", "", s)

def _is_artist_match(query: str, artist_name: str) -> bool:

    q_norm = _normalize_name_for_match(query)

    a_norm = _normalize_name_for_match(artist_name)

    if not q_norm or not a_norm:

        return False

    return q_norm == a_norm

def _album_matches_artist(album_artist: str, target_artist: str) -> bool:

    alb_a = _normalize_name_for_match(album_artist)

    tgt_a = _normalize_name_for_match(target_artist)

    if not alb_a or not tgt_a:

        return True

    if alb_a == tgt_a:

        return True

    if tgt_a in alb_a:

        return True

    return False

