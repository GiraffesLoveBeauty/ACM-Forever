"""Administrator-only proxy for APKs kept in unpublished GitHub drafts.

No upstream credentials or signed asset URLs are returned to clients. Public
formal updates remain static GitHub Release assets and do not use this API.
"""
import asyncio
import hashlib
import json
import os
import re
import tempfile
from urllib.parse import urlsplit

import aiohttp
from quart import Blueprint, Response, current_app, jsonify

from .backend_api import admin_required, _login_required_response

android_release_api = Blueprint("android_releases", __name__)
PACKAGE = "com.giraffeslovebeauty.acmforever"
CERTIFICATE = "88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4"
MAX_APK = 150 * 1024 * 1024
MODULES = {"official-themes": "module-official-themes.acmpack", "advanced": "module-advanced.apk",
           "admin": "module-admin.apk", "cat-art": "module-cat-art.acmpack"}
MAX_MODULE = 16 * 1024 * 1024


def file_digest(file):
    digest = hashlib.sha256()
    for block in iter(lambda: file.read(65536), b""):
        digest.update(block)
    return digest


class ReleaseUnavailable(Exception):
    pass


class NoPreview(ReleaseUnavailable):
    """The source is reachable, but there is no unreleased complete preview."""


def validate_manifest(value):
    if (not isinstance(value, dict) or value.get("packageName") != PACKAGE
            or value.get("distribution") != "preview" or type(value.get("schemaVersion")) is not int or value.get("schemaVersion") != 2
            or "apkUrl" in value or "channel" in value or "modulesUrl" in value
            or type(value.get("versionCode")) is not int or not 1 <= value["versionCode"] <= 2100000000
            or not re.fullmatch(r"\d+\.\d+\.\d+", str(value.get("versionName", "")))
            or type(value.get("releaseVersionCode")) is not int or not value["versionCode"] < value["releaseVersionCode"] <= 2100000000
            or type(value.get("previewRevision")) is not int or value["previewRevision"] < 1
            or value.get("previewTag") != f'v{value["versionName"]}-preview.{value["previewRevision"]}'
            or value.get("apkPath") != f'/api/admin/android/releases/{value["previewTag"]}/apk'
            or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("sha256", "")))
            or value.get("signingCertificateSha256") != CERTIFICATE
            or type(value.get("sizeBytes")) is not int or not 0 < value["sizeBytes"] <= MAX_APK
            or type(value.get("minSdk")) is not int or not 26 <= value["minSdk"] <= 10000
            or not isinstance(value.get("notes"), str) or not value["notes"].strip()
            or len(value["notes"].encode("utf-16-le")) // 2 > 8000):
        raise ReleaseUnavailable()
    # Return only the documented client fields, never arbitrary upstream fields.
    keys = ("schemaVersion", "distribution", "packageName", "versionName", "versionCode", "minSdk",
            "apkPath", "sha256", "sizeBytes", "notes", "signingCertificateSha256", "releaseVersionCode", "previewRevision", "previewTag")
    result = {key: value[key] for key in keys}
    if value["releaseVersionCode"] >= 39:
        if value.get("modulesPath") != f'/api/admin/android/releases/{value["previewTag"]}/modules':
            raise ReleaseUnavailable()
        result["modulesPath"] = value["modulesPath"]
    return result


def validate_catalog(catalog, manifest, repository):
    if (not isinstance(catalog, dict) or type(catalog.get("schemaVersion")) is not int or catalog.get("schemaVersion") != 1
            or type(catalog.get("versionCode")) is not int or catalog.get("versionCode") != manifest["versionCode"]
            or catalog.get("versionName") != manifest["versionName"]
            or catalog.get("previewTag") != manifest["previewTag"]
            or not isinstance(catalog.get("modules"), list) or len(catalog["modules"]) != 4):
        raise ReleaseUnavailable()
    rows, seen = [], set()
    for item in catalog["modules"]:
        module = item.get("id") if isinstance(item, dict) else None
        if module not in MODULES or module in seen:
            raise ReleaseUnavailable()
        seen.add(module)
        native = module in {"advanced", "admin"}
        if (item.get("url") != f'https://github.com/{repository}/releases/download/{manifest["previewTag"]}/{MODULES[module]}'
                or item.get("kind") != ("native" if native else "assets")
                or type(item.get("sizeBytes")) is not int or not 0 < item["sizeBytes"] <= MAX_MODULE
                or not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
                or not isinstance(item.get("revision"), str)
                or not re.fullmatch(("n1-" if native else "a1-") + r"[0-9a-f]{64}", item["revision"])
                or not isinstance(item.get("number", ""), str) or len(item.get("number", "")) > 250):
            raise ReleaseUnavailable()
        rows.append({key: item[key] for key in ("id", "kind", "url", "sizeBytes", "sha256", "revision", "number") if key in item})
    return dict(schemaVersion=1, versionCode=manifest["versionCode"], versionName=manifest["versionName"],
                previewTag=manifest["previewTag"], modules=rows)


