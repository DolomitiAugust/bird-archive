"""Build the species index from the official AviList v2026 Explorer snapshot."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
VERSION = "v2026"
SOURCE = "https://www.avilist.org/checklist/v2026/"
DATA_URL = "https://explore.avilist.org/data/avilist-2026.json"
SHA256 = "0f00995c819903e35eaee65cf5313193868362f1a6383e05949fe3d3600a8b39"
EXPECTED_SPECIES = 11172
CITATION = "AviList Core Team. 2026. AviList: The Global Avian Checklist, v2026. https://doi.org/10.2173/avilist.v2026"


def read_source(local_file):
    if local_file is not None:
        content = local_file.read_bytes()
    else:
        request = Request(DATA_URL, headers={"User-Agent": "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"})
        with urlopen(request, timeout=120) as response:
            content = response.read()
    if hashlib.sha256(content).hexdigest() != SHA256:
        raise ValueError("The input differs from the reviewed v2026 snapshot. Check the source and schema before updating.")
    return json.loads(content)


def make_records(rows):
    records = []
    identifiers = set()
    scientific_names = set()
    for row in rows:
        if row[1] != "species":
            continue
        # Column order in the versioned AviList Explorer download, documented in data/AVILIST.md.
        order, family, latin, english = row[2], row[3], row[5], row[8]
        geographic_range, extinction, identifier = row[13], row[14], row[19]
        if not all(isinstance(value, str) and value.strip() for value in [order, family, latin, english, geographic_range]):
            raise ValueError(f"Missing required species fields at source row {row[0]}")
        if not re.fullmatch(r"avibase-[0-9A-F]{8}", identifier or "") or len(latin.split()) != 2:
            raise ValueError(f"Unexpected species identifier or scientific name: {identifier}, {latin}")
        if identifier in identifiers or latin in scientific_names:
            raise ValueError(f"Duplicate species: {identifier}, {latin}")
        identifiers.add(identifier)
        scientific_names.add(latin)
        record = {
            "id": identifier, "en": english, "latin": latin, "order": order,
            "family": family, "genus": latin.split()[0], "range": geographic_range,
        }
        if extinction:
            record["extinction"] = extinction
        records.append(record)
    if len(records) != EXPECTED_SPECIES:
        raise ValueError(f"Expected {EXPECTED_SPECIES} species, received {len(records)}")
    return records


def write_index(records, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    # One species per line keeps individual changes reviewable in Git.
    metadata = {
        "version": VERSION, "source": SOURCE, "citation": CITATION,
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }
    header = json.dumps(metadata, ensure_ascii=False, indent=2)[:-2]
    rows = [json.dumps(record, ensure_ascii=False, separators=(",", ":")) for record in records]
    content = header + ',\n  "species": [\n' + ',\n'.join(rows) + '\n  ]\n}\n'
    with NamedTemporaryFile(dir=output.parent, delete=False) as handle:
        temp = Path(handle.name)
    try:
        temp.write_bytes(content.encode("utf-8"))
        temp.replace(output)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Use a downloaded copy of the official v2026 Explorer JSON.")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "checklist.json")
    args = parser.parse_args()
    records = make_records(read_source(args.input))
    write_index(records, args.output)
    print(f"AviList {VERSION}: wrote {len(records):,} species to {args.output}")


if __name__ == "__main__":
    main()
