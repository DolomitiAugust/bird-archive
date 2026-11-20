"""Extract the English order and family names approved in AviList v2026."""

import argparse
import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from import_checklist import CITATION, ROOT, SOURCE, VERSION, read_source


def build_labels(rows):
    groups = {"order": {}, "family": {}}
    for row in rows:
        rank = row[1]
        if rank not in groups:
            continue
        scientific, english = row[5], row[8]
        if not scientific or not english or scientific in groups[rank]:
            raise ValueError(f"Missing or repeated {rank} at AviList row {row[0]}")
        groups[rank][scientific] = english

    species = [row for row in rows if row[1] == "species"]
    for rank, column, expected in (("order", 2, 45), ("family", 3, 250)):
        if len(groups[rank]) != expected or set(groups[rank]) != {row[column] for row in species}:
            raise ValueError(f"The {rank} names do not cover the reviewed species checklist")

    return {
        "version": VERSION, "source": SOURCE, "citation": CITATION,
        "license": "CC BY 4.0", "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
        "changes": "Selected scientific and English names from order and family rows; retained AviList spelling and sequence.",
        "orders": groups["order"], "families": groups["family"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Local copy of the official AviList v2026 Explorer JSON")
    parser.add_argument("--output", type=Path, default=ROOT / "data/taxon-labels-en.json")
    args = parser.parse_args()
    labels = build_labels(read_source(args.input))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=args.output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(labels, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        temporary.replace(args.output)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    print(f"Wrote {len(labels['orders'])} order and {len(labels['families'])} family names")


if __name__ == "__main__":
    main()
