"""Unified Live Music Discovery Orchestrator.

Combines Deezer (high-res artwork, live charts, previews) with MusicBrainz

for canonical album categorization (Studio Albums, EPs, Singles, Live, Compilations, Remixes).

"""

import re
from . import deezer_api
from . import musicbrainz_api
from . import itunes_api
from .. import store
from core.logger import get_logger, get_search_logger
_log = get_logger("discovery")

_search_log = get_search_logger()

def get_live_genres() -> list[dict]:
    """Return live genre list."""
    return deezer_api.get_live_genres()
def get_chart_albums(genre_id: int = 0, limit: int = 36) -> list[dict]:
    """Return trending charts for a genre or global."""
    albums = deezer_api.get_chart_albums(genre_id=genre_id, limit=limit)
    for a in albums:
        if not a.get("category"):
            rec_t = (a.get("record_type") or "").lower()
            if "single" in rec_t:
                a["category"] = "Singles"
            elif "ep" in rec_t:
                a["category"] = "EPs"
            elif "compile" in rec_t or "compilation" in rec_t:
                a["category"] = "Compilations"
            else:
                a["category"] = "Studio Albums"
    return albums
# Canonical Music Taxonomy & Release Group Deduplication Engine
from .taxonomy import (
    build_mb_map,
    clean_master_title,
    consolidate_master_release_groups,
    get_album_editions,
    _classify_album_with_taxonomy,
    _normalize_category,
    _is_collaborative_release,
    _normalize_name_for_match,
    _is_artist_match,
    _album_matches_artist,
    _clean_for_lookup,
    _norm_group_key_title,
)

