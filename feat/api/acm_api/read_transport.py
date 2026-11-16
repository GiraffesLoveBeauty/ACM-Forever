"""Explicit public validators and opt-in compression; never caches private JSON."""

import gzip
import hashlib

from quart import request


async def optimize_response(response):
    public = request.path == "/api/mobile/v1/capabilities"
    if public and request.method == "GET" and response.status_code == 200:
        # Authorization/error handlers have already run before after_request.
        body = await response.get_data()
        tag = hashlib.sha256(body).hexdigest()
        response.headers["ETag"] = f'"{tag}"'
        response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
        if request.if_none_match.star_tag or request.if_none_match.contains_weak(tag):
            response.status_code = 304
            response.set_data(b"")
    # Dynamic authenticated bodies, cookies and secrets must not be compressed together.
    # Restrict to the already-public Wiki JSON and the public capabilities document.
    safe_public = public or (request.path.startswith("/api/wiki/") and response.headers.get("Cache-Control", "").startswith("public,"))
    if safe_public and request.method == "GET" and response.status_code == 200 and response.mimetype == "application/json" and "Content-Encoding" not in response.headers and not response.headers.getlist("Set-Cookie"):
        response.vary.add("Accept-Encoding")
        if request.accept_encodings["gzip"] > 0:
            body = await response.get_data()
            if len(body) >= 1024:
                packed = gzip.compress(body, compresslevel=5, mtime=0)
                if len(packed) < len(body):
                    response.set_data(packed)
                    response.headers["Content-Encoding"] = "gzip"
                    # Weak tags validate the same representation across encodings.
                    if response.headers.get("ETag", "").startswith('"'):
                        response.headers["ETag"] = "W/" + response.headers["ETag"]
    return response
