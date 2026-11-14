"""Bluesky (AT Protocol) wrapper using plain XRPC calls.

Uses an app password (Bluesky → Settings → App Passwords) and logs in fresh
on each run — at a monthly cadence there's no need to cache the session.
"""

import re
from datetime import datetime, timezone

from .http import request_json

SERVICE = "https://bsky.social"

# Same idea as @atproto/api's RichText.detectFacets, for the two things our
# caption contains: links and hashtags.
_URL_RE = re.compile(r"https?://[^\s<>\"']+[^\s<>\"'.,;:!?)\]]")
_TAG_RE = re.compile(r"(?:^|(?<=\s))#([^\s#\d][^\s#]*)")
_TAG_TRAILING_PUNCT = re.compile(r"[.,;:!?)\]'\"]+$")


def _byte_slice(text, start, end):
    return {
        "byteStart": len(text[:start].encode()),
        "byteEnd": len(text[:end].encode()),
    }


def detect_facets(text):
    facets = []
    for m in _URL_RE.finditer(text):
        facets.append({
            "index": _byte_slice(text, m.start(), m.end()),
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": m.group(0)}],
        })
    for m in _TAG_RE.finditer(text):
        tag = _TAG_TRAILING_PUNCT.sub("", m.group(1))
        if not tag or len(tag) > 64:
            continue
        start = m.start(1) - 1  # include the '#'
        facets.append({
            "index": _byte_slice(text, start, start + 1 + len(tag)),
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag}],
        })
    return facets


def post_to_bluesky(*, identifier, password, text, image=None):
    """Publish a post (optionally with one image). Returns {"uri", "cid"}.

    image: {"data": bytes, "mime", "alt", "width", "height"}
    """
    _, session = request_json(
        f"{SERVICE}/xrpc/com.atproto.server.createSession",
        method="POST", json_body={"identifier": identifier, "password": password},
    )
    # Talk to the account's own PDS if the session tells us where it is.
    pds = SERVICE
    for svc in (session.get("didDoc") or {}).get("service", []):
        if svc.get("id") == "#atproto_pds" and svc.get("serviceEndpoint"):
            pds = svc["serviceEndpoint"].rstrip("/")
    auth = {"Authorization": f"Bearer {session['accessJwt']}"}

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "langs": ["en"],
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    facets = detect_facets(text)
    if facets:
        record["facets"] = facets

    if image:
        _, blob = request_json(
            f"{pds}/xrpc/com.atproto.repo.uploadBlob",
            method="POST", headers={**auth, "Content-Type": image["mime"]},
            data=image["data"], timeout=60,
        )
        record["embed"] = {
            "$type": "app.bsky.embed.images",
            "images": [{
                "image": blob["blob"],
                "alt": image.get("alt") or "",
                "aspectRatio": {"width": image.get("width", 1200),
                                "height": image.get("height", 1200)},
            }],
        }

    _, res = request_json(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        method="POST", headers=auth,
        json_body={"repo": session["did"], "collection": "app.bsky.feed.post",
                   "record": record},
    )
    return {"uri": res["uri"], "cid": res["cid"]}
