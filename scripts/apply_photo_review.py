"""Apply the visual review after importing observations. Restore missing local detail images."""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
import re

from PIL import Image, ImageOps

from cache_observation_photos import write_index
from supplement_inaturalist import merge
from sync_photos import ROOT, Rendition, download, restore_rendition, valid_webp


def restore(detail, sid, photo_id, verify_only):
    key = sid.removeprefix("avibase-").lower()
    if not re.fullmatch(r"[0-9a-f]{8}", key) or not re.fullmatch(r"[0-9]+", photo_id):
        raise ValueError(f"Invalid image identifier for {sid}")
    filename = f"{key}-{photo_id}.webp"
    large = Path("photos/plates") / filename
    small = Path("photos/archive") / key[:2] / filename
    versions = [(large, Rendition(filename, 1920, 88, detail["size"], None)),
                (small, Rendition(filename, 480, 82, detail["thumbnailSize"], detail.get("thumbnailCrop")))]
    missing = [(ROOT / path, version) for path, version in versions if not valid_webp(ROOT / path, version)]
    if missing:
        if verify_only:
            raise ValueError(f"Missing or invalid local image for {sid}: {missing[0][0]}")
        raw = download(detail["imageUrl"])
        if hashlib.sha256(raw).hexdigest() != detail["sourceSHA256"]:
            raise ValueError(f"Source photograph changed for {sid}")
        with Image.open(BytesIO(raw)) as file:
            source = ImageOps.exif_transpose(file).convert("RGB")
        if list(source.size) != detail["sourceSize"]:
            raise ValueError(f"Original dimensions changed for {sid}")
        for path, version in missing:
            path.parent.mkdir(parents=True, exist_ok=True)
            restore_rendition(source, path, version)
    return large.as_posix(), small.as_posix()


def apply(index, review, verify_only):
    taxonomy = {r["id"]: r for r in json.loads((ROOT / "data/checklist.json").read_bytes())["species"]}
    curated = {r["id"]: r["latin"] for r in json.loads((ROOT / "data/photos.json").read_bytes())}
    entries = index["bySpecies"]
    for decision in review["removed"]:
        if "curated" in decision and curated.get(decision["curated"]) != taxonomy[decision["taxon"]]["latin"]:
            raise ValueError(f"Missing curated replacement for {decision['taxon']}")
        current = entries.get(decision["taxon"])
        replacement = review["details"].get(decision["taxon"], {}).get("photo")
        if current and str(current["photoId"]) not in {str(decision["photo"]), str(replacement)}:
            raise ValueError(f"Review is stale for {decision['taxon']}")
    merge(index, review, taxonomy)
    for sid, detail in review["details"].items():
        row = entries[sid]
        if str(row["photoId"]) != str(detail["photo"]):
            raise ValueError(f"Image and credit disagree for {sid}")
        row["localFull"], row["localThumb"] = restore(detail, sid, str(detail["photo"]), verify_only)
        row["imageUrl"] = detail["imageUrl"]
    return index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=ROOT / "data/observations.json")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    review = json.loads((ROOT / "data/photo-quality-review.json").read_bytes())
    index = json.loads(args.index.read_bytes())
    if args.verify_only:
        original = json.dumps(index, sort_keys=True)
    apply(index, review, args.verify_only)
    if args.verify_only:
        if json.dumps(index, sort_keys=True) != original:
            raise ValueError("Published photo index differs from the visual review")
    else:
        write_index(index, args.index)
    print(f"{len(review['details'])} observation photographs verified")


if __name__ == "__main__":
    main()
