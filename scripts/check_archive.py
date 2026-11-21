"""Validate the joins and source credits, report coverage, and optionally export remaining gaps."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate():
    catalog = read(DATA / "checklist.json")
    records = catalog["species"]
    species = {row["id"]: row for row in records}
    latin_ids = {row["latin"]: row["id"] for row in records}
    assert len(species) == len(latin_ids) == len(records), "duplicate taxonomy entries"
    localized = read(DATA / "chinese-names.json")["names"]
    assert localized.keys() <= latin_ids.keys(), "unmatched Chinese names"
    references = read(DATA / "references.json")["species"]
    assert references.keys() <= species.keys(), "unmatched external references"
    photographed, local_photos = set(), set()
    curated_files = set()
    for row in read(DATA / "photos.json"):
        sid = latin_ids[row["latin"]]
        assert sid not in photographed, row["id"]
        images = [row]
        if "historicalPhoto" in row:
            historic = row["historicalPhoto"]
            assert all(historic.get(k) for k in ("source", "enSource", "url", "photographed", "enPhotographed")), sid
            images.append(historic)
        if row.get("kind") == "specimen":
            assert row["source"] and row["enSource"] and len(row["sourceSize"]) == 2, sid
            assert max(row["size"]) == min(1920, max(row["sourceSize"])), sid
            thumb = row["thumbnail"]
            assert 0 < min(thumb["size"]) <= max(thumb["size"]) <= min(480, max(row["sourceSize"])), sid
        for image in images:
            local_original = image.get("originalFile")
            pages = "https://dolomitiaugust.github.io/bird-archive/photos/"
            source_url = image["credit"]["imageUrl"]
            if source_url.startswith(pages):
                local_original = source_url[len(pages):]
            if local_original:
                assert re.fullmatch(r"sources/[a-z0-9-]+\.jpe?g", local_original), sid
                raw = (ROOT / "photos" / local_original).read_bytes()
                assert hashlib.sha1(raw).hexdigest() == image["sourceSHA1"], sid
            filenames = [image["file"]]
            if "thumbnail" in image:
                filenames.append(image["thumbnail"]["file"])
            for filename in filenames:
                assert Path(filename).name == filename and filename not in curated_files, filename
                assert (ROOT / "photos" / filename).is_file(), filename
                curated_files.add(filename)
            assert all(image["credit"].get(k) for k in ("author", "filePage", "license", "licenseUrl", "imageUrl")), image["file"]
        photographed.add(sid)
        local_photos.add(sid)
    observations = read(DATA / "observations.json")["bySpecies"]
    assert len({r["photoId"] for r in observations.values()}) == len(observations), "same source image assigned to multiple taxa"
    for sid, row in observations.items():
        assert species[sid]["latin"] == row["scientificName"], sid
        assert all(row.get(k) for k in ("author", "sourceUrl", "license", "licenseUrl", "imageUrl", "thumbUrl")), sid
        if row.get("localThumb"):
            thumb = row["localThumb"]
            assert re.fullmatch(r"photos/archive/[0-9a-f]{2}/[0-9a-f]{8}-[0-9]+\.webp", thumb), sid
            assert (ROOT / thumb).is_file() and (ROOT / thumb).stat().st_size > 0, sid
            local_photos.add(sid)
        if row.get("localFull"):
            filename = f"{sid[8:].lower()}-{row['photoId']}.webp"
            assert row["localFull"] == f"photos/plates/{filename}", sid
            assert (ROOT / row["localFull"]).is_file() and row.get("localThumb"), sid
        photographed.add(sid)
    archives = {}
    for folder, languages in (("accounts", {"zh", "en"}), ("accounts-en", {"en"})):
        index = {}
        shards = sorted((DATA / folder).glob("*.json"))
        assert len(shards) == 256, f"Missing {folder} shards"
        for shard in shards:
            for sid, entry in read(shard).items():
                assert sid in species and sid[8:10].lower() == shard.stem and sid not in index, sid
                assert entry["lang"] in languages and entry["url"].startswith("https://") and entry["text"], sid
                index[sid] = entry
        archives[folder] = index
    accounts, english = archives["accounts"], archives["accounts-en"]
    gaps = []
    for row in records:
        sid = row["id"]
        missing = [label for label, found in (
            ("实拍照片", sid in photographed), ("中文名", row["latin"] in localized),
            ("百科简介", sid in accounts), ("外部档案", bool(references.get(sid))),
        ) if not found]
        if missing:
            gaps.append([sid, localized.get(row["latin"], {}).get("zh", ""), row["en"], row["latin"],
                         row["order"], row["family"], "、".join(missing)])
    counts = {
        "species": len(species), "photographedSpecies": len(photographed), "speciesWithLocalImages": len(local_photos),
        "chineseNames": len(localized), "accounts": len(accounts), "accountLanguages": dict(Counter(a["lang"] for a in accounts.values())),
        "englishExcerpts": len(english), "externalRecords": sum(bool(r) for r in references.values()),
        "photosToFind": len(records) - len(photographed),
    }
    return counts, gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gaps", type=Path, help="write a UTF-8 CSV of records needing material")
    parser.add_argument("--english-gaps", type=Path, help="write the same inventory with English labels")
    args = parser.parse_args()
    counts, gaps = validate()
    if args.gaps:
        with args.gaps.open("w", encoding="utf-8-sig", newline="") as handle:
            output = csv.writer(handle)
            output.writerow(["物种编号", "中文名", "英文名", "学名", "目", "科", "待补项目"])
            output.writerows(gaps)
    if args.english_gaps:
        labels = {"实拍照片": "Photograph", "中文名": "Chinese name", "百科简介": "Encyclopedia excerpt", "外部档案": "External record"}
        with args.english_gaps.open("w", encoding="utf-8-sig", newline="") as handle:
            output = csv.writer(handle)
            output.writerow(["Species ID", "Chinese name", "English name", "Scientific name", "Order", "Family", "Missing material"])
            for *record, missing in gaps:
                output.writerow(record + [", ".join(labels[item] for item in missing.split("、"))])
    print(json.dumps(counts, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError, KeyError, OSError) as error:
        sys.exit(f"Archive check failed: {error}")
