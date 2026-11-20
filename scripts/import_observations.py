"""Build the traceable Avicommons and BirdNET+ iNaturalist photo index for AviList."""

import argparse
from collections import Counter, defaultdict
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen
from zipfile import ZipFile

import import_checklist as avi


REPO = Path(__file__).resolve().parents[1]
COMMIT = "44305ddac3df99474e8f0fca33b23907ca35eedb"
INDEX_URL = f"https://raw.githubusercontent.com/rawcomposition/avicommons/{COMMIT}/public/2025.json"
INDEX_SHA256 = "3fce5e48eec0f9136c341dfc29752b970505ffe4a43c45af6c223acecee117de"
BIRDNET_RELEASE = "v0.5-Nov2026"
BIRDNET_STEM = f"BirdNET_Taxonomy_{BIRDNET_RELEASE}"
BIRDNET_ARCHIVE = f"https://github.com/birdnet-team/birdnet-taxonomy/releases/download/{BIRDNET_RELEASE}/{BIRDNET_STEM}.zip"
BIRDNET_SHA256 = "6fd24ab69532dcbffa6c53061e55118afe367f94ef06f100f1f386ca5d5421a1"
INAT_PHOTO_PATH = re.compile(r"/photos/([0-9]+)/")
INAT_OPEN_IMAGE = re.compile(r"https://inaturalist-open-data\.s3\.amazonaws\.com/photos/([0-9]+)/large\.(jpe?g|png)", re.IGNORECASE)
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
            "sourceId": "avicommons", "id": key, "photoId": key, "scientificName": taxon[5],
            "author": photo["by"], "license": license_name, "licenseUrl": license_url,
            "sourceUrl": original, "filePage": original, "imageUrl": media + "900.jpg",
            "thumbUrl": media + "320.jpg",
        }
    return eligible, skipped


def add_birdnet_images(images, avicommons, taxonomy, birdnet):
    taxa = {r[19]: r for r in taxonomy if r[1] == "species"}
    cornell = {r[17]: r[19] for r in taxa.values() if r[17]}
    associated = defaultdict(set)
    for photo in avicommons:
        if photo["key"].isdecimal():
            associated[photo["key"]].add(cornell.get(photo["code"], "unresolved:" + photo["code"]))
    for bird in birdnet:
        url = (bird.get("image") or {}).get("src") or ""
        match = INAT_PHOTO_PATH.search(url)
        if match:
            associated[match[1]].add("avibase-" + str(bird["avibase_id"]))

    skipped = Counter()
    before = len(images)
    for bird in birdnet:
        taxon_id = "avibase-" + str(bird["avibase_id"])
        taxon = taxa.get(taxon_id)
        if bird["taxon_group"] != "Aves" or bird["record_type"] != "species" or taxon is None:
            continue
        if taxon_id in images or bird["scientific_name"] != taxon[5]:
            continue
        if taxon[14] and "reintroduced" not in taxon[14].lower():
            skipped["extinction flag needs review"] += 1
            continue
        if bird["image_source"] != "iNaturalist":
            skipped["not iNaturalist photography"] += 1
            continue
        label = bird["image_license"]
        if label not in SHORT_LICENSES:
            skipped["unverified or excluded license"] += 1
            continue
        author = (bird["image_author"] or "").strip()
        if not author or author.lower() in {"unknown", "anonymous", "unknown author", "no rights reserved", "n/a"}:
            skipped["missing photographer credit"] += 1
            continue
        url = bird["image"]["src"]
        match = INAT_OPEN_IMAGE.fullmatch(url)
        if not match:
            skipped["unverified photo host or format"] += 1
            continue
        key = match[1]
        if associated[key] != {taxon_id}:
            skipped["ambiguous photo ID across taxa"] += 1
            continue
        original = f"https://www.inaturalist.org/photos/{key}"
        license_name, license_url = license_details(label)
        images[taxon_id] = {
            "sourceId": "birdnet-inaturalist", "id": key, "photoId": key, "scientificName": taxon[5],
            "author": author, "license": license_name, "licenseUrl": license_url,
            "sourceUrl": original, "filePage": original, "imageUrl": url,
            "thumbUrl": url.replace("/large.", "/medium."),
        }
    return len(images) - before, skipped


def write_catalog(photos, output):
    metadata = {
        "sourceId": "inaturalist-photos", "source": "Avicommons · BirdNET+ · iNaturalist",
        "sourceUrl": "https://avicommons.org/", "version": "Avicommons 2025 / BirdNET+ v0.5-Nov2026",
        "sources": {
            "avicommons": {"url": "https://avicommons.org/", "version": "eBird/Clements 2025"},
            "birdnet-inaturalist": {"url": "https://birdnet.cornell.edu/taxonomy/download", "version": BIRDNET_RELEASE,
                "metadataLicense": "https://creativecommons.org/licenses/by-sa/4.0/"},
        },
        "license": "Each photograph retains its individual Creative Commons license.",
        "attribution": "Avicommons (Adam Jackson); BirdNET+ Taxonomy v0.5-Nov2026 (birdnet.cornell.edu/taxonomy, CC BY-SA 4.0). Original photographers credited per image.",
        "provenance": "iNaturalist photographs identified by source photo ID. Index derived by selection, normalization and exact matching to AviList. Field conditions and research grade are not individually verified.",
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


def verified_download(path, url, sha256):
    if path:
        content = path.read_bytes()
    else:
        request = Request(url, headers={"User-Agent": "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"})
        with urlopen(request, timeout=120) as response:
            content = response.read()
    if hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError(f"Unexpected snapshot for {url}; review the source before updating.")
    return content


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--taxonomy", type=Path, help="Local copy of the original AviList Explorer v2026 JSON.")
    p.add_argument("--photos", type=Path, help="Local copy of the pinned Avicommons 2025 JSON.")
    p.add_argument("--birdnet", type=Path, help="Local copy of the official BirdNET+ v0.5-Nov2026 ZIP release.")
    p.add_argument("--output", type=Path, default=REPO / "data" / "observations.json")
    args = p.parse_args()
    photos = json.loads(verified_download(args.photos, INDEX_URL, INDEX_SHA256))
    taxonomy = avi.read_source(args.taxonomy)
    images, skipped = import_images(photos, taxonomy)
    if len(images) != 8631:
        raise ValueError(f"Expected 8,631 matched species in this snapshot, found {len(images)}.")
    print(f"Accepted {len(images):,} / {len(photos):,} source entries. Exclusions: {dict(skipped)}")
    with ZipFile(BytesIO(verified_download(args.birdnet, BIRDNET_ARCHIVE, BIRDNET_SHA256))) as archive:
        with archive.open(BIRDNET_STEM + ".json") as stream:
            additions, excluded = add_birdnet_images(images, photos, taxonomy, json.load(stream))
    if additions != 1324 or len({r["photoId"] for r in images.values()}) != len(images):
        raise ValueError("Unexpected coverage or duplicate photo ID across sources.")
    write_catalog(images, args.output)
    print(f"Added {additions:,} BirdNET+ photos. Total {len(images):,}. Exclusions: {dict(excluded)}")


if __name__ == "__main__":
    main()
