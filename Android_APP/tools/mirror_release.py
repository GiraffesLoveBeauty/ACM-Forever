"""Mirror the same verified release assets over pinned SSH; promote latest only after publication."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from urllib.parse import urlsplit

MAX_APK = 150 * 1024 * 1024


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            result.update(block)
    return result.hexdigest()


def tag_value(tag):
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Invalid release tag")
    return tag


def checked_root(value):
    root = Path(value).absolute()
    if root.is_symlink() or root == root.parent:
        raise ValueError("Release root must be a dedicated real directory")
    root.mkdir(parents=True, exist_ok=True, mode=0o755)
    return root.resolve()


def child(root, *parts):
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents) if p != root.parent):
        raise ValueError("Release path escapes its directory or contains a symlink")
    return path


@contextmanager
def release_lock(root):
    lock = child(root, ".publish.lock")
    with lock.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.write(b"\0")
            stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def validate_directory(directory, tag):
    tag_value(tag)
    manifest_path = directory / "update.json"
    if manifest_path.is_symlink() or not 0 < manifest_path.stat().st_size <= 32768:
        raise ValueError("Invalid mirror manifest size")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("packageName") != "com.giraffeslovebeauty.acmforever"
            or manifest.get("versionName") != tag[1:]
            or type(manifest.get("versionCode")) is not int or not 1 <= manifest["versionCode"] <= 2100000000
            or manifest.get("channel") not in ("debug", "release")
            or not re.fullmatch(r"[a-f0-9]{64}", manifest.get("sha256", ""))
            or not re.fullmatch(r"[a-f0-9]{64}", manifest.get("signingCertificateSha256", ""))):
        raise ValueError("Invalid mirror release identity")
    filename = "acmforever-" + tag[1:] + ("-debug" if manifest["channel"] == "debug" else "") + ".apk"
    apk, checksum = directory / filename, directory / (filename + ".sha256")
    if (apk.is_symlink() or checksum.is_symlink() or not 0 < apk.stat().st_size <= MAX_APK
            or apk.stat().st_size != manifest.get("sizeBytes") or sha(apk) != manifest["sha256"]
            or checksum.stat().st_size > 256
            or checksum.read_text(encoding="ascii").strip() != manifest["sha256"] + "  " + filename):
        raise ValueError("Mirror assets do not match their manifest")
    return manifest, (filename, filename + ".sha256", "update.json")


def receive(root, tag, stream):
    """Receive only three regular files into quarantine, then install an immutable version."""
    root = checked_root(root)
    tag_value(tag)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
    try:
        seen, total = set(), 0
        with tarfile.open(fileobj=stream, mode="r|") as archive:
            for entry in archive:
                if (not entry.isfile() or not re.fullmatch(r"(?:update\.json|acmforever-\d+\.\d+\.\d+(?:-debug)?\.apk(?:\.sha256)?)", entry.name)
                        or entry.name in seen or entry.size < 0):
                    raise ValueError("Unexpected or duplicate mirror archive entry")
                seen.add(entry.name)
                total += entry.size
                if len(seen) > 3 or total > MAX_APK + 33024:
                    raise ValueError("Mirror archive exceeds its limit")
                target = stage / entry.name
                with archive.extractfile(entry) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, 65536)
                os.chmod(target, 0o644)
        manifest, names = validate_directory(stage, tag)
        if seen != set(names):
            raise ValueError("Mirror archive must contain exactly the release assets")
        with release_lock(root):
            parent = child(root, "download")
            parent.mkdir(exist_ok=True, mode=0o755)
            destination = child(root, "download", tag)
            if destination.exists():
                _, old_names = validate_directory(destination, tag)
                if names != old_names or any(sha(stage / name) != sha(destination / name) for name in names):
                    raise ValueError("An immutable mirrored version already has different assets")
            else:
                os.chmod(stage, 0o755)
                stage.rename(destination)
        return manifest
    finally:
        if stage.exists():
            if stage.is_symlink() or stage.resolve().parent != root or not stage.name.startswith(".stage-"):
                raise ValueError("Refusing to clean a staging path outside its release root")
            shutil.rmtree(stage)


def promote(root, tag):
    root = checked_root(root)
    tag_value(tag)
    with release_lock(root):
        directory = child(root, "download", tag)
        manifest, _ = validate_directory(directory, tag)
        latest = child(root, "latest")
        latest.mkdir(exist_ok=True, mode=0o755)
        target = child(root, "latest", "update.json")
        if target.exists():
            if target.stat().st_size > 32768:
                raise ValueError("Existing latest is invalid")
            old = json.loads(target.read_text(encoding="utf-8"))
            if (type(old.get("versionCode")) is not int or old["versionCode"] > manifest["versionCode"]
                    or old["versionCode"] == manifest["versionCode"] and old != manifest):
                raise ValueError("Cannot downgrade latest or replace the same code")
            if old.get("channel") != manifest["channel"] or old.get("signingCertificateSha256") != manifest["signingCertificateSha256"]:
                raise ValueError("Mirror channel or signing certificate changed")
        fd, temporary = tempfile.mkstemp(prefix=".update-", dir=latest)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write((directory / "update.json").read_bytes())
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temporary, 0o644)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)


class SSHMirror:
    def __init__(self, repository, origin):
        self.repository, self.origin = repository, origin.rstrip("/")
        parsed = urlsplit(self.origin)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.path or parsed.query or parsed.fragment or not re.fullmatch(r"[\w.-]+/[\w.-]+", repository)):
            raise ValueError("Invalid mirror HTTPS origin or repository")
        self.host = os.environ.get("ANDROID_MIRROR_HOST", "")
        self.user = os.environ.get("ANDROID_MIRROR_USER", "")
        self.port = os.environ.get("ANDROID_MIRROR_PORT", "22")
        self.root = os.environ.get("ANDROID_MIRROR_ROOT", "")
        self.key = os.environ.get("ANDROID_MIRROR_KEY_FILE", "")
        self.hosts = os.environ.get("ANDROID_MIRROR_HOSTS_FILE", "")
        if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", self.host)
                or not re.fullmatch(r"[a-z_][a-z0-9_-]*", self.user)
                or not self.port.isdigit() or not 1 <= int(self.port) <= 65535
                or not re.fullmatch(r"/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+", self.root)
                or self.root in ("/root", "/srv", "/home", "/tmp")
                or "acm-forever-feat" in self.root.split("/")
                or not Path(self.key).is_file() or not Path(self.hosts).is_file()):
            raise ValueError("Configure the dedicated mirror SSH account, directory and pinned host key")

    def remote(self, action, tag, stream=None):
        tag_value(tag)
        code = Path(__file__).read_text(encoding="utf-8")
        command = " ".join(shlex.quote(v) for v in ["python3", "-c", code, "--receive", action, "--root", self.root, "--tag", tag])
        result = subprocess.run(["ssh", "-i", self.key, "-p", self.port,
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + self.hosts,
            "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=2",
            self.user + "@" + self.host, command], stdin=stream if stream is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        if result.returncode:
            raise RuntimeError("Mirror " + action + " failed; check server directory, SSH permissions and deployment logs")

    def public_check(self, suffix, expected):
        class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, message, headers, url):
                if urlsplit(url).scheme != "https":
                    raise ValueError("Mirror redirect must remain HTTPS")
                return super().redirect_request(request, fp, code, message, headers, url)
        request = urllib.request.Request(self.origin + "/" + self.repository + "/releases/" + suffix,
            headers={"Cache-Control": "no-cache", "User-Agent": "ACMforever-release-verification"})
        digest, size = hashlib.sha256(), 0
        with urllib.request.build_opener(HTTPSRedirect()).open(request, timeout=30) as response:
            if response.status != 200 or urlsplit(response.url).scheme != "https":
                raise ValueError("Mirror public URL is not an HTTPS download")
            for chunk in iter(lambda: response.read(65536), b""):
                size += len(chunk)
                if size > expected.stat().st_size:
                    raise ValueError("Mirror public download has an unexpected size")
                digest.update(chunk)
        if size != expected.stat().st_size or digest.hexdigest() != sha(expected):
            raise ValueError("Mirror public read-back differs from the release assets")

    def stage(self, tag, directory, manifest):
        _, names = validate_directory(directory, tag)
        with tempfile.TemporaryFile() as archive:
            with tarfile.open(fileobj=archive, mode="w") as output:
                for name in names:
                    output.add(directory / name, arcname=name, recursive=False)
            archive.seek(0)
            self.remote("stage", tag, archive)
        for name in names:
            self.public_check("download/" + tag + "/" + name, directory / name)

    def promote(self, tag, directory, manifest):
        self.remote("promote", tag)
        self.public_check("latest/update.json", directory / "update.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receive", choices=("stage", "promote"), required=True)
    parser.add_argument("--root", required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    if args.receive == "stage":
        receive(args.root, args.tag, sys.stdin.buffer)
    else:
        promote(args.root, args.tag)


if __name__ == "__main__":
    main()
