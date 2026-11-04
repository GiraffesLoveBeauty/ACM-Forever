"""Build public update metadata from a verified, signed APK; never reads secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import urlsplit
from zipfile import ZipFile

PACKAGE = "com.giraffeslovebeauty.acmforever"
MAX_BYTES = 150 * 1024 * 1024


def bundled_history(apk, expected):
    with ZipFile(apk) as archive:
        entry = archive.getinfo("assets/releases/history.json")
        if entry.file_size > 131072:
            raise ValueError("Bundled release history exceeds 128 KiB")
        history = json.loads(archive.read(entry).decode("utf-8"))
    if history != expected:
        raise ValueError("APK contains a different release history from the source")
    return history


def parse_badging(text):
    package_line = next((line for line in text.splitlines() if line.startswith("package: ")), "")
    fields = dict(re.findall(r"(\w+)='([^']*)'", package_line))
    sdk = re.search(r"^sdkVersion:'(\d+)'", text, re.MULTILINE)
    name = fields.get("versionName", "")
    if (fields.get("name") != PACKAGE or not re.fullmatch(r"\d+\.\d+\.\d+", name)
            or not fields.get("versionCode", "").isdigit() or not sdk):
        raise ValueError("APK package/version/minSdk metadata is invalid")
    code, minimum = int(fields["versionCode"]), int(sdk[1])
    if not 1 <= code <= 2100000000 or minimum < 26:
        raise ValueError("APK versionCode or minSdk is invalid")
    return {"packageName": PACKAGE, "versionCode": code, "versionName": name, "minSdk": minimum}


def manifest_for(apk, metadata, history, *, tag, repository, server, notes):
    if tag != "v" + metadata["versionName"]:
        raise ValueError("Release tag must match the actual APK version: vX.Y.Z")
    if (history.get("schemaVersion") != 1 or history.get("currentVersionCode") != metadata["versionCode"]
            or not history.get("entries") or history["entries"][0].get("versionName") != metadata["versionName"]):
        raise ValueError("APK version differs from the bundled release history")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid GitHub repository")
    origin = urlsplit(server)
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.path not in ("", "/") or origin.query or origin.fragment):
        raise ValueError("GitHub server must be an HTTPS origin without credentials")
    size = apk.stat().st_size
    if not 0 < size <= MAX_BYTES:
        raise ValueError("APK size exceeds the client's accepted range")
    notes = notes.strip() or "\n".join(filter(None, [history["entries"][0].get("summary", "")]
        + history["entries"][0].get("changes", []) + history["entries"][0].get("notes", [])))
    notes = notes or "本次更新没有附加说明。"
    if len(notes.encode("utf-16-le")) // 2 > 8000:
        raise ValueError("Release notes exceed the Android client's 8000-character limit")
    filename = "acmforever-" + metadata["versionName"] + ".apk"
    digest = hashlib.sha256()
    with apk.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    result = {**metadata, "apkUrl": server.rstrip("/") + "/" + repository
              + "/releases/download/" + tag + "/" + filename,
              "sha256": digest.hexdigest(), "sizeBytes": size, "notes": notes}
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 32768:
        raise ValueError("Manifest exceeds the Android client's 32 KiB limit")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("apk", "aapt", "apksigner", "tag", "repository", "server", "output-dir"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--history", default=str(Path(__file__).resolve().parents[1]
                        / "app/app/src/main/assets/releases/history.json"))
    args = parser.parse_args()
    apk = Path(args.apk).resolve(strict=True)
    subprocess.run([args.apksigner, "verify", "--verbose", str(apk)], check=True, capture_output=True)
    badging = subprocess.run([args.aapt, "dump", "badging", str(apk)], check=True, capture_output=True).stdout.decode("utf-8")
    metadata = parse_badging(badging)
    history = bundled_history(apk, json.loads(Path(args.history).read_text(encoding="utf-8")))
    manifest = manifest_for(apk, metadata, history, tag=args.tag, repository=args.repository,
                            server=args.server, notes=os.environ.get("RELEASE_NOTES", ""))
    destination = Path(args.output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    filename = "acmforever-" + metadata["versionName"] + ".apk"
    output_apk = destination / filename
    if output_apk == apk:
        raise ValueError("Output directory must differ from the build artifact directory")
    shutil.copyfile(apk, output_apk)
    # Refuse publication if the artifact changes during copy/hash verification.
    if hashlib.sha256(output_apk.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("APK changed while creating release metadata")
    (destination / "update.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (destination / (filename + ".sha256")).write_text(manifest["sha256"] + "  " + filename + "\n", encoding="ascii")
    print("apk_name=" + filename)


if __name__ == "__main__":
    main()