def search_music(query: str, limit: int = 48) -> dict:
    """Smart live search with Master Release Group binding, MusicBrainz canonical taxonomy,
    strict artist ID isolation, and earliest release year normalization.
    """
    raw_q = query or ""
    _q_chars = "\'\"`\u2018\u2019\u201c\u201d"
    q = raw_q.strip().strip(_q_chars)
    if not q:
        return {"artists": [], "albums": [], "categories": [], "counts": {}}
    # 1. Search for matching artists
    artists = deezer_api.search_artists(q, limit=6)
    discography_albums = []
    mb_categorized = None
    related_artists = []
    artist_hero = None
    is_artist_search = False
    target_artist_name = ""
    target_artist_id = ""
    if artists:
        candidate = artists[0]
        if _is_artist_match(q, candidate["name"]):
            is_artist_search = True
            top_artist = candidate
        elif len(artists) > 1 and _is_artist_match(q, artists[1]["name"]):
            is_artist_search = True
            top_artist = artists[1]
        else:
            top_artist = candidate
        artist_name = top_artist["name"]
        target_artist_id = str(top_artist["id"])
        target_artist_name = artist_name
        # Fetch Top 5 popular tracks & profile data for integrated Artist Hero
        try:
            top_tracks = deezer_api.get_artist_top_tracks(target_artist_id, limit=5)
            artist_hero = {
                "id": target_artist_id,
                "name": target_artist_name,
                "picture": top_artist.get("picture_xl") or top_artist.get("picture_big") or top_artist.get("picture_medium") or "",
                "fans": top_artist.get("nb_fan") or top_artist.get("fans", 0),
                "top_tracks": top_tracks
            }
        except Exception as exc:
            _log.debug("Artist hero fetch notice: %s", exc)
        # Fetch similar/related artists for rabbit-hole discovery
        try:
            related_artists = deezer_api.get_related_artists(target_artist_id, limit=15)
        except Exception as exc:
            _log.debug("Related artists fetch notice: %s", exc)
        # MusicBrainz categorized discography & canonical release years
        mb_map = {}
        try:
            mb_categorized = musicbrainz_api.get_artist_categorized_discography(artist_name, limit=100)
            if mb_categorized and mb_categorized.get("albums"):
                mb_map = build_mb_map(mb_categorized["albums"])
        except Exception as exc:
            _log.debug("MB categorized fetch notice: %s", exc)
        # Deezer direct relational discography
        raw_dz = deezer_api.get_artist_discography(target_artist_id, limit=limit * 2)
        # Strict artist ID filtering: Discard any release where artist ID does not match
        filtered_dz = []
        for alb in raw_dz:
            alb_art_id = str(alb.get("artist_id") or "")
            if alb_art_id and alb_art_id != target_artist_id:
                continue
            alb["artist"] = artist_name
            alb["category"] = _classify_album_with_taxonomy(alb, mb_map, target_artist=artist_name)
            filtered_dz.append(alb)
        # Consolidate multiple editions under single Master Release Group cards
        discography_albums = consolidate_master_release_groups(filtered_dz, mb_map=mb_map)
    # Search local library on hard drives (hybrid local + online discovery)
    local_hits = []
    try:
        from .. import store
        raw_local = []
        for alb in raw_local:
            local_hits.append({
                "id": str(alb["id"]),
                "title": alb.get("title") or "Unknown Album",
                "artist": alb.get("artist") or "Unknown Artist",
                "year": str(alb.get("year") or "")[:4],
                "cover": alb.get("cover") or f"/api/library/cover?id={alb['id']}",
                "category": "Local Library",
                "track_count": alb.get("track_count") or 0,
                "drive_root": alb.get("drive_root") or "Local",
                "is_local": True
            })
    except Exception as exc:
        _log.debug("Local album search notice: %s", exc)
    # Track & Remix Search (Universal Deezer + YouTube Songs & Remixes)
    search_tracks_list = []
    try:
        from . import stream_service
        # Search Deezer tracks
        dz_tracks = deezer_api.search_tracks(q, limit=10)
        for dt in dz_tracks:
            dt["source"] = "deezer"
            search_tracks_list.append(dt)
        # Search YouTube tracks/remixes (vital for remix queries, bootlegs, or general track titles)
        is_remix_query = any(
            k in q.lower()
            for k in ["remix", "mix", "edit", "bootleg", "version", "flip", "mashup", "live", "acoustic", "feat", "ft.", "we have got this"]
        )
        should_query_yt = is_remix_query or (not is_artist_search) or (len(search_tracks_list) < 5)
        if should_query_yt:
            yt_tracks = stream_service.search_youtube_tracks(q, limit=6)
            if is_remix_query and yt_tracks:
                combined_tracks = yt_tracks + search_tracks_list
            else:
                combined_tracks = search_tracks_list + yt_tracks
        else:
            combined_tracks = search_tracks_list
        # Deduplicate tracks by id or title
        deduped_tracks = []
        seen_track_keys = set()
        for t in combined_tracks:
            key = (t.get("video_id") or t.get("id") or t.get("title", "")).strip().lower()
            if key not in seen_track_keys:
                seen_track_keys.add(key)
                deduped_tracks.append(t)
        search_tracks_list = deduped_tracks[:12]
    except Exception as exc:
        _log.debug("Track search exception notice: %s", exc)
    if is_artist_search and discography_albums:
        combined_albums = local_hits + discography_albums
    else:
        # General/Album title search
        search_albums = deezer_api.search_albums(q, limit=limit)
        for alb in search_albums:
            alb["category"] = _normalize_category(alb.get("record_type") or "", alb.get("title") or "")
        combined_albums = local_hits + discography_albums + search_albums
    # If no albums found but songs/remixes were found, synthesize cards so the releases section is not blank
    if not combined_albums and search_tracks_list:
        for t in search_tracks_list:
            combined_albums.append({
                "id": str(t.get("id")),
                "video_id": t.get("video_id") or "",
                "title": t.get("title") or "Unknown Title",
                "artist": t.get("artist") or "YouTube",
                "cover": t.get("cover") or "/placeholder-cover.svg",
                "year": str(t.get("year") or t.get("release_date") or "")[:4],
                "category": "Singles & Remixes",
                "record_type": "single",
                "tracks_count": 1,
                "preview": t.get("preview") or "",
                "duration": t.get("duration") or 0,
                "source": t.get("source", "youtube"),
            })
    # Build category counts and ordering
    category_counts = {}
    for alb in combined_albums:
        cat = alb.get("category") or "Studio Albums"
        category_counts[cat] = category_counts.get(cat, 0) + 1
    desired_order = ["Local Library", "Studio Albums", "Collaborative / Duets", "Mixtapes & Street", "EPs", "Singles", "Singles & Remixes", "Live Albums", "Compilations", "Remixes", "Soundtracks", "Other"]
    sorted_categories = [c for c in desired_order if c in category_counts]
    for c in category_counts:
        if c not in sorted_categories:
            sorted_categories.append(c)
    prio_map = {c: idx for idx, c in enumerate(desired_order)}
    def _album_sort_key(a):
        cat = a.get("category") or "Studio Albums"
        prio = prio_map.get(cat, 99)
        yr = 0
        try:
            yr = int(str(a.get("year") or a.get("release_date") or "")[:4])
        except Exception:
            yr = 0
        return (prio, -yr)
    combined_albums.sort(key=_album_sort_key)
    final_albums = combined_albums if is_artist_search else combined_albums[:limit]
    # COMPREHENSIVE SEARCH & DISCOVERY TELEMETRY LOGGING
    _search_log.info("=" * 76)
    _search_log.info("[SEARCH QUERY] '%s' (limit requested: %d)", q, limit)
    _search_log.info("-" * 76)
    if artists:
        matched_str = " | ".join(f"{a['name']} (Fans: {a.get('fans', 0):,}, ID: {a['id']})" for a in artists[:5])
        _search_log.info("[Matched Artists (%d)]: %s", len(artists), matched_str)
    if is_artist_search and target_artist_name:
        _search_log.info(
            "[Detection Mode] Artist Discography Match: '%s' -> Consolidated under Master Release Groups",
            target_artist_name
        )
    _search_log.info(
        "[Results Breakdown] Returning %d releases across %d categories: %s",
        len(final_albums), len(sorted_categories),
        ", ".join(f"{c}: {category_counts[c]}" for c in sorted_categories)
    )
    for idx, a in enumerate(final_albums, 1):
        cat = a.get("category") or "Studio Albums"
        art = a.get("artist") or "Unknown Artist"
        tit = a.get("title") or "Untitled"
        yr = a.get("year") or a.get("release_date") or "----"
        aid = a.get("id") or "N/A"
        eds = len(a.get("editions") or [])
        _search_log.info("  #%02d [%s] %s - %s (%s) [Editions: %d, ID: %s]", idx, cat, art, tit, str(yr)[:4], eds, aid)
    _search_log.info("=" * 76 + "\n")
    return {
        "artists": artists,
        "related_artists": related_artists,
        "artist_hero": artist_hero,
        "tracks": search_tracks_list,
        "albums": final_albums,
        "categories": sorted_categories,
        "counts": category_counts,
        "total": len(combined_albums)
    }
