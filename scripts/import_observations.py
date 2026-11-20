"""Import the curated, traceable iNaturalist subset of Avicommons for AviList."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen

import import_checklist as avi


REPO = Path(__file__).resolve().parents[1]
COMMIT = "44305ddac3df99474e8f0fca33b23907ca35eedb"
INDEX_URL = f"https://raw.githubusercontent.com/rawcomposition/avicommons/{COMMIT}/public/2025.json"
INDEX_SHA256 = "3fce5e48eec0f9136c341dfc29752b970505ffe4a43c45af6c223acecee117de"
SHORT_LICENSES = {
    "cc0": "CC0 1.0", "cc-by": "CC BY 4.0", "cc-by-sa": "CC BY-SA 4.0",
    "cc-by-nc": "CC BY-NC 4.0", "cc-by-nc-sa": "CC BY-NC-SA 4.0",
}


def license_details(label):
    # Use the source's explicit version. Only unversioned iNat codes use its
    # published mapping. The curated dataset also contains invalid CC0 versions.
    full = SHORT_LICENSES.get(label, label)
    if full == "CC0 1.0":
        return full, "https://creativecommons.org/publicdomain/zero/1.0/"
    match = re.fullmatch(r"CC (BY(?:-NC-SA|-NC|-SA)?) ([1234]\.0|2\.5)(?:-([a-z]{2}))?", full)
    if not match:
        return None
    scheme, version, region = match.groups()
    href = f"https://creativecommons.org/licenses/{scheme.lower()}/{version}/"
    if region:
        return f"CC {scheme} {version} {region.upper()}", f"{href}{region}/"
    return full, href


def import_images(photos, taxonomy):
    taxon_by_code = {r[17]: r for r in taxonomy if r[1] == "species" and r[17]}
    key_counts = Counter(p["key"] for p in photos)
    eligible = {}
    skipped = Counter()
    for photo in photos:
        key, code = photo["key"], photo["code"]
        taxon = taxon_by_code.get(code)
        if not re.fullmatch(r"[0-9]+", key):
            skipped["non-iNat key / medium not verified"] += 1
            continue
        if taxon is None or taxon[5] != photo["sciName"]:
            skipped["taxonomy differs"] += 1
            continue
        if key_counts[key] != 1:
            skipped["photo reused by multiple source species"] += 1
            continue
        if taxon[14] and "reintroduced" not in taxon[14].lower():
            skipped["extinction flag needs review"] += 1
            continue
        license_info = license_details(photo["license"])
        if not license_info or not photo["by"].strip():
            skipped["unusable license or attribution"] += 1
            continue
        taxon_id = taxon[19]
        if taxon_id in eligible:
            raise ValueError(f"Duplicate target species {taxon_id}")
        license_name, license_url = license_info
        original = f"https://www.inaturalist.org/photos/{key}"
        media = f"https://static.avicommons.org/{code}-{key}-"
        eligible[taxon_id] = {
            "id": key, "photoId": key, "scientificName": taxon[5],
            "author": photo["by"], "license": license_name, "licenseUrl": license_url,
            "sourceUrl": original, "filePage": original, "imageUrl": media + "900.jpg",
            "thumbUrl": media + "320.jpg",
        }
    return eligible, skipped


def write_catalog(photos, output):
    metadata = {
        "sourceId": "avicommons", "source": "Avicommons · iNaturalist",
        "sourceUrl": "https://avicommons.org/", "version": "eBird/Clements 2025",
        "license": "Each photograph retains its individual Creative Commons license.",
        "attribution": "Photo selection and presentation by Avicommons (Adam Jackson); original photographers credited per image.",
        "provenance": "Curated iNaturalist photos; links identify the original photograph. Not a per-photo field or research-grade verification.",
    }
    head = json.dumps(metadata, ensure_ascii=False, indent=2)[:-2]
    lines = [json.dumps(key) + ":" + json.dumps(row, ensure_ascii=False, separators=(",", ":")) for key, row in photos.items()]
    content = head + ',\n  "bySpecies": {\n' + ',\n'.join(lines) + '\n  }\n}\n'
    output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output.parent, delete=False) as dest:
        temporary = Path(dest.name)
    try:
        temporary.write_bytes(content.encode("utf-8"))
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--taxonomy", type=Path, help="Local copy of the original AviList Explorer v2026 JSON.")
    p.add_argument("--photos", type=Path, help="Local copy of the pinned Avicommons 2025 JSON.")
    p.add_argument("--output", type=Path, default=REPO / "data" / "observations.json")
    args = p.parse_args()
    if args.photos:
        content = args.photos.read_bytes()
    else:
        request = Request(INDEX_URL, headers={"User-Agent": "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"})
        with urlopen(request, timeout=120) as response:
            content = response.read()
    if hashlib.sha256(content).hexdigest() != INDEX_SHA256:
        raise ValueError("Unexpected Avicommons snapshot; review the source before updating.")
    photos = json.loads(content)
    images, skipped = import_images(photos, avi.read_source(args.taxonomy))
    if len(images) != 8631:
        raise ValueError(f"Expected 8,631 matched species in this snapshot, found {len(images)}.")
    write_catalog(images, args.output)
    print(f"Accepted {len(images):,} / {len(photos):,} source entries. Exclusions: {dict(skipped)}")


if __name__ == "__main__":
    main()
