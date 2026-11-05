"""Validate reviewed version tags and publish complete APK assets from GitHub Actions only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote

PACKAGE = "com.giraffeslovebeauty.acmforever"


def validate_source(tag, gradle, history):
    version = re.search(r"\bversionName\s+'(\d+\.\d+\.\d+)'", gradle)
    code = re.search(r"\bversionCode\s+(\d+)\b", gradle)
    if not version or not code or tag != "v" + version[1] or not 1 <= int(code[1]) <= 2100000000:
        raise ValueError("Tag must be vX.Y.Z and match the checked-out Android version")
    if (int(code[1]) != history.get("currentVersionCode") or not history.get("entries")
            or history["entries"][0].get("versionName") != version[1] or history.get("schemaVersion") != 1):
        raise ValueError("Version code/name and current bundled release notes must agree")
    return version[1], int(code[1])


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            result.update(block)
    return result.hexdigest()


def validate_manifest(value):
    if (not isinstance(value, dict) or value.get("packageName") != PACKAGE or type(value.get("versionCode")) is not int
            or not 1 <= value["versionCode"] <= 2100000000
            or not re.fullmatch(r"\d+\.\d+\.\d+", value.get("versionName", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", value.get("sha256", ""))
            or type(value.get("sizeBytes")) is not int or not 0 < value["sizeBytes"] <= 150 * 1024 * 1024
            or type(value.get("minSdk")) is not int or not 26 <= value["minSdk"] <= 10000
            or not isinstance(value.get("notes"), str) or not value["notes"].strip()
            or len(value["notes"].encode("utf-16-le")) // 2 > 8000):
        raise ValueError("Release manifest identity/version/hash is invalid")


class GitHub:
    """Use gh's authenticated asset transport; never print tokens or redirect credentials."""
    def __init__(self, repository):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository")
        self.repository = repository

    def run(self, *args, missing=False):
        result = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
        if result.returncode:
            if missing and "(HTTP 404)" in result.stderr:
                return None
            raise RuntimeError("GitHub operation failed; check Actions permissions, repository and asset availability")
        return result.stdout

    def api(self, suffix, *args, missing=False):
        result = self.run("api", "repos/" + self.repository + suffix, *args, missing=missing)
        return None if result is None else json.loads(result)

    def repository_info(self):
        return self.api("")

    def latest(self):
        return self.api("/releases/latest", missing=True)

    def release(self, tag):
        current = self.api("/releases/tags/" + quote(tag, safe=""), missing=True)
        if current is not None:
            return current
        # Drafts may have an untagged HTML URL and return 404 from the tag lookup,
        # even though the authenticated releases list contains their tag_name.
        found, page = None, 1
        while True:
            rows = self.api("/releases?per_page=100&page=" + str(page))
            for row in rows:
                if row.get("tag_name") == tag and row.get("draft"):
                    if found is not None:
                        raise ValueError("Multiple drafts match this tag; resolve them before publishing")
                    found = row
            if len(rows) < 100:
                return found
            page += 1

    def create(self, tag, title, notes):
        # --verify-tag prevents gh from silently creating a tag at the default branch.
        self.run("release", "create", tag, "--repo", self.repository, "--verify-tag", "--draft", "--title", title, "--notes-file", str(notes))

    def upload(self, tag, paths):
        current = self.release(tag)
        if current is None or not current.get("draft"):
            raise ValueError("Only an unpublished draft may receive or replace assets")
        # Address the draft and its attachments by ID, never by its tag URL.
        for path in paths:
            for asset in current.get("assets", []):
                if asset.get("name") == path.name:
                    self.run("api", "--method", "DELETE", "repos/" + self.repository
                             + "/releases/assets/" + str(asset["id"]))
            self.run("api", "--method", "POST", "https://uploads.github.com/repos/" + self.repository
                     + "/releases/" + str(current["id"]) + "/assets?name=" + quote(path.name, safe=""),
                     "--header", "Content-Type: application/octet-stream", "--input", str(path))

    def download(self, tag, filename, directory):
        current = self.release(tag)
        asset = next((a for a in (current or {}).get("assets", []) if a.get("name") == filename), None)
        if asset is None:
            raise ValueError("Release attachment is missing: " + filename)
        target = directory / filename
        with target.open("wb") as output:
            result = subprocess.run(["gh", "api", "repos/" + self.repository + "/releases/assets/" + str(asset["id"]),
                "--header", "Accept: application/octet-stream"], stdout=output, stderr=subprocess.PIPE)
        if result.returncode:
            target.unlink(missing_ok=True)
            raise RuntimeError("Release attachment download failed; check Actions permissions and availability")
        return target

    def publish(self, tag):
        current = self.release(tag)
        if current is None or not current.get("draft"):
            raise ValueError("Only an unpublished draft may be published")
        result = self.api("/releases/" + str(current["id"]), "--method", "PATCH",
                          "--field", "draft=false", "--field", "prerelease=false", "--raw-field", "make_latest=true")
        if result.get("draft") is not False or result.get("tag_name") != tag:
            raise ValueError("Published Release response differs from the selected draft")