def get_artist_albums(artist_id: str, artist_name: str = "", limit: int = 100) -> dict:
    """Fetch complete verified discography consolidated under Master Release Groups with related artists."""
    clean_id = str(artist_id or "").strip()
    clean_name = (artist_name or "").strip()
    if not clean_name and clean_id and not clean_id.isdigit():
        clean_name = clean_id
        clean_id = ""

    related_artists = []
    artist_hero = None
    if clean_id:
        try:
            related_artists = deezer_api.get_related_artists(clean_id, limit=15)
        except Exception:
            pass
        try:
            top_tracks = deezer_api.get_artist_top_tracks(clean_id, limit=5)
            art_info = deezer_api.fetch_json(f"https://api.deezer.com/artist/{clean_id}", cache_ttl=3600) or {}
            artist_hero = {
                "id": clean_id,
                "name": art_info.get("name") or clean_name,
                "picture": art_info.get("picture_xl") or art_info.get("picture_big") or art_info.get("picture_medium") or "",
                "fans": art_info.get("nb_fan", 0),
                "top_tracks": top_tracks
            }
            if not clean_name:
                clean_name = artist_hero["name"]
        except Exception:
            pass
    elif clean_name and not clean_id:
        try:
            found_art = deezer_api.search_artists(clean_name, limit=1)
            if found_art:
                clean_id = str(found_art[0].get("id") or "")
                clean_name = found_art[0].get("name") or clean_name
        except Exception:
            pass

    mb_map = {}
    mb_categorized = None
    if clean_name:
        try:
            mb_categorized = musicbrainz_api.get_artist_categorized_discography(clean_name, limit=limit)
            if mb_categorized and mb_categorized.get("albums"):
                mb_map = build_mb_map(mb_categorized["albums"])
        except Exception:
            pass
    raw_dz = deezer_api.get_artist_discography(clean_id, limit=limit * 2)

    # Build Deezer & iTunes in-memory lookup maps in ONE single batch each
    def _is_better_album_match(new_a, existing_a, target_norm=""):
        if not existing_a: return True
        rec_rank = {"album": 3, "ep": 2, "single": 1}
        new_rank = rec_rank.get((new_a.get("record_type") or "").lower(), 2)
        old_rank = rec_rank.get((existing_a.get("record_type") or "").lower(), 2)
        if new_rank != old_rank: return new_rank > old_rank
        new_tit, old_tit = (new_a.get("title") or "").strip().lower(), (existing_a.get("title") or "").strip().lower()
        if ("remix" in old_tit) != ("remix" in new_tit): return "remix" not in new_tit
        if target_norm:
            if new_tit == target_norm and old_tit != target_norm: return True
            if old_tit == target_norm and new_tit != target_norm: return False
        new_tc = int(new_a.get("tracks_count") or new_a.get("nb_tracks") or 0)
        old_tc = int(existing_a.get("tracks_count") or existing_a.get("nb_tracks") or 0)
        if new_tc > 0 and old_tc > 0 and new_tc != old_tc: return new_tc > old_tc
        return False

    dz_match_map = {}
    for a in (raw_dz or []):
        raw_t = a.get("title", "")
        norm_t = clean_master_title(raw_t).lower()
        if norm_t and _is_better_album_match(a, dz_match_map.get(norm_t), target_norm=norm_t):
            dz_match_map[norm_t] = a
        lk = _clean_for_lookup(raw_t)
        if lk and _is_better_album_match(a, dz_match_map.get(lk), target_norm=norm_t):
            dz_match_map[lk] = a

    it_match_map = {}
    if clean_name:
        try:
            it_batch = itunes_api.search_artist_albums(clean_name, limit=100)
            for ia in (it_batch or []):
                raw_it = ia.get("title", "")
                norm_it = clean_master_title(raw_it).lower()
                if norm_it and _is_better_album_match(ia, it_match_map.get(norm_it), target_norm=norm_it):
                    it_match_map[norm_it] = ia
                lk_it = _clean_for_lookup(raw_it)
                if lk_it and _is_better_album_match(ia, it_match_map.get(lk_it), target_norm=norm_it):
                    it_match_map[lk_it] = ia
        except Exception:
            pass

    # Helper: fast in-memory resolver (0 external HTTP calls in loop to prevent rate limiting)
    def _find_catalog_match(norm_title: str, raw_title: str = ""):
        if not norm_title and not raw_title:
            return None, None
        lk = _clean_for_lookup(raw_title or norm_title)
        # 1. Exact match by clean title or alphanumeric lookup key
        if norm_title in dz_match_map:
            return dz_match_map[norm_title], "deezer"
        if lk and lk in dz_match_map:
            return dz_match_map[lk], "deezer"
        if norm_title in it_match_map:
            return it_match_map[norm_title], "itunes"
        if lk and lk in it_match_map:
            return it_match_map[lk], "itunes"
        # 2. Fuzzy substring match in pre-fetched batch
        for k, v in dz_match_map.items():
            if len(k) >= 4 and (k in norm_title or norm_title in k or (lk and len(lk) >= 4 and (k in lk or lk in k))):
                return v, "deezer"
        for k, v in it_match_map.items():
            if len(k) >= 4 and (k in norm_title or norm_title in k or (lk and len(lk) >= 4 and (k in lk or lk in k))):
                return v, "itunes"
        return None, None

    # MUSICBRAINZ PRIMARY: Use MusicBrainz as the canonical foundation for the discography
    if mb_categorized and mb_categorized.get("albums"):
        mb_primary_list = []
        for mb_alb in mb_categorized["albums"]:
            raw_t = mb_alb.get("title", "")
            norm_t = clean_master_title(raw_t).lower()
            matched, source = _find_catalog_match(norm_t, raw_t)

            alb_id = matched.get("id") if matched else f"mb_{mb_alb.get('id') or norm_t}"
            cover = (matched.get("cover") if matched else "") or mb_alb.get("cover") or ""

            # Never allow raw unverified coverartarchive URLs that 404
            if cover and "coverartarchive.org" in cover:
                cover = ""

            # Quick search fallback if a studio album still lacks high-res cover
            if not cover and mb_alb.get("category") == "Studio Albums" and clean_name:
                try:
                    alb_hits = deezer_api.search_albums(f"{raw_t} {clean_name}", limit=1)
                    if alb_hits:
                        hit = alb_hits[0]
                        cover = hit.get("cover") or hit.get("cover_medium") or ""
                        if not matched and hit.get("id"):
                            alb_id = hit["id"]
                except Exception:
                    pass

            yr_str = str(mb_alb.get("year") or "")[:4]
            mb_primary_list.append({
                "id": str(alb_id),
                "title": raw_t,
                "artist": clean_name,
                "artist_id": clean_id,
                "year": yr_str,
                "release_date": yr_str,
                "full_release_date": yr_str,
                "cover": cover,
                "category": mb_alb.get("category") or "Studio Albums",
                "record_type": mb_alb.get("record_type") or "album",
                "tracks_count": mb_alb.get("track_count") or (matched.get("tracks_count") if matched else 10),
                "source": "MusicBrainz Canonical"
            })

        seen_ids = {str(a.get("id")) for a in mb_primary_list if a.get("id")}
        seen_tits = {clean_master_title(a.get("title", "")).lower() for a in mb_primary_list}
        for da in (raw_dz or []):
            did = str(da.get("id") or "")
            dtit = clean_master_title(da.get("title", "")).lower()
            if did in seen_ids or dtit in seen_tits: continue
            seen_ids.add(did); seen_tits.add(dtit)
            yr = str(da.get("release_date") or da.get("year") or "")[:4]
            mb_primary_list.append({
                "id": did, "title": da.get("title", "Unknown"), "artist": clean_name or da.get("artist", ""),
                "artist_id": clean_id, "year": yr, "release_date": yr, "full_release_date": yr,
                "cover": da.get("cover") or da.get("cover_medium") or "",
                "category": _classify_album_with_taxonomy(da, mb_map, target_artist=clean_name),
                "record_type": da.get("record_type") or "album",
                "tracks_count": da.get("tracks_count") or da.get("nb_tracks") or 1,
                "source": "Deezer Official"
            })
        consolidated = consolidate_master_release_groups(mb_primary_list, mb_map=mb_map)
    else:
        # Fallback to Deezer if MusicBrainz is unreachable
        filtered_dz = []
        for alb in raw_dz:
            alb_art_id = str(alb.get("artist_id") or "")
            if alb_art_id and alb_art_id != clean_id:
                continue
            if clean_name:
                alb["artist"] = clean_name
            alb["category"] = _classify_album_with_taxonomy(alb, mb_map, target_artist=clean_name)
            filtered_dz.append(alb)
        consolidated = consolidate_master_release_groups(filtered_dz, mb_map=mb_map)
    category_counts = {}
    for alb in consolidated:
        cat = alb.get("category") or "Studio Albums"
        category_counts[cat] = category_counts.get(cat, 0) + 1
    desired_order = ["Local Library", "Studio Albums", "Collaborative / Duets", "Mixtapes & Street", "EPs", "Singles", "Live Albums", "Compilations", "Remixes", "Soundtracks", "Other"]
    sorted_categories = [c for c in desired_order if c in category_counts]
    for c in category_counts:
        if c not in sorted_categories:
            sorted_categories.append(c)
    prio_map = {c: idx for idx, c in enumerate(desired_order)}
    def _artist_album_sort_key(a):
        cat = a.get("category") or "Studio Albums"
        prio = prio_map.get(cat, 99)
        yr = 0
        try:
            yr = int(str(a.get("year") or a.get("release_date") or "")[:4])
        except Exception:
            yr = 0
        return (prio, -yr)
    consolidated.sort(key=_artist_album_sort_key)
    return {
        "albums": consolidated,
        "related_artists": related_artists,
        "artist_hero": artist_hero,
        "categories": sorted_categories,
        "counts": category_counts,
        "total": len(consolidated)
    }
