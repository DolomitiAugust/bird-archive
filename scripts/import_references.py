"""Build per-species links to external archives from verified source identifiers."""

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from zipfile import ZipFile

import import_checklist as avilist
import import_chinese_names as birdnet


def birdnet_links(archive, identifiers):
    """Crosswalk only exact Avibase ID + binomial matches; reject ambiguous IDs."""
    data = archive.read_bytes() if archive else birdnet.read_url(f"{birdnet.RELEASE}/{birdnet.ZIP_NAME}")
    if hashlib.sha256(data).hexdigest() != birdnet.ZIP_SHA256:
        raise ValueError("Unexpected BirdNET+ archive checksum")
    links = {}
    used = {"inat": set(), "gbif": set()}
    with ZipFile(io.BytesIO(data)) as bundle:
        with bundle.open(f"BirdNET_Taxonomy_{birdnet.VERSION}.csv") as csv_file:
            rows = csv.DictReader(io.TextIOWrapper(csv_file, encoding="utf-8-sig"))
            for row in rows:
                if row["taxon_group"] != "Aves" or row["record_type"] != "species":
                    continue
                identifier = "avibase-" + row["avibase_id"].upper()
                if identifiers.get(identifier) != row["scientific_name"]:
                    continue
                if identifier in links:
                    raise ValueError(f"Duplicate BirdNET+ species: {identifier}")
                record = {}
                for source, key in (("inat", "inat_id"), ("gbif", "gbif_id")):
                    value = row[key]
                    if not value:
                        continue
                    if not re.fullmatch(r"[1-9][0-9]*", value) or value in used[source]:
                        raise ValueError(f"Invalid or ambiguous {source} identifier: {value}")
                    record[source] = int(value)
                    used[source].add(value)
                links[identifier] = record
    return links


def avilist_links(row):
    """Validate the exact published targets, not a URL guessed from a bird's name."""
    record = {}
    for field, column, pattern in (
        ("ebird", 17, r"[a-z0-9]+"),
        ("birdlife", 16, r"https://datazone\.birdlife\.org/species/factsheet/[0-9]+"),
        ("bow", 18, r"https://birdsoftheworld\.org/bow/species/[a-z0-9]+"),
    ):
        value = row[column]
        if value:
            if not re.fullmatch(pattern, value):
                raise ValueError(f"Unexpected AviList {field} destination for {row[5]}: {value}")
            record[field] = value
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--avilist-json", type=Path, help="Local copy of the reviewed AviList v2026 source.")
    parser.add_argument("--birdnet-zip", type=Path, help="Local copy of the original BirdNET+ release.")
    parser.add_argument("--output", type=Path, default=avilist.ROOT / "data/references.json")
    args = parser.parse_args()
    rows = avilist.read_source(args.avilist_json)
    identifiers = {bird["id"]: bird["latin"] for bird in avilist.make_records(rows)}
    extra = birdnet_links(args.birdnet_zip, identifiers)
    records = {}
    for row in rows:
        if row[1] == "species":
            links = avilist_links(row)
            links.update(extra.get(row[19], {}))
            if links:
                records[row[19]] = links
    metadata = {
        "source": f"AviList {avilist.VERSION}; BirdNET+ Taxonomy {birdnet.VERSION}",
        "license": "CC BY-SA 4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "sources": [
            {"fields": ["ebird", "birdlife", "bow"], "credit": avilist.CITATION, "url": avilist.SOURCE,
             "license": "CC BY 4.0", "licenseUrl": "https://creativecommons.org/licenses/by/4.0/"},
            {"fields": ["inat", "gbif"], "credit": f"BirdNET Team, BirdNET+ Taxonomy {birdnet.VERSION}",
             "url": "https://birdnet.cornell.edu/taxonomy/about#license",
             "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/"}
        ],
        "changes": "按物种抽取 AviList 的科内尔物种代号、BirdLife 和 Birds of the World 档案地址。以学名和 Avibase 编号双重对应 BirdNET+ 行，抽取 iNaturalist 和 GBIF 标识。只关联外部资料，所链接媒体保留各自许可。",
    }
    # Keep one record per line for reviewing taxonomy upgrades in version control.
    header = json.dumps(metadata, ensure_ascii=False, indent=2)[:-2]
    items = [f'    "{key}":{json.dumps(detail, separators=(",", ":"))}' for key, detail in sorted(records.items())]
    document = header + ',\n  "species": {\n' + ',\n'.join(items) + '\n  }\n}\n'
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with NamedTemporaryFile(dir=args.output.parent, delete=False) as handle:
        staging = Path(handle.name)
    try:
        staging.write_text(document, encoding="utf-8")
        staging.replace(args.output)
    finally:
        staging.unlink(missing_ok=True)
    print(f"External archive links: {len(records)} of {len(identifiers)} species")


if __name__ == "__main__":
    main()
