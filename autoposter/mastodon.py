"""Mastodon wrapper (plain REST API).

Auth: an access token from your instance → Preferences → Development → New
Application (scopes: write:statuses, write:media). Mastodon auto-linkifies
URLs and hashtags, so there are no facets to build.
"""

import time
import uuid

from .http import HTTPError, request_json


def _multipart(fields, file_field, filename, mime, data):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def post_to_mastodon(*, instance, token, text, image=None):
    """Publish a public status, optionally with one image. Returns {"url", "id"}."""
    base = instance.rstrip("/")
    auth = {"Authorization": f"Bearer {token}"}

    media_ids = []
    if image:
        filename = "top5.jpg" if image["mime"] == "image/jpeg" else "top5.png"
        fields = {"description": image["alt"]} if image.get("alt") else {}
        body, ctype = _multipart(fields, "file", filename, image["mime"], image["data"])
        try:
            status, media = request_json(
                f"{base}/api/v2/media", method="POST",
                headers={**auth, "Content-Type": ctype}, data=body, timeout=60,
            )
        except HTTPError as err:
            raise RuntimeError(f"media upload failed: {err}") from None
        # 202 = accepted but still processing; poll until it's ready.
        if status == 202:
            media = _wait_for_media(base, auth, media["id"])
        media_ids = [media["id"]]

    try:
        _, data = request_json(
            f"{base}/api/v1/statuses", method="POST",
            headers={**auth, "Idempotency-Key": str(uuid.uuid4())},
            json_body={"status": text, "media_ids": media_ids,
                       "language": "en", "visibility": "public"},
        )
    except HTTPError as err:
        raise RuntimeError(f"status post failed: {err}") from None
    return {"url": data["url"], "id": data["id"]}


def _wait_for_media(base, auth, media_id, tries=30, delay=1.0):
    for _ in range(tries):
        time.sleep(delay)
        status, media = request_json(f"{base}/api/v1/media/{media_id}", headers=auth)
        if status == 200:
            return media
        if status != 206:  # 206 = still processing
            raise RuntimeError(f"media processing failed: HTTP {status}")
    raise RuntimeError("media processing timed out")