def get_related_artists(artist_id: str, limit: int = 15) -> list[dict]:
    """Fetch live similar/related artists."""
    return deezer_api.get_related_artists(artist_id=artist_id, limit=limit)
def get_new_releases(limit: int = 100) -> dict:
    """Fetch live new releases this week."""
    from . import releases
    return releases.get_new_releases(limit=limit)
def resolve_album_canonical(
    deezer_album_id: str = "",
    upc: str = "",
    fallback_artist: str = "",
    fallback_title: str = ""
) -> dict:

    """Execute the multi-service deterministic resolution pipeline:
    1. Local SQLite catalog check (<0.2ms)
    2. Deezer UPC / Barcode extraction
    3. iTunes Asset Bridge via UPC (1400x1400 uncompressed artwork & collectionId)
    4. MusicBrainz Deterministic Release-Group Resolution via Barcode
    5. Fallback paths (Track ISRC or normalized title match)
    6. Persist to local SQLite WAL album_catalog
    """
    dz_id = str(deezer_album_id or "").strip()
    clean_upc = str(upc or "").strip()
    # Step 1: Sub-millisecond Local SQLite Check
    if clean_upc:
        cached = store.get_catalog_by_upc(clean_upc)
        if cached:
            return cached
    if dz_id:
        cached = store.get_catalog_by_deezer_id(dz_id)
        if cached:
            return cached
    # If UPC not provided, fetch Deezer album payload to extract UPC & track 1 ISRC
    track_1_isrc = ""
    deezer_cover = ""
    deezer_record_type = ""
    if dz_id and not clean_upc:
        try:
            dz_details = deezer_api.get_album_details(dz_id)
            if dz_details and "error" not in dz_details:
                clean_upc = str(dz_details.get("upc") or "").strip()
                deezer_cover = dz_details.get("cover") or ""
                deezer_record_type = dz_details.get("record_type") or ""
                if not fallback_artist:
                    fallback_artist = dz_details.get("artist") or ""
                if not fallback_title:
                    fallback_title = dz_details.get("title") or ""
                tracks = dz_details.get("tracks") or []
                if tracks:
                    track_1_isrc = tracks[0].get("isrc") or ""
        except Exception as exc:
            _log.debug("Deezer payload fetch error for %s: %s", dz_id, exc)
    itunes_data = None
    mb_data = None
    # Step 2: iTunes Asset Bridge via UPC
    if clean_upc:
        try:
            itunes_data = itunes_api.lookup_by_upc(clean_upc)
        except Exception as exc:
            _log.debug("iTunes UPC bridge error for %s: %s", clean_upc, exc)
    # Step 3: MusicBrainz Deterministic Resolution via Barcode
    if clean_upc:
        try:
            mb_data = musicbrainz_api.resolve_by_barcode(clean_upc)
        except Exception as exc:
            _log.debug("MusicBrainz barcode resolution error for %s: %s", clean_upc, exc)
    # Step 4: Fallback Paths (Track ISRC)
    if not mb_data and track_1_isrc:
        try:
            mb_data = musicbrainz_api.resolve_by_isrc(track_1_isrc)
        except Exception as exc:
            _log.debug("MusicBrainz ISRC resolution fallback error: %s", exc)
    # Determine Canonical Values
    # Hierarchy: MusicBrainz (Taxonomy Authority) > Strict Taxonomy Normalizer
    final_category = _classify_album_with_taxonomy(
        {
            "title": fallback_title,
            "record_type": deezer_record_type,
            "tracks_count": 0,
        },
        mb_map={clean_master_title(fallback_title).lower(): mb_data} if mb_data else None
    )
    if mb_data and mb_data.get("category"):
        final_category = mb_data["category"]
    final_artist = (
        (itunes_data.get("artist") if itunes_data else None)
        or (mb_data.get("artist") if mb_data else None)
        or fallback_artist
        or "Unknown Artist"
    )
    final_title = (
        (itunes_data.get("title") if itunes_data else None)
        or (mb_data.get("title") if mb_data else None)
        or fallback_title
        or "Unknown Album"
    )
    itunes_artwork = (itunes_data.get("artwork_url") if itunes_data else "") or ""
    itunes_id = (itunes_data.get("itunes_id") if itunes_data else "") or ""
    mb_rg_id = (mb_data.get("mb_release_group_id") if mb_data else "") or ""
    entry = {
        "upc": clean_upc or (f"dz_{dz_id}" if dz_id else ""),
        "deezer_id": dz_id,
        "itunes_id": itunes_id,
        "mb_release_group_id": mb_rg_id,
        "artist": final_artist,
        "title": final_title,
        "category": final_category,
        "deezer_cover": deezer_cover,
        "itunes_artwork": itunes_artwork,
    }
    if entry["upc"]:
        try:
            store.save_catalog_entry(entry)
        except Exception as exc:
            _log.debug("Failed to persist catalog entry for %s: %s", entry["upc"], exc)
    return entry
