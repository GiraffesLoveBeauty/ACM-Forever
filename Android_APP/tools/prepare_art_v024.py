"""Import user-supplied art and publicly served official platform marks."""
from pathlib import Path
from PIL import Image
import concurrent.futures
import hashlib
import io
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "app/app/src/main/res/drawable-nodpi"
QA = ROOT / "app/app/build/qa-v024"
RES.mkdir(exist_ok=True)
QA.mkdir(parents=True, exist_ok=True)
SOURCES = Path(r"E:\爱臭美工程\图片")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def import_user_art():
    records = []
    for source, name, size in [("1.png", "avatar_catgirl", 512),
                               ("2.png", "catgirl_loading", 640),
                               ("3.png", "catgirl_mask", 384)]:
        data = (SOURCES / source).read_bytes()
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        # Remove only near-transparent isolated colour specks from the exported edge.
        alpha = im.getchannel("A").point(lambda x: 0 if x < 12 else x)
        im.putalpha(alpha)
        if "mask" in name:
            im = Image.new("RGBA", im.size, (255, 255, 255, 0))
            im.putalpha(alpha)
        im.thumbnail((size, size), Image.Resampling.LANCZOS)
        im.save(RES / (name + ".png"), optimize=True)
        records.append({"source": str(SOURCES / source), "resource": name,
                        "source_sha256": digest(data)})
    # Adaptive launcher safe area: all character content fits inside the mask.
    launcher = Image.new("RGBA", (432, 432), (0, 0, 0, 0))
    portrait = Image.open(RES / "avatar_catgirl.png")
    portrait.thumbnail((264, 264), Image.Resampling.LANCZOS)
    launcher.alpha_composite(portrait, ((432-portrait.width)//2, (432-portrait.height)//2))
    launcher.save(RES / "launcher_portrait.png", optimize=True)
    # Notification icons use only alpha; avoid the old silhouette resource.
    Image.open(RES / "catgirl_mask.png").resize((96, 96), Image.Resampling.LANCZOS).save(RES / "ic_cat_notification.png")
    (QA / "user-art-sources.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    preview = Image.new("RGB", (900, 320), "#f4f5f7")
    for i, name in enumerate(["avatar_catgirl", "catgirl_loading", "catgirl_mask"]):
        im = Image.open(RES / (name + ".png"))
        if "mask" in name:
            tint = Image.new("RGBA", im.size, "#1e211c")
            tint.putalpha(im.getchannel("A"))
            im = tint
        im.thumbnail((280, 280), Image.Resampling.LANCZOS)
        preview.paste(im, (i*300+(300-im.width)//2, (320-im.height)//2), im)
    preview.save(QA / "user-art-preview.png")


def download_marks():
    candidates = {
        "codeforces": ["https://codeforces.org/s/0/images/codeforces-sponsored-by-ton.png", "https://codeforces.com/favicon.ico"],
        "atcoder": ["https://img.atcoder.jp/assets/atcoder.png", "https://img.atcoder.jp/assets/favicon.png"],
        "luogu": ["https://www.luogu.com.cn/favicon.ico", "https://www.luogu.com.cn/favicon.png"],
        "nowcoder": ["https://static.nowcoder.com/fe/file/logo/1.png"],
        "cjlu": ["https://acm.cjlu.edu.cn/favicon.ico"],
    }
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"https": "http://127.0.0.1:7897"}))
    def one(item):
        key, urls = item
        results = []
        for url in urls:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with opener.open(req, timeout=18) as response:
                    raw = response.read(2_000_000)
                    actual = response.url
                mark = Image.open(io.BytesIO(raw)).convert("RGBA")
                if key == "codeforces" and mark.width == 555 and mark.height == 130:
                    # Crop the unchanged three-bar brand symbol from the official wordmark.
                    mark = mark.crop((0, 19, 84, 86))
                # A square transparent tile keeps each original mark's aspect ratio.
                scale = min(320 / mark.width, 220 / mark.height)
                mark = mark.resize((round(mark.width * scale), round(mark.height * scale)), Image.Resampling.LANCZOS)
                tile = Image.new("RGBA", (352, 256), (255, 255, 255, 0))
                tile.alpha_composite(mark, ((352-mark.width)//2, (256-mark.height)//2))
                tile.save(RES / ("platform_" + key + ".png"), optimize=True)
                results.append({"url": url, "resolved_url": actual, "status": "downloaded", "sha256": digest(raw)})
                break
            except Exception as error:
                results.append({"url": url, "status": str(error)})
        return key, results
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = dict(pool.map(one, candidates.items()))
    (QA / "official-logo-sources.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import_user_art()
    download_marks()
