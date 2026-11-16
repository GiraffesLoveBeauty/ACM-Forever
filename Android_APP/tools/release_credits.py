"""Keep completed Review attribution in new published APKs; never infer a reviewer."""
import json
import re
from zipfile import ZipFile

ASSET = "assets/releases/credits.json"
REPOSITORY = "GiraffesLoveBeauty/ACM-Forever"


def requires_review_record(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid credits version")
    # Preserve immutable historical releases and their original publication contracts.
    return tuple(map(int, version.split("."))) >= (1, 0, 0)


def validate_release_credits(credits, version):
    if credits.get("schemaVersion") != 1 or credits.get("repository") != REPOSITORY:
        raise ValueError("Invalid release attribution snapshot")
    people = {p["login"] for p in credits["people"]}
    record = credits["versions"][version]
    text = [credits["historyOwnerNote"], *(p["role"] for p in credits["people"]),
            *(r["scope"] for r in credits["versions"].values())]
    if any("本人" in value or "鄙人" in value for value in text):
        raise ValueError("Attribution must name GitHub users, not first-person pronouns")
    if record["status"] not in ("reviewed", "published"):
        raise ValueError("Complete the actual Review record before creating a release Tag")
    if any(word in record["scope"] for word in ("尚未", "待评审", "未完成Review", "未完成 Review", "候选")):
        raise ValueError("Completed Review attribution still contains a pending-review description")
    for role in ("uploaders", "reviewRequesters", "reviewers"):
        names = record[role]
        if (not names or len(set(names)) != len(names)
                or any(name not in people for name in names)):
            raise ValueError("Release attribution is missing a valid " + role + " record")
    pr = record["pr"]
    evidence = record["evidence"]
    if type(pr) is not int or pr <= 0 or not evidence or any(
            not re.fullmatch(r"https://github\.com/" + REPOSITORY + r"/pull/" + str(pr)
                             + r"(?:#[A-Za-z0-9-]+)?", url) for url in evidence):
        raise ValueError("Review attribution must link to its actual PR")
    if ((record["status"] == "reviewed" and record["publishers"])
            or (record["status"] == "published" and not record["publishers"])
            or any(name not in people for name in record["publishers"])):
        raise ValueError("Do not prefill publication while recording a completed Review")
    return credits


def bundled_credits(apk, version, expected=None):
    with ZipFile(apk) as archive:
        entry = archive.getinfo(ASSET)
        if entry.file_size > 262144:
            raise ValueError("Bundled attribution snapshot exceeds 256 KiB")
        credits = json.loads(archive.read(entry).decode("utf-8"))
    if expected is not None and credits != expected:
        raise ValueError("APK contains different attribution from the reviewed source")
    return validate_release_credits(credits, version)
