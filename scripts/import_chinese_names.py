"""Rebuild the Chinese name index from BirdNET+ Taxonomy and Wikidata."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.5-Nov2026"
RELEASE = f"https://github.com/birdnet-team/birdnet-taxonomy/releases/download/{VERSION}"
ZIP_NAME = f"BirdNET_Taxonomy_{VERSION}.zip"
ZIP_SHA256 = "6fd24ab69532dcbffa6c53061e55118afe367f94ef06f100f1f386ca5d5421a1"
USER_AGENT = "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"
LOCALES = ("zh-cn", "zh-hans", "zh", "zh-tw", "zh-hant", "zh-hk", "zh-tra", "zh-sg", "zh-my")
HAN = re.compile(r"[\u3400-\u9fff\U00020000-\U000323af]")
WIKIDATA = "https://query.wikidata.org/sparql"


def read_url(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=90) as response:
                return response.read()
        except HTTPError as exc:
            if attempt == 2 or exc.code not in (429, 502, 503, 504):
                raise
            retry_after = exc.headers.get("Retry-After", "")
            time.sleep(int(retry_after) if retry_after.isdecimal() else 4 * (attempt + 1))


def name_record(localized, suffix=""):
    """Prefer explicitly localized names and discard empty/Latin-name fallbacks."""
    values = []
    for language in LOCALES:
        name = localized.get(language, "").strip()
        if HAN.search(name) and name.endswith(suffix) and name not in values:
            values.append(name)
    return {"zh": values[0], "aliases": values[1:]} if values else None


def read_birdnet(checklist, archive):
    data = archive.read_bytes() if archive else read_url(f"{RELEASE}/{ZIP_NAME}")
    if hashlib.sha256(data).hexdigest() != ZIP_SHA256:
        raise ValueError("BirdNET+ archive differs from the published release checksum")
    with ZipFile(io.BytesIO(data)) as bundle:
        with bundle.open(f"BirdNET_Taxonomy_{VERSION}.json") as handle:
            rows = json.load(handle)
    ids = {bird["latin"]: bird["id"].removeprefix("avibase-").upper() for bird in checklist}
    names = {}
    for row in rows:
        latin = row["scientific_name"]
        if row["taxon_group"] != "Aves" or row["record_type"] != "species" or latin not in ids:
            continue
        if row.get("avibase_id") and row["avibase_id"].upper() != ids[latin]:
            continue
        localized = {key.lower().replace("_", "-"): value for key, value in row["common_names"].items()}
        record = name_record(localized)
        if record:
            if latin in names:
                raise ValueError(f"Multiple BirdNET+ species have the same scientific name: {latin}")
            names[latin] = record
    return names


def wikidata_names(latin_names, rank, expected_ids=None):
    """Use exact scientific name and rank; omit ambiguous items or conflicting IDs."""
    latin_names = sorted(latin_names)
    output = {}
    languages = ", ".join(json.dumps(code) for code in LOCALES)
    for start in range(0, len(latin_names), 30):
        batch = " ".join(json.dumps(name) for name in latin_names[start:start + 30])
        query = f"""SELECT DISTINCT ?latin ?item ?label ?avibase WHERE {{
            VALUES ?latin {{ {batch} }}
            ?item wdt:P225 ?latin; wdt:P105 wd:{rank}; rdfs:label ?label.
            FILTER (LANG(?label) IN ({languages}))
            OPTIONAL {{ ?item wdt:P2026 ?avibase }}
        }}"""
        result = json.loads(read_url(WIKIDATA + "?" + urlencode({"query": query, "format": "json"})))
        candidates = {}
        for row in result["results"]["bindings"]:
            latin = row["latin"]["value"]
            comparable_id = row.get("avibase", {}).get("value", "").upper()
            if expected_ids and comparable_id and comparable_id[:8] != expected_ids[latin]:
                continue
            qid = row["item"]["value"].rsplit("/", 1)[1]
            localized = candidates.setdefault(latin, {}).setdefault(qid, {})
            localized[row["label"]["xml:lang"]] = row["label"]["value"]
        for latin, items in candidates.items():
            if len(items) != 1:
                continue
            qid, localized = next(iter(items.items()))
            # A monotypic family can share an item/page with its genus or species.
            # Only show a label that actually names the requested rank.
            suffix = {"Q35409": "科", "Q36602": "目"}.get(rank, "")
            record = name_record(localized, suffix)
            if record:
                output[latin] = {**record, "wikidata": qid}
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", type=Path, default=ROOT / "data/checklist.json")
    parser.add_argument("--birdnet-zip", type=Path, help="Already downloaded, unmodified release ZIP")
    parser.add_argument("--output", type=Path, default=ROOT / "data/chinese-names.json")
    args = parser.parse_args()
    catalog = json.loads(args.checklist.read_text(encoding="utf-8"))
    birds = catalog["species"]
    names = read_birdnet(birds, args.birdnet_zip)
    missing = {bird["latin"]: bird["id"].removeprefix("avibase-").upper()
               for bird in birds if bird["latin"] not in names}
    names.update(wikidata_names(missing, "Q7432", missing))
    orders = wikidata_names({bird["order"] for bird in birds}, "Q36602")
    families = wikidata_names({bird["family"] for bird in birds}, "Q35409")
    document = {
        "source": f"BirdNET+ Taxonomy {VERSION}；Wikidata",
        "creator": "BirdNET Team；Wikidata contributors",
        "sourceUrl": "https://birdnet.cornell.edu/taxonomy/about#license",
        "license": "CC BY-SA 4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "wikidataLicense": "https://www.wikidata.org/wiki/Wikidata:Licensing",
        "taxonomy": catalog["version"],
        "changes": "按学名与分类阶元对应 AviList，核对可用的 Avibase 编号。提取中文名称，合并不同中文地区用名作为检索别名。带 wikidata 字段的记录取自该 Wikidata 条目（CC0）。",
        "names": dict(sorted(names.items())),
        "orders": dict(sorted(orders.items())),
        "families": dict(sorted(families.items())),
    }
    args.output.parent.mkdir(exist_ok=True, parents=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", delete=False,
                                     dir=args.output.parent, suffix=".tmp") as handle:
        staging = Path(handle.name)
    try:
        staging.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n",
                           encoding="utf-8")
        os.replace(staging, args.output)
    finally:
        staging.unlink(missing_ok=True)
    print(f"Chinese names: {len(names)}/{len(birds)} species; {len(orders)} orders; {len(families)} families")


if __name__ == "__main__":
    main()