def is_skit_track(title: str) -> bool:
    """Detect spoken dialogue skits and non-music interludes."""
    t = (title or "").strip().lower()
    if not t:
        return False
    skit_patterns = [
        r"[\(\[\{]\s*skit(?:\s*\d+)?\s*[\)\]\}]",  # (Skit), [Skit 1]
        r"\bskit\s*#?\d+\b",                       # Skit 1, Skit #2
        r"[-–—:]\s*skit\b",                        # - Skit
        r"\bskit\s*[-–—:]",                        # Skit -
        r"^skit\b",                                # Skit
        r"\bspoken\s*word\b"                       # Spoken Word
    ]
    return any(re.search(p, t) for p in skit_patterns)
def get_album_details(album_id: str) -> dict:
    """Fetch verified album tracklist with 30s preview streams, uncompressed 1400x1400 artwork,
    skit filtering, tracklist deduplication, and edition selector support.
    """
    aid = str(album_id or "").strip()
    if aid.startswith("local_"):
        pass
        details = None
        if details:
            return details
    elif aid.startswith("apple:"):
        from . import releases
        details = releases.get_apple_album_details(aid)
    elif aid.startswith("it_"):
        details = itunes_api.lookup_album_tracks(aid)
    elif aid.startswith("mb_"):
        details = musicbrainz_api.get_release_group_details(aid)
    elif aid.startswith("yt_"):
        vid = aid[3:]
        from . import stream_service
        yt_meta = stream_service.get_video_metadata(vid) or {}
        yt_title = yt_meta.get("title") or "YouTube Single"
        yt_artist = yt_meta.get("artist") or "YouTube"
        yt_dur = int(yt_meta.get("duration") or 0)
        yt_year = str(yt_meta.get("release_year") or yt_meta.get("upload_date") or "")[:4]
        details = {
            "id": aid,
            "title": yt_title,
            "artist": yt_artist,
            "cover": yt_meta.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            "year": yt_year if yt_year.isdigit() else "",
            "category": "Singles & Remixes",
            "record_type": "single",
            "tracks": [{
                "id": aid,
                "video_id": vid,
                "title": yt_title,
                "artist": yt_artist,
                "album": "YouTube Audio",
                "duration": yt_dur,
                "track_num": 1,
                "disc_num": 1,
            }]
        }
    elif "-" in aid or aid.startswith("tm_") or not aid.isdigit():
        from . import timemachine_service
        lm = timemachine_service.get_landmark_album_details(aid)
        details = lm if lm else deezer_api.get_album_details(aid)
    else:
        details = deezer_api.get_album_details(aid)
    if not details or "error" in details:
        return details
    # 1. Deduplicate only truly identical tracks (same ID or exact position & duration)
    tracks = details.get("tracks") or []
    seen_track_keys = set()
    deduped_tracks = []
    for t in tracks:
        tid = str(t.get("id") or "")
        tnum = t.get("track_num")
        dnum = t.get("disc_num", 1)
        raw_t = (t.get("title") or "").strip().lower()
        dur = t.get("duration", 0)
        key = tid if tid else f"{dnum}:{tnum}:{raw_t}:{dur}"
        if key in seen_track_keys:
            continue
        seen_track_keys.add(key)
        deduped_tracks.append(t)
    # 2. Filter out spoken dialogue skits, preserving comedy/spoken-word albums
    music_tracks = [t for t in deduped_tracks if not is_skit_track(t.get("title") or "")]
    final_tracks = music_tracks if music_tracks else deduped_tracks
    # 3. Cleanly re-sequence track numbers 1..N
    for i, t in enumerate(final_tracks, 1):
        t["track_num"] = i
    # Identify Hit Single and Essential Deep Cut
    if final_tracks and len(final_tracks) >= 2:
        ranked = sorted(final_tracks, key=lambda x: x.get("rank") or 0, reverse=True)
        top_track = ranked[0]
        if (top_track.get("rank") or 0) > 0:
            top_track["is_hit"] = True
        else:
            final_tracks[0]["is_hit"] = True
        non_hit_ranked = [t for t in ranked if not t.get("is_hit")]
        deep_candidates = [t for t in non_hit_ranked if (t.get("track_num") or 1) >= 4]
        if not deep_candidates:
            deep_candidates = [t for t in non_hit_ranked if (t.get("track_num") or 1) >= 2]
        if deep_candidates:
            deep_candidates[0]["is_deep_cut"] = True
    details["tracks"] = final_tracks
    details["tracks_count"] = len(final_tracks)
    # Attach sibling editions for the modal dropdown selector
    artist_id = str(details.get("artist_id") or "")
    if artist_id:
        editions = get_album_editions(artist_id, aid, details.get("title", ""))
        if editions:
            details["editions"] = editions
    # Check cache first for instant sub-millisecond lookup
    cached = store.get_catalog_by_deezer_id(aid)
    if cached:
        if cached.get("itunes_artwork"):
            details["cover"] = cached["itunes_artwork"]
        if cached.get("category"):
            details["category"] = cached["category"]
        if cached.get("itunes_id"):
            details["itunes_id"] = cached["itunes_id"]
        if cached.get("mb_release_group_id"):
            details["mb_release_group_id"] = cached["mb_release_group_id"]
        if cached.get("title"):
            details["title"] = cached["title"]
    else:
        # Non-blocking background canonical resolution so tracklist loads in 0.15s with zero delay!
        upc = str(details.get("upc") or "").strip()
        def _bg_resolve():
            try:
                resolve_album_canonical(
                    deezer_album_id=aid,
                    upc=upc,
                    fallback_artist=details.get("artist", ""),
                    fallback_title=details.get("title", "")
                )
            except Exception:
                pass
        import threading
        threading.Thread(target=_bg_resolve, daemon=True).start()
    # Attach dynamic Sonic DNA sister albums
    try:
        details["sister_albums"] = get_sonic_sister_albums(details)
    except Exception as e:
        _log.debug("Failed to attach sister albums: %s", e)
        details["sister_albums"] = []
    return details
