"""Rebuild the Commons photo supplements from visually reviewed files with pinned hashes."""

import argparse
from datetime import date
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import time

from PIL import Image, ImageOps

from import_chinese_names import read_url
from import_wiki_accounts import request_json


ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(str(value))
    return " ".join(" ".join(parser.parts).split())


def save_picture(source, destination):
    with Image.open(BytesIO(read_url(source))) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((900, 900), Image.Resampling.LANCZOS)
        with NamedTemporaryFile(dir=destination.parent, delete=False, suffix=".part") as handle:
            temp = Path(handle.name)
        try:
            image.save(temp, "WEBP", quality=85, method=4)
            temp.replace(destination)
        finally:
            temp.unlink(missing_ok=True)


def checked_record(species, localized, review, page, photo_dir):
    info = page["imageinfo"][0]
    meta = {r["name"]: str(r["value"]) for r in info.get("metadata", [])}
    ext = {key: plain(value["value"]) for key, value in info["extmetadata"].items()}
    if info["sha1"] != review["fileSha1"] or info["mime"] != "image/jpeg":
        raise ValueError("Image version or format changed; recheck " + page["title"])
    camera = meta.get("Model", "").strip()
    if not camera:
        raise ValueError("No camera model for " + page["title"])
    description = ext.get("ImageDescription", "")
    if review["identityText"].casefold() not in (page["title"] + " " + description).casefold():
        raise ValueError("Species identification missing from " + page["title"])
    if species["latin"] != review["scientificName"]:
        raise ValueError("Taxon definition changed: " + review["speciesId"])
    author = ext.get("Attribution") or ext.get("Artist")
    license_name = ext.get("LicenseShortName", "")
    license_url = ext.get("LicenseUrl", "").rstrip("/") + "/"
    license_match = re.fullmatch(r"CC (BY|BY-SA) ([1-4]\.\d)", license_name)
    if not author or not license_match or license_url != f"https://creativecommons.org/licenses/{license_match[1].lower()}/{license_match[2]}/":
        raise ValueError("Review attribution and terms for " + page["title"])
    page_id = page["pageid"]
    filename = f"commons-{page_id}.webp"
    save_picture(info["thumburl"], photo_dir / filename)
    bird = localized["names"].get(species["latin"], {})
    row = {
        "id": f"BH-C{page_id}", "avibaseId": species["id"], "file": filename, "name": bird.get("zh") or species["en"],
        "en": species["en"], "latin": species["latin"],
        "order": localized["orders"].get(species["order"], {}).get("zh", species["order"]),
        "family": localized["families"].get(species["family"], {}).get("zh", species["family"]),
        "aliases": " ".join(bird.get("aliases", [])), "note": "", "source": "Wikimedia Commons", "url": info["descriptionurl"],
        "sourceId": "commons-p18", "basis": "camera-photograph",
        "imageContext": "活体实拍", "enImageContext": "Photograph of a living bird",
        "credit": {
            "author": author, "filePage": info["descriptionurl"], "imageUrl": info["url"],
            "license": license_name, "licenseUrl": license_url, "sourceId": "commons-p18",
        },
        "acquired": date.today().isoformat(), "changes": "保留原比例，缩小后转为 WebP。总览卡片按框裁切。",
        "enChanges": "Resized without changing proportions and converted to WebP. Gallery cards crop the preview.",
        "evidence": {"wikidata": review["qid"], "commonsPageId": page_id, "sha1": info["sha1"], "cameraModel": camera,
                     "identification": review["identityText"], "visualReview": "living bird"},
    }
    if "taxonomyReference" in review:
        row["evidence"]["taxonomyReference"] = review["taxonomyReference"]
    capture_date = ext.get("DateTimeOriginal", "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?: \d\d:\d\d:\d\d)?", capture_date):
        row["photographed"] = row["enPhotographed"] = capture_date[:10]
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "data/commons-additions.part")
    args = parser.parse_args()
    data = args.root / "data"
    reviews = json.loads((data / "commons-reviewed.json").read_text(encoding="utf-8"))
    check = json.loads((data / "checklist.json").read_text(encoding="utf-8"))
    catalog = {r["id"]: r for r in check["species"]}
    localized = json.loads((data / "chinese-names.json").read_text(encoding="utf-8"))
    records = []
    for start in range(0, len(reviews), 10):
        group = {r["pageId"]: r for r in reviews[start:start + 10]}
        response = request_json(API, {
            "action": "query", "format": "json", "formatversion": 2, "prop": "imageinfo",
            "iiprop": "url|metadata|extmetadata|mime|sha1", "iiurlwidth": 960, "iiextmetadatalanguage": "en",
            "maxlag": 5, "pageids": "|".join(str(pid) for pid in group),
        })
        for page in response["query"]["pages"]:
            review = group[page["pageid"]]
            records.append(checked_record(catalog[review["speciesId"]], localized, review, page, args.root / "photos"))
            time.sleep(0.4)
    if len(records) != len(reviews):
        raise ValueError("One of the reviewed files was not returned")
    records.sort(key=lambda row: row["avibaseId"])
    with NamedTemporaryFile(dir=args.output.parent, mode="w", suffix=".part", encoding="utf-8", delete=False) as handle:
        temp = Path(handle.name)
        json.dump(records, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        temp.replace(args.output)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Saved {len(records)} reviewed Commons photographs")


if __name__ == "__main__":
    main()
