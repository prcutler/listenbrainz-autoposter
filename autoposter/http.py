"""Tiny stdlib HTTP helpers, so the only third-party dependency is Pillow."""

import json
import urllib.error
import urllib.request

USER_AGENT = "listenbrainz-autoposter/2.0 (+https://github.com/prcutler/listenbrainz-autoposter)"


class HTTPError(Exception):
    def __init__(self, status, body=""):
        super().__init__(f"HTTP {status} {body}".strip())
        self.status = status
        self.body = body


def request(url, *, method="GET", headers=None, data=None, json_body=None, timeout=30):
    """Return (status, body_bytes). Raises HTTPError for 4xx/5xx."""
    hdrs = {"User-Agent": USER_AGENT, **(headers or {})}
    if json_body is not None:
        data = json.dumps(json_body).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as err:
        body = err.read().decode(errors="replace")[:500]
        raise HTTPError(err.code, body) from None


def request_json(url, **kwargs):
    status, body = request(url, **kwargs)
    return status, (json.loads(body) if body else None)