class DraftReleases:
    def __init__(self):
        self.token = os.getenv("ACM_ANDROID_GITHUB_TOKEN", "").strip()
        self.repository = os.getenv("ACM_ANDROID_GITHUB_REPOSITORY", "GiraffesLoveBeauty/ACM-Forever").strip()
        self.lock = asyncio.Lock()

    def configured(self):
        if not self.token or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repository):
            raise ReleaseUnavailable()

    async def fetch(self, session, path, limit, target=None):
        """Only GitHub API receives the token; redirects receive no credentials."""
        url = "https://api.github.com/repos/" + self.repository + path
        headers = {"Authorization": "Bearer " + self.token, "Accept": "application/octet-stream" if "/assets/" in path else "application/vnd.github+json"}
        for _ in range(4):
            async with session.get(url, headers=headers, allow_redirects=False) as response:
                if response.status in (301, 302, 303, 307, 308):
                    url = response.headers.get("Location", "")
                    parsed = urlsplit(url)
                    if (parsed.scheme != "https" or parsed.hostname not in {
                            "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
                            or parsed.port not in (None, 443) or parsed.username or parsed.password or parsed.fragment):
                        raise ReleaseUnavailable()
                    headers = {"Accept": "application/octet-stream"}
                    continue
                if response.status != 200 or (response.content_length is not None and response.content_length > limit):
                    raise ReleaseUnavailable()
                chunks = bytearray()
                count = 0
                async for block in response.content.iter_chunked(65536):
                    count += len(block)
                    if count > limit:
                        raise ReleaseUnavailable()
                    if target is None:
                        chunks.extend(block)
                    else:
                        await asyncio.to_thread(target.write, block)
                return bytes(chunks)
        raise ReleaseUnavailable()

    async def latest(self, session):
        # Drafts are not exposed by /releases/latest or anonymous tag lookup.
        candidates, published = [], []
        for page in range(1, 11):
            rows = json.loads(await self.fetch(session, f"/releases?per_page=100&page={page}", 4 * 1024 * 1024))
            if not isinstance(rows, list):
                raise ReleaseUnavailable()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("tag_name", ""), str) or not isinstance(row.get("assets", []), list) or any(not isinstance(a, dict) for a in row.get("assets", [])):
                    raise ReleaseUnavailable()
                tag = row.get("tag_name", "")
                if row.get("draft") is False and not row.get("prerelease") and re.fullmatch(r"v\d+\.\d+\.\d+", tag) and any(a.get("name") == "update.json" for a in row.get("assets", [])):
                    published.append(tuple(map(int, tag[1:].split("."))))
                if row.get("draft") is not True or not re.fullmatch(r"v\d+\.\d+\.\d+-preview\.[1-9]\d*", tag):
                    continue
                assets = row.get("assets", [])
                manifests = [a for a in assets if a.get("name") == "update.json" and a.get("state") == "uploaded"]
                if len(manifests) != 1:
                    continue  # A still-uploading draft must not hide the previous usable version.
                try:
                    asset_id = int(manifests[0]["id"])
                    value = validate_manifest(json.loads(await self.fetch(session, f"/releases/assets/{asset_id}", 32768)))
                except (ReleaseUnavailable, ValueError, KeyError, TypeError):
                    continue
                name = f'acmforever-{value["versionName"]}-preview.{value["previewRevision"]}.apk'
                apks = [a for a in assets if a.get("name") == name and a.get("state") == "uploaded"
                        and a.get("size") == value["sizeBytes"]]
                module_ids = {}
                if value["releaseVersionCode"] >= 39:
                    catalogs = [a for a in assets if a.get("name") == "modules.json" and a.get("state") == "uploaded"]
                    if len(catalogs) != 1:
                        continue
                    try:
                        catalog = validate_catalog(json.loads(await self.fetch(session, f'/releases/assets/{int(catalogs[0]["id"])}', 65536)), value, self.repository)
                        expected_names = {"update.json", "modules.json", name, name + ".sha256", *MODULES.values()}
                        if len(assets) != 8 or {a.get("name") for a in assets if a.get("state") == "uploaded"} != expected_names:
                            continue
                        for entry in catalog["modules"]:
                            matches = [a for a in assets if a.get("name") == MODULES[entry["id"]] and a.get("size") == entry["sizeBytes"]]
                            if len(matches) != 1:
                                raise ReleaseUnavailable()
                            module_ids[MODULES[entry["id"]]] = int(matches[0]["id"])
                        value["moduleCatalog"] = catalog
                    except (ReleaseUnavailable, ValueError, KeyError, TypeError):
                        continue
                if tag == value["previewTag"] and len(apks) == 1:
                    candidates.append((value, int(apks[0]["id"]), module_ids))
            if len(rows) < 100:
                break
        else:
            # A truncated scan could miss a formal release and expose its retired preview.
            raise ReleaseUnavailable()
        if published:
            candidates = [c for c in candidates if tuple(map(int, c[0]["versionName"].split("."))) > max(published)]
        if not candidates:
            raise NoPreview()
        rank = lambda item: (item[0]["releaseVersionCode"], item[0]["previewRevision"])
        candidates.sort(key=rank, reverse=True)
        if len(candidates) > 1 and rank(candidates[0]) == rank(candidates[1]):
            raise ReleaseUnavailable()
        return candidates[0]

    async def metadata(self):
        self.configured()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            return (await self.latest(session))[0]

    async def download(self, tag):
        return await self.download_asset(tag, None)

    async def download_asset(self, tag, name):
        self.configured()
        # Bound simultaneous full APK buffers on each worker; no public static directory.
        async with self.lock:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                value, asset_id, module_ids = await self.latest(session)
                if value["previewTag"] != tag:
                    raise ReleaseUnavailable()
                limit = MAX_APK
                if name is not None:
                    if name not in module_ids:
                        raise ReleaseUnavailable()
                    asset_id = module_ids[name]
                    value = next(entry for entry in value["moduleCatalog"]["modules"] if MODULES[entry["id"]] == name)
                    limit = MAX_MODULE
                file = tempfile.TemporaryFile()
                try:
                    await self.fetch(session, f"/releases/assets/{asset_id}", limit, target=file)
                    await asyncio.to_thread(file.seek, 0)
                    digest = await asyncio.to_thread(file_digest, file)
                    if file.tell() != value["sizeBytes"] or digest.hexdigest() != value["sha256"]:
                        raise ReleaseUnavailable()
                    file.seek(0)
                    return value, file
                except BaseException:
                    file.close()
                    raise