def get_sonic_sister_albums(details: dict) -> list[dict]:
    """Dynamically resolve 3 Sonic DNA Sister Albums based on artist, genre, era, and lineage."""
    if not details:
        return []
    aid = str(details.get("id") or "")
    artist = details.get("artist") or ""
    artist_id = str(details.get("artist_id") or "")
    genre = details.get("genre") or "Rock"
    sister_records = []
    seen_ids = {aid}
    # 1. Live related artists from Deezer
    if artist_id:
        try:
            rel_artists = deezer_api.get_related_artists(artist_id, limit=6)
            for ra in rel_artists:
                if len(sister_records) >= 3:
                    break
                ra_id = str(ra.get("id") or "")
                ra_name = ra.get("name") or ""
                disc = deezer_api.get_artist_discography(ra_id, limit=2)
                for alb in (disc or []):
                    salb_id = str(alb.get("id") or "")
                    if salb_id and salb_id not in seen_ids:
                        seen_ids.add(salb_id)
                        sister_records.append({"id": salb_id, "title": alb.get("title", ""), "artist": ra_name, "cover": alb.get("cover") or ra.get("picture", ""), "year": alb.get("year", ""), "genre": genre, "match_reason": f"Shared sonic DNA & lineage with {artist}"})
                        break
        except Exception as e:
            _log.debug("Related artist sister album error: %s", e)
    # 2. Curated landmark / timemachine albums in matching/adjacent genre
    if len(sister_records) < 3:
        try:
            from . import timemachine_service
            all_landmarks = []
            for yr_albs in timemachine_service.TIMEMACHINE_LANDMARKS.values():
                all_landmarks.extend(yr_albs)
            genre_lower = genre.lower()
            matched_landmarks = [
                a for a in all_landmarks
                if a.get("id") not in seen_ids and (
                    any(w in a.get("genre", "").lower() for w in genre_lower.split() if len(w) > 3) or
                    any(w in genre_lower for w in a.get("genre", "").lower().split() if len(w) > 3)
                )
            ]
            for a in all_landmarks:
                if a.get("id") not in seen_ids and a not in matched_landmarks:
                    matched_landmarks.append(a)
            for alb in matched_landmarks:
                if len(sister_records) >= 3:
                    break
                salb_id = str(alb.get("id") or "")
                if salb_id not in seen_ids:
                    seen_ids.add(salb_id)
                    sister_records.append({"id": salb_id, "title": alb.get("title", ""), "artist": alb.get("artist", ""), "cover": alb.get("cover", ""), "year": alb.get("year", ""), "genre": alb.get("genre", genre), "match_reason": alb.get("desc") or f"Iconic companion in {alb.get('genre', genre)}"})
        except Exception as e:
            _log.debug("Fallback landmark sister album error: %s", e)
    return sister_records[:3]
