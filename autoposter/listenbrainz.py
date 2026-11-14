"""ListenBrainz statistics API wrapper.

We use the "month" range, which is ListenBrainz's *last completed calendar
month* — NOT a rolling 30 days. Their stats are fully reimported only on the
1st and 15th of the month and can lag well past that, so __main__ checks the
returned `to` date before posting.

Reading another user's public stats requires no auth token.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .http import HTTPError, request_json

API = "https://api.listenbrainz.org/1"


def get_top_albums(username, *, range_="month", count=5):
    """Return {"albums": [...], "from": datetime|None, "to": datetime|None}.

    Each album is {"album", "artist", "plays", "cover"}.
    """
    # Use the *release-group* stat (an album, not a specific pressing) and
    # over-fetch so we can merge the occasional album split across MBIDs.
    fetch_count = max(count * 5, 25)
    url = (f"{API}/stats/user/{quote(username, safe='')}/release-groups"
           f"?range={quote(range_)}&count={fetch_count}")
    try:
        status, data = request_json(url, headers={"Accept": "application/json"})
    except HTTPError as err:
        if err.status == 404:
            raise RuntimeError(f'ListenBrainz user "{username}" not found') from None
        raise RuntimeError(f"ListenBrainz API error: HTTP {err.status}") from None

    # 204 = the stats exist but there's no data for this window yet.
    if status == 204 or not data:
        return {"albums": [], "from": None, "to": None}

    payload = data.get("payload") or {}
    raw = [{
        "album": r.get("release_group_name") or "Unknown album",
        "artist": r.get("artist_name") or "Unknown artist",
        "plays": r.get("listen_count") or 0,
        "cover": _cover_url(r),
    } for r in payload.get("release_groups") or []]

    def ts(key):
        v = payload.get(key)
        return datetime.fromtimestamp(v, tz=timezone.utc) if v else None

    return {"albums": _dedupe(raw)[:count], "from": ts("from_ts"), "to": ts("to_ts")}


def _dedupe(albums):
    """Merge same album+artist (case-insensitive), summing plays; sort by plays."""
    merged = {}
    for a in albums:
        key = f"{a['album']} {a['artist']}".lower().strip()
        if key in merged:
            merged[key]["plays"] += a["plays"]
            if not merged[key]["cover"] and a["cover"]:
                merged[key]["cover"] = a["cover"]
        else:
            merged[key] = dict(a)
    return sorted(merged.values(), key=lambda a: a["plays"], reverse=True)


def _cover_url(r):
    """Cover Art Archive URL for a release, or None."""
    mbid, caa_id = r.get("caa_release_mbid"), r.get("caa_id")
    if mbid and caa_id is not None:
        return f"https://archive.org/download/mbid-{mbid}/mbid-{mbid}-{caa_id}_thumb500.jpg"
    if r.get("release_mbid"):
        return f"https://coverartarchive.org/release/{r['release_mbid']}/front-500"
    return None


def format_range(start, end):
    """e.g. "Oct 1 – Oct 31". `end` is exclusive, so step back one day."""
    if not start or not end:
        return ""
    fmt = lambda d: f"{d:%b} {d.day}"
    return f"{fmt(start)} – {fmt(end - timedelta(days=1))}"
