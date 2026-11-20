"""Rebuild the Chinese name index, matching published names to AviList taxa."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
import hashlib
from http.client import IncompleteRead, RemoteDisconnected
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

import import_checklist as avilist


ROOT = Path(__file__).resolve().parents[1]
VERSION = "v0.5-Nov2026"
RELEASE = f"https://github.com/birdnet-team/birdnet-taxonomy/releases/download/{VERSION}"
ZIP_NAME = f"BirdNET_Taxonomy_{VERSION}.zip"
ZIP_SHA256 = "6fd24ab69532dcbffa6c53061e55118afe367f94ef06f100f1f386ca5d5421a1"
USER_AGENT = "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"
LOCALES = ("zh-cn", "zh-hans", "zh", "zh-tw", "zh-hant", "zh-hk", "zh-tra", "zh-sg", "zh-my")
HAN = re.compile(r"[\u3400-\u9fff\U00020000-\U000323af]")
WIKIDATA = "https://query.wikidata.org/sparql"
IOC_URL = "https://hosted-datasets.gbif.org/datasets/ioc.zip"
IOC_SHA256 = "982e729f1abf8e2e1b36757f27e521f373bd8ce1e9a13b2fc0c9a09fad8d1c9b"
ZH_NAME = re.compile(r"[\u3400-\u9fff\U00020000-\U000323af]+")


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
        except (URLError, ConnectionError, TimeoutError, IncompleteRead, RemoteDisconnected):
            if attempt == 2:
                raise
            time.sleep(4 * (attempt + 1))


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
    suffix = {"Q35409": "科", "Q36602": "目"}.get(rank, "")
    properties = "rdfs:label wdt:P1843 skos:altLabel" if suffix else "rdfs:label"
    for start in range(0, len(latin_names), 30):
        batch = " ".join(json.dumps(name) for name in latin_names[start:start + 30])
        query = f"""SELECT DISTINCT ?latin ?item ?label ?property ?avibase WHERE {{
            VALUES ?latin {{ {batch} }}
            VALUES ?property {{ {properties} }}
            ?item wdt:P225 ?latin; wdt:P105 wd:{rank}; ?property ?label.
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
            label = row["label"]["value"]
            if not label.endswith(suffix) or not HAN.search(label):
                continue
            language = row["label"]["xml:lang"]
            prop = row["property"]["value"]
            # Prefer an item's main label to a common name statement or alias.
            priority = 0 if prop.endswith("#label") else 1 if prop.endswith("/P1843") else 2
            value = (priority, label)
            if language not in localized or value < localized[language]:
                localized[language] = value
        for latin, items in candidates.items():
            if len(items) != 1:
                continue
            qid, localized = next(iter(items.items()))
            # A monotypic family can share an item/page with its genus or species.
            # Only show a label that actually names the requested rank.
            record = name_record({lang: value[1] for lang, value in localized.items()}, suffix)
            if record:
                output[latin] = {**record, "wikidata": qid}
    return output


def comparable(value):
    # Orthographic punctuation/accents do not change an authority or English name.
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value or "").lower())


def same_authority(first, second):
    # IOC often supplies author initials omitted by AviList (e.g. "Forster, JR, 1844").
    # Keep both full surnames and the publication year when there are co-authors.
    initials = r",\s*(?:[A-Z]\.?){1,3}(?=\s*[,\)&])"
    return comparable(re.sub(initials, "", first)) == comparable(re.sub(initials, "", second))


def add_ioc_names(names, avilist_rows, ioc_archive):
    data = ioc_archive.read_bytes() if ioc_archive else read_url(IOC_URL)
    if hashlib.sha256(data).hexdigest() != IOC_SHA256:
        raise ValueError("The IOC archive has changed. Review its version and provenance.")
    taxa = {}
    children = defaultdict(set)
    common = defaultdict(lambda: defaultdict(list))
    with ZipFile(io.BytesIO(data)) as bundle:
        with bundle.open("NameUsage.tsv") as handle:
            for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"), delimiter="\t"):
                if row["col:status"] != "accepted":
                    continue
                if row["col:rank"] == "species":
                    taxa[row["col:scientificName"]] = row
                elif row["col:rank"] == "subspecies":
                    children[row["col:parentID"]].add(row["col:scientificName"])
        with bundle.open("VernacularName.tsv") as handle:
            for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"), delimiter="\t"):
                if row["col:language"] in ("eng", "zho"):
                    common[row["col:taxonID"]][row["col:language"]].append(row["col:name"])
    avilist_children = defaultdict(set)
    for row in avilist_rows:
        if row[1] == "subspecies":
            avilist_children[" ".join(row[5].split()[:2])].add(row[5])
    for row in avilist_rows:
        latin = row[5]
        if row[1] != "species" or latin not in taxa:
            continue
        taxon = taxa[latin]
        key = taxon["col:ID"]
        loc = common[key]
        if (not row[6] or not same_authority(row[6], taxon["col:authorship"])
                or comparable(row[8]) not in {comparable(n) for n in loc["eng"]}
                or avilist_children[latin] != children[key]):
            continue
        labels = [label for label in loc["zho"] if ZH_NAME.fullmatch(label)]
        if not labels:
            continue
        existing = names.get(latin)
        if not existing:
            names[latin] = {"zh": labels[0], "aliases": labels[1:], "ioc": True}
        else:
            added = [label for label in labels if label not in [existing["zh"], *existing["aliases"]]]
            if added:
                existing["aliases"].extend(added)
                existing["ioc"] = True