_PRESERVED_DUO_BANDS = {
    "ac/dc", "hall & oates", "daryl hall & john oates", "simon & garfunkel",
    "earth, wind & fire", "florence + the machine", "florence and the machine",
    "mumford & sons", "guns n' roses", "brooks & dunn", "tegan and sara",
    "coheed and cambria", "crosby, stills, nash & young", "crosby, stills & nash",
    "emerson, lake & palmer", "peter, paul and mary", "kool & the gang",
    "kc and the sunshine band", "sly and the family stone", "echo & the bunnymen",
    "belle and sebastian", "angus & julia stone", "above & beyond", "chase & status"
}

def split_collab_artists(artist_str: str) -> list[str]:
    """Split composite collaboration strings ('Calvin Harris, Ellie Goulding', 'Daft Punk feat. Pharrell')
    into individual artists while preserving band names that contain punctuation."""
    raw = (artist_str or "").strip()
    if not raw:
        return []
    if raw.lower() in _PRESERVED_DUO_BANDS:
        return [raw]
    parts = re.split(
        r"\s+(?:feat\.?|ft\.?|featuring|with|vs\.?|x)\s+|\s*,\s*|\s*&\s*|\s*;\s*|\s*/\s*",
        raw,
        flags=re.IGNORECASE
    )
    cleaned = [p.strip() for p in parts if p and len(p.strip()) > 1]
    return cleaned if cleaned else [raw]

def apply_artist_separation(tracks: list[dict], min_distance: int = 4, exclude_artists: list[str] = None, max_per_artist: int = 2) -> list[dict]:
    """Ensure no two songs by the same artist (including featured/collab credits) appear consecutively
    or within `min_distance` tracks of each other, penalize recently played artists, and cap per artist."""
    if not tracks:
        return []
    import random
    from collections import defaultdict
    recent_artists = set()
    for a in (exclude_artists or []):
        for sub_a in split_collab_artists(a):
            recent_artists.add(sub_a.lower().strip())
    by_artist = defaultdict(list)
    for t in tracks:
        credits = [c.lower().strip() for c in split_collab_artists(t.get("artist") or "")]
        art_key = credits[0] if credits else (t.get("artist") or "").lower().strip()
        if len(by_artist[art_key]) < max_per_artist:
            by_artist[art_key].append(t)
    ordered = []
    last_artist_pos = {}
    remaining_count = sum(len(v) for v in by_artist.values())
    max_loops = remaining_count * 8
    loop = 0
    while remaining_count > 0 and loop < max_loops:
        loop += 1
        best_art = None
        best_score = -999999
        current_idx = len(ordered)
        for art, trks in list(by_artist.items()):
            if not trks:
                continue
            cand_credits = [c.lower().strip() for c in split_collab_artists(trks[0].get("artist") or art)]
            min_dist_seen = min((current_idx - last_artist_pos.get(c, -999)) for c in cand_credits)
            # Hard constraint: NEVER pick the same primary or featured artist consecutively (dist <= 1)
            if min_dist_seen <= 1 and current_idx > 0:
                continue
            score = 0
            if min_dist_seen < min_distance:
                score -= (min_distance - min_dist_seen) * 100
            else:
                score += min_dist_seen * 10
            if any(c in recent_artists for c in cand_credits):
                score -= 600
            score += random.uniform(0, 15)
            if score > best_score:
                best_score = score
                best_art = art
        if best_art and by_artist[best_art]:
            chosen_track = by_artist[best_art].pop(0)
            ordered.append(chosen_track)
            for c in split_collab_artists(chosen_track.get("artist") or best_art):
                last_artist_pos[c.lower().strip()] = current_idx
            remaining_count -= 1
        else:
            break
    return ordered
