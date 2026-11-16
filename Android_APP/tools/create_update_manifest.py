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
        if any(name.lower().endswith(".apk") for name in archive.namelist()):
            raise ValueError("A distribution APK must not bundle another APK")
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
    return {"packageName": fields["name"], "versionCode": code, "versionName": name, "minSdk": minimum}


def manifest_for(apk, metadata, history, *, tag, repository, server, notes, channel="release", certificate=None):
    if channel not in ("preview", "release"):
        raise ValueError("Invalid release channel")
    if metadata["packageName"] != PACKAGE:
        raise ValueError("Distribution and application ID must agree")
    preview = re.fullmatch(r"v" + re.escape(metadata["versionName"]) + r"-preview\.([1-9]\d*)", tag) if channel == "preview" else None
    if (channel == "preview" and preview is None) or (channel == "release" and tag != "v" + metadata["versionName"]):
        raise ValueError("Release tag must match the actual APK version: vX.Y.Z")
    target = history.get("currentVersionCode", 0)
    code_matches = metadata["versionCode"] < target if preview else metadata["versionCode"] == target
    if (history.get("schemaVersion") != 1 or not code_matches
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
    filename = "acmforever-" + metadata["versionName"] + ("-preview." + preview[1] if preview else "") + ".apk"
    digest = hashlib.sha256()
    with apk.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    result = {**metadata, "apkUrl": server.rstrip("/") + "/" + repository
              + "/releases/download/" + tag + "/" + filename,
              "sha256": digest.hexdigest(), "sizeBytes": size, "notes": notes,
              "schemaVersion": 2, "distribution": channel}
    # Legacy 0.2.x clients reject channel=release when running a debug build.
    # An absent legacy channel enables the signed, same-package migration.
    if preview:
        result.pop("apkUrl")
        result.update(previewTag=tag, previewRevision=int(preview[1]), releaseVersionCode=target)
        result["apkPath"] = "/api/admin/android/releases/" + tag + "/apk"
    if certificate is not None:
        result["signingCertificateSha256"] = certificate
    if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > 32768:
        raise ValueError("Manifest exceeds the Android client's 32 KiB limit")
    return result


def verify_variant(badging, channel):
    debug = bool(re.search(r"^application-debuggable\s*$", badging, re.MULTILINE))
    if channel not in ("release", "preview") or debug:
        raise ValueError("APK build type differs from the selected release channel")


def signer_digest(output, expected):
    expected = expected.replace(":", "").lower()
    signers = re.findall(r"^Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})\s*$", output, re.MULTILINE)
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or len(signers) != 1 or signers[0].lower() != expected:
        raise ValueError("APK signing certificate differs from the pinned channel certificate")
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("apk", "aapt", "apksigner", "tag", "repository", "server", "output-dir"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--channel", choices=("preview", "release"), required=True)
    parser.add_argument("--certificate", required=True, help="Pinned SHA-256 of the signing certificate")
    parser.add_argument("--history", default=str(Path(__file__).resolve().parents[1]
                        / "app/app/src/main/assets/releases/history.json"))
    parser.add_argument("--credits", default=str(Path(__file__).resolve().parents[1]
                        / "app/app/src/main/assets/releases/credits.json"))
    args = parser.parse_args()
    apk = Path(args.apk).resolve(strict=True)
    verification = subprocess.run([args.apksigner, "verify", "--verbose", "--print-certs", str(apk)], check=True, capture_output=True)
    certificate = signer_digest(verification.stdout.decode("utf-8"), args.certificate)
    badging = subprocess.run([args.aapt, "dump", "badging", str(apk)], check=True, capture_output=True).stdout.decode("utf-8")
    metadata = parse_badging(badging)
    verify_variant(badging, args.channel)
    history = bundled_history(apk, json.loads(Path(args.history).read_text(encoding="utf-8")))
    from release_credits import bundled_credits, requires_review_record
    if requires_review_record(metadata["versionName"]):
        bundled_credits(apk, metadata["versionName"], json.loads(Path(args.credits).read_text(encoding="utf-8")))
    manifest = manifest_for(apk, metadata, history, tag=args.tag, repository=args.repository,
                            server=args.server, notes=os.environ.get("RELEASE_NOTES", ""), channel=args.channel, certificate=certificate)
    tree = subprocess.run([args.aapt, "dump", "xmltree", str(apk), "AndroidManifest.xml"], check=True, capture_output=True).stdout.decode("utf-8")
    verify_embedded_distribution(tree, manifest)
    destination = Path(args.output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    filename = "acmforever-" + metadata["versionName"] + ("-preview." + str(manifest["previewRevision"]) if args.channel == "preview" else "") + ".apk"
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


def verify_embedded_distribution(tree, manifest):
    values, entry = {}, None
    def finish():
        if entry and "name" in entry and "value" in entry:
            values[entry["name"]] = entry["value"]
    for line in tree.splitlines():
        if "E:" in line:
            finish()
            entry = {} if re.search(r"E: meta-data\b", line) else None
        elif entry is not None:
            match = re.search(r'A: android:(name|value)\([^)]*\)=(?:"([^"]*)"|\(type 0x1[02]\)(0x[0-9a-fA-F]+))', line)
            if match:
                entry[match[1]] = match[2] if match[2] is not None else int(match[3], 16)
    finish()
    if (values.get("acmforever.distribution") != manifest["distribution"]
            or values.get("acmforever.preview_revision") != manifest.get("previewRevision", 0)
            or values.get("acmforever.release_version_code") != manifest.get("releaseVersionCode", manifest["versionCode"])):
        raise ValueError("Embedded distribution/revision differs from the selected manifest")


if __name__ == "__main__":
    main()