def provider():
    return current_app.extensions["android_private_releases"]


@android_release_api.after_request
async def private_headers(response):
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Vary"] = "Cookie"
    return response


@android_release_api.get("/admin/android/releases/latest")
@admin_required
async def admin_latest():
    try:
        value = await provider().metadata()
        error = await revalidate_admin()
        return error or jsonify(value)
    except NoPreview:
        error = await revalidate_admin()
        return error or jsonify(available=False, message="暂无待发布测试版。")
    except (ReleaseUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return jsonify(success=False, message="测试版发布源尚未配置或暂不可用。"), 503


@android_release_api.get("/admin/android/releases/<string:tag>/apk")
@admin_required
async def admin_apk(tag):
    return await transfer(tag, None)


@android_release_api.get("/admin/android/releases/<string:tag>/modules")
@admin_required
async def admin_modules(tag):
    try:
        value = await provider().metadata()
        if value["previewTag"] != tag or "moduleCatalog" not in value:
            raise ReleaseUnavailable()
        error = await revalidate_admin()
        return error or jsonify(value["moduleCatalog"])
    except (ReleaseUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return jsonify(success=False, message="测试模块清单暂不可用，请重新检查版本。"), 503


@android_release_api.get("/admin/android/releases/<string:tag>/assets/<string:name>")
@admin_required
async def admin_asset(tag, name):
    if name not in MODULES.values():
        return jsonify(success=False, message="不支持的测试附件。"), 404
    return await transfer(tag, name)


async def transfer(tag, name):
    try:
        if not re.fullmatch(r"v\d+\.\d+\.\d+-preview\.[1-9]\d*", tag):
            raise ReleaseUnavailable()
        value, file = await (provider().download(tag) if name is None else provider().download_asset(tag, name))
    except (ReleaseUnavailable, aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return jsonify(success=False, message="测试版下载暂不可用，请重新检查版本。"), 503
    # Fetching upstream may take time. Revalidate role and password status before release of bytes.
    error = await revalidate_admin()
    if error:
        file.close()
        return error

    async def body():
        try:
            while True:
                block = await asyncio.to_thread(file.read, 65536)
                if not block:
                    break
                yield block
        finally:
            file.close()
    filename = name or f'acmforever-{value["versionName"]}-preview.{value["previewRevision"]}.apk'
    response = Response(body(), mimetype="application/vnd.android.package-archive" if filename.endswith(".apk") else "application/octet-stream")
    response.content_length = value["sizeBytes"]
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.timeout = 300
    return response


async def revalidate_admin():
    identity, error = await _login_required_response()
    if error:
        return error
    if identity["role"] not in {"admin", "root"}:
        return jsonify(success=False, message="管理权限已失效。"), 403
    return None