def read_manifest(github, release, directory):
    if not any(a.get("name") == "update.json" for a in release.get("assets", [])):
        raise ValueError("Published Release has no update.json; do not guess its version")
    path = github.download(release["tag_name"], "update.json", directory)
    if path.stat().st_size > 32768:
        raise ValueError("Published update manifest exceeds 32 KiB")
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(value)
    return value


def require_newer(github, manifest):
    previous = github.latest()
    if previous is None:
        return
    with tempfile.TemporaryDirectory() as temp:
        old = read_manifest(github, previous, Path(temp))
    if manifest["versionCode"] <= old["versionCode"]:
        raise ValueError("versionCode must be greater than the latest published code")
    if (old.get("channel", "release") == manifest["channel"]
            and old.get("signingCertificateSha256") != manifest["signingCertificateSha256"]):
        raise ValueError("The signing certificate changed within the same release channel")


def publish(github, tag, directory, source_commit):
    directory = Path(directory)
    manifest_path = directory / "update.json"
    if manifest_path.stat().st_size > 32768:
        raise ValueError("Update manifest exceeds 32 KiB")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(manifest)
    if tag != "v" + manifest["versionName"] or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Tag or source commit is invalid")
    if (manifest.get("channel") not in ("debug", "release")
            or not re.fullmatch(r"[0-9a-f]{64}", manifest.get("signingCertificateSha256", ""))):
        raise ValueError("Channel and pinned signing certificate are required")
    suffix = "-debug" if manifest["channel"] == "debug" else ""
    filename = "acmforever-" + manifest["versionName"] + suffix + ".apk"
    expected_url = "https://github.com/" + github.repository + "/releases/download/" + tag + "/" + filename
    if manifest.get("apkUrl") != expected_url:
        raise ValueError("APK URL must identify this repository, version tag and channel")
    apk, checksum = directory / filename, directory / (filename + ".sha256")
    if (not 0 < apk.stat().st_size <= 150 * 1024 * 1024 or apk.stat().st_size != manifest.get("sizeBytes")
            or digest(apk) != manifest["sha256"]
            or checksum.read_text(encoding="ascii").strip() != manifest["sha256"] + "  " + filename):
        raise ValueError("Local release assets no longer match the validated APK")
    if github.repository_info().get("private") is not False:
        raise ValueError("App update assets must be in a public repository")
    current = github.release(tag)
    if current is not None and not current.get("draft"):
        # Published versions are immutable. Only a byte-identical rerun is a no-op.
        with tempfile.TemporaryDirectory() as temp:
            remote = read_manifest(github, current, Path(temp))
            if remote != manifest:
                raise ValueError("A different published artifact already exists for this tag")
            remote_apk = github.download(tag, filename, Path(temp))
            if digest(remote_apk) != manifest["sha256"]:
                raise ValueError("Published APK differs from its manifest")
            remote_checksum = github.download(tag, checksum.name, Path(temp))
            if digest(remote_checksum) != digest(checksum):
                raise ValueError("Published checksum differs from the APK checksum")
        return "Already published; identical APK and manifest"
    require_newer(github, manifest)
    with tempfile.TemporaryDirectory() as temp:
        notes = Path(temp) / "release-notes.md"
        title = "ACMforever " + manifest["versionName"] + (" · debug" if suffix else "")
        notes.write_text("# " + title + "\n\nversionCode: " + str(manifest["versionCode"])
                         + "\n\n" + manifest.get("notes", "") + "\n\nSource commit: `" + source_commit + "`\n", encoding="utf-8")
        if current is None:
            github.create(tag, title, notes)
        github.upload(tag, [apk, checksum, manifest_path])
        # Read back each draft asset using gh's authenticated download support.
        for local in (apk, checksum, manifest_path):
            remote = github.download(tag, local.name, Path(temp))
            if digest(remote) != digest(local):
                raise ValueError("Uploaded asset read-back failed; Release remains a draft")
        require_newer(github, manifest)
        github.publish(tag)
    return "Published verified Release " + tag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("--tag", required=True)
    check.add_argument("--gradle", default="Android_APP/app/app/build.gradle")
    check.add_argument("--history", default="Android_APP/app/app/src/main/assets/releases/history.json")
    release = sub.add_parser("publish")
    for option in ("tag", "directory", "repository", "source-commit"):
        release.add_argument("--" + option, required=True)
    args = parser.parse_args()
    if args.command == "validate":
        print(validate_source(args.tag, Path(args.gradle).read_text(encoding="utf-8"), json.loads(Path(args.history).read_text(encoding="utf-8"))))
    else:
        if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "push"
                or os.environ.get("GITHUB_REF") != "refs/tags/" + args.tag
                or os.environ.get("GITHUB_REPOSITORY") != args.repository
                or os.environ.get("GITHUB_SHA") != args.source_commit):
            parser.error("Publication is allowed only in the matching GitHub tag-push Action")
        print(publish(GitHub(args.repository), args.tag, args.directory, args.source_commit))


if __name__ == "__main__":
    main()