def gbif_rank(requested):
    latin, rank, suffix = requested
    base = "https://api.gbif.org/v1/species"
    params = {"name": latin, "rank": rank, "class": "Aves", "kingdom": "Animalia", "strict": "true"}
    match = json.loads(read_url(base + "/match?" + urlencode(params)))
    if (match.get("matchType"), match.get("rank"), match.get("class"), match.get("canonicalName"),
            match.get("status")) != ("EXACT", rank, "Aves", latin, "ACCEPTED"):
        return latin, None
    key = match["usageKey"]
    page = json.loads(read_url(f"{base}/{key}/vernacularNames?limit=1000"))
    if not page["endOfRecords"]:
        raise ValueError(f"Incomplete GBIF vernacular records for {latin}")
    labels = []
    for row in page["results"]:
        label = row["vernacularName"]
        if (row.get("language") == "zho" and row.get("source") == "Catalogue of Life"
                and ZH_NAME.fullmatch(label) and label.endswith(suffix) and label not in labels):
            labels.append(label)
    return latin, {"zh": labels[0], "aliases": labels[1:], "gbif": key} if labels else None


def rank_names(birds, field, rank, suffix):
    latin_names = {bird[field] for bird in birds}
    qid = {"ORDER": "Q36602", "FAMILY": "Q35409"}[rank]
    result = wikidata_names(latin_names, qid)
    add_reviewed_names(result, field, latin_names, suffix)
    remaining = [(name, rank, suffix) for name in sorted(latin_names - result.keys())]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for latin, record in pool.map(gbif_rank, remaining):
            if record:
                result[latin] = record
    return result


def add_reviewed_names(result, field, latin_names, suffix=""):
    evidence = Path(__file__).with_name("reviewed_zh_names.tsv")
    with evidence.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            latin, zh, revision = row["latin"], row["zh"], row["wikipedia_revision"]
            if row["rank"] != field or latin not in latin_names or latin in result:
                continue
            if not ZH_NAME.fullmatch(zh) or not zh.endswith(suffix) or not revision.isdecimal():
                raise ValueError(f"Invalid reviewed taxon name: {row}")
            result[latin] = {"zh": zh, "aliases": [], "wikiRevision": int(revision)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checklist", type=Path, default=ROOT / "data/checklist.json")
    parser.add_argument("--birdnet-zip", type=Path, help="Already downloaded, unmodified release ZIP")
    parser.add_argument("--ioc-zip", type=Path, help="Original IOC v15.2 GBIF archive.")
    parser.add_argument("--avilist-json", type=Path, help="Original AviList v2026 Explorer JSON, including subspecies.")
    parser.add_argument("--output", type=Path, default=ROOT / "data/chinese-names.json")
    args = parser.parse_args()
    catalog = json.loads(args.checklist.read_text(encoding="utf-8"))
    birds = catalog["species"]
    names = read_birdnet(birds, args.birdnet_zip)
    missing = {bird["latin"]: bird["id"].removeprefix("avibase-").upper()
               for bird in birds if bird["latin"] not in names}
    names.update(wikidata_names(missing, "Q7432", missing))
    avilist_rows = avilist.read_source(args.avilist_json)
    add_ioc_names(names, avilist_rows, args.ioc_zip)
    add_reviewed_names(names, "species", {bird["latin"] for bird in birds})
    orders = rank_names(birds, "order", "ORDER", "目")
    families = rank_names(birds, "family", "FAMILY", "科")
    document = {
        "source": f"BirdNET+ Taxonomy {VERSION}；Wikidata；IOC World Bird List v15.2；GBIF Backbone Taxonomy；中文维基百科",
        "creator": "BirdNET Team；Wikidata contributors；Gill, Donsker & Rasmussen (eds.) / International Ornithologists Union；GBIF Secretariat / Catalogue of Life；中文维基百科贡献者",
        "sourceUrl": "https://birdnet.cornell.edu/taxonomy/about#license",
        "license": "CC BY-SA 4.0",
        "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/",
        "wikidataLicense": "https://www.wikidata.org/wiki/Wikidata:Licensing",
        "additionalSources": [
            {"name": "IOC World Bird List v15.2, GBIF 数据包", "url": "https://doi.org/10.15468/anfqn6",
             "license": "CC BY 4.0", "licenseUrl": "https://creativecommons.org/licenses/by/4.0/"},
            {"name": "GBIF Backbone Taxonomy / Catalogue of Life", "url": "https://doi.org/10.15468/39omei",
             "license": "CC BY 4.0", "licenseUrl": "https://creativecommons.org/licenses/by/4.0/"},
            {"name": "中文维基百科贡献者，见各条目固定版本", "urlTemplate": "https://zh.wikipedia.org/w/index.php?oldid={wikiRevision}",
             "license": "CC BY-SA 4.0", "licenseUrl": "https://creativecommons.org/licenses/by-sa/4.0/"}
        ],
        "taxonomy": catalog["version"],
        "changes": "按学名及阶元对应 AviList，核对可用的 Avibase 编号；合并地区名为检索别名。wikidata 指向原条目（CC0）。ioc 标示有名称取自 IOC v15.2，在学名、命名人和年份、英文名及亚种组成均吻合时使用。gbif 标示 GBIF Backbone 所收 Catalogue of Life 的中文阶元名。wikiRevision 标示据中文维基百科固定版本中并列的拉丁阶元与中文名人工摘录。",
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