def get_autoplay_dj_mix(artist_name: str = "", artist_id: str = "", exclude_ids: list[str] | set[str] = None, exclude_artists: list[str] = None) -> dict:
    """Generate a dynamic, multi-cloud vibe mix from diverse artists with strict anti-repeat and artist separation.
    Zero hardcoded tracks, zero hardcoded playlists: 100% dynamically fetched live across Deezer, YouTube Music, and Apple Music.
    """
    import random
    pool = []
    vibe_label = (artist_name or "").strip()
    aid = str(artist_id or "").strip()
    aname = str(artist_name or "").strip()
    collab_parts = split_collab_artists(aname)
    # 1. Dynamically resolve artist details from Deezer (splitting composite collaborations so we never hit a 0-fan stub)
    if not aid and aname:
        try:
            for cand_name in ([collab_parts[0]] if len(collab_parts) > 1 else [aname]) + collab_parts[1:]:
                artists = deezer_api.search_artists(cand_name, limit=4)
                valid_artists = [a for a in (artists or []) if int(a.get("fans") or 0) >= 500] or artists
                if valid_artists:
                    aid = str(valid_artists[0].get("id") or "")
                    vibe_label = valid_artists[0].get("name", cand_name)
                    aname = vibe_label
                    break
        except Exception:
            pass
    # 2. CLOUD SOURCE A: Deezer Live Artist Radio & Related Artists Graph
    if aid:
        try:
            radio = deezer_api.get_artist_radio(aid, limit=30)
            if radio:
                pool.extend(radio)
        except Exception:
            pass
        try:
            related = deezer_api.get_related_artists(aid, limit=20)
            if related:
                sample_rel = random.sample(related, min(10, len(related)))
                for rel in sample_rel:
                    rel_id = rel.get("id")
                    if rel_id:
                        rel_tracks = deezer_api.get_artist_top_tracks(rel_id, limit=3)
                        if rel_tracks:
                            pool.extend(rel_tracks)
        except Exception:
            pass
    # 3. CLOUD SOURCE B: YouTube Music Live Recommendation Feed
    if aname:
        try:
            from . import stream_service
            yt_songs = stream_service._search_ytmusic_songs(f"{aname} songs", filter_songs=True)
            for item in (yt_songs or [])[:15]:
                vid = item.get("id")
                t_title = (item.get("title") or "").strip()
                t_artist = item.get("channel") or (item.get("artists")[0] if item.get("artists") else aname)
                t_dur = item.get("duration_seconds") or 0
                t_thumb = item.get("thumbnail") or ""
                t_alb = item.get("album") or ""
                if vid and t_title and t_artist:
                    pool.append({"id": f"yt_{vid}", "title": t_title, "artist": t_artist, "album": t_alb, "duration": t_dur, "cover": t_thumb, "provider": "youtube"})
        except Exception:
            pass
    # 4. If an artist seed is active and pool needs more tracks, pull deeper related peers (NOT generic pop charts)
    if (aname or aid) and len(pool) < 30:
        try:
            if aname:
                from . import stream_service
                yt_mix = stream_service._search_ytmusic_songs(f"{aname} mix", filter_songs=True)
                for item in (yt_mix or [])[:15]:
                    vid = item.get("id")
                    t_title = (item.get("title") or "").strip()
                    t_artist = item.get("channel") or (item.get("artists")[0] if item.get("artists") else aname)
                    if vid and t_title and t_artist:
                        pool.append({"id": f"yt_{vid}", "title": t_title, "artist": t_artist, "album": item.get("album") or "", "duration": item.get("duration_seconds") or 0, "cover": item.get("thumbnail") or "", "provider": "youtube"})
        except Exception:
            pass
    # 5. Generic Charts Fallback (ONLY when NO artist seed is active - Surprise Me / Global Mode)
    if not aname and not aid and len(pool) < 25:
        try:
            from . import official_charts
            uk_chart = official_charts.get_live_official_charts("gb", limit=25)
            if uk_chart and uk_chart.get("tracks"):
                pool.extend(uk_chart["tracks"])
            us_chart = official_charts.get_live_official_charts("us", limit=25)
            if us_chart and us_chart.get("tracks"):
                pool.extend(us_chart["tracks"])
            if not vibe_label:
                vibe_label = "Live Multi-Cloud Countdown"
        except Exception:
            pass
        if len(pool) < 20:
            try:
                chart_tracks = deezer_api.get_chart_tracks(limit=40)
                if chart_tracks:
                    pool.extend(chart_tracks)
                if not vibe_label:
                    vibe_label = "Live Global Trending Hits"
            except Exception:
                pass
    # Normalized exclusion set (IDs and artist:::title keys)
    ex_set = set()
    if exclude_ids:
        for x in exclude_ids:
            if x:
                ex_set.add(str(x).lower().strip())
    # Deduplicate by artist + title and filter out excluded tracks
    seen = set()
    unique_tracks = []
    for t in pool:
        tid = str(t.get("id") or "").lower().strip()
        art = (t.get("artist") or "").lower().strip()
        title = (t.get("title") or "").lower().strip()
        k = f"{art}:::{title}"
        if not tid or not title:
            continue
        if tid in ex_set or k in ex_set:
            continue
        if k not in seen:
            seen.add(k)
            unique_tracks.append(t)
    # Apply professional Artist Separation to guarantee variety & spacing
    scheduled_tracks = apply_artist_separation(unique_tracks, min_distance=4, exclude_artists=exclude_artists, max_per_artist=2)
    return {
        "vibe": vibe_label or "Live Multi-Cloud Vibe",
        "tracks": scheduled_tracks,
        "count": len(scheduled_tracks)
    }
