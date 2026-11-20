"""Find existing Chinese Wikipedia accounts for species whose current account is in English."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen
from zipfile import ZipFile

from import_accounts import excerpt
from import_chinese_names import USER_AGENT, ZIP_NAME, ZIP_SHA256


ROOT = Path(__file__).resolve().parents[1]
WDQS = "https://query.wikidata.org/sparql"
WIKI = "https://zh.wikipedia.org/w/api.php"


def wait_time(response, fallback):
    value = response.headers.get("Retry-After", "")
    if value.isdecimal():
        return max(1, int(value))
    if value:
        try:
            return max(1, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError):
            pass
    return fallback


def request_json(endpoint, params):
    url = endpoint + "?" + urlencode(params)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/sparql-results+json"})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=45) as response:
                payload = json.load(response)
                error = payload.get("error")
                if not error:
                    return payload
                if error.get("code") != "maxlag":
                    raise ValueError(error.get("info", str(error)))
                delay = wait_time(response, 5 * (attempt + 1))
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504}:
                raise
            delay = wait_time(error, 5 * (attempt + 1))
        except (TimeoutError, URLError):
            delay = 5 * (attempt + 1)
        if attempt < 3:
            time.sleep(delay)
    raise RuntimeError(f"Could not read {endpoint} after four attempts")


def load_targets(root, archive):
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIP_SHA256:
        raise ValueError("Unexpected BirdNET+ release checksum")
    catalog = json.loads((root / "data/checklist.json").read_text(encoding="utf-8"))
    ids = {r["latin"]: r["id"] for r in catalog["species"]}
    english = set()
    for path in (root / "data/accounts").glob("*.json"):
        accounts = json.loads(path.read_text(encoding="utf-8"))
        english.update(sid for sid, account in accounts.items() if account["lang"] == "en")
    with ZipFile(archive) as package:
        all_rows = json.loads(package.read(ZIP_NAME.replace(".zip", ".json")))
    by_qid = defaultdict(list)
    for row in all_rows:
        latin = row["scientific_name"]
        sid = ids.get(latin)
        qid = row.get("wikidata_qid") or ""
        if sid not in english or row["taxon_group"] != "Aves" or row["record_type"] != "species":
            continue
        if not re.fullmatch(r"Q[1-9]\d*", qid):
            continue
        if row.get("avibase_id") and sid != "avibase-" + row["avibase_id"].upper():
            continue
        linked = urlsplit((row.get("wikipedia_urls") or {}).get("zh", ""))
        title = ""
        if linked.scheme == "https" and linked.hostname == "zh.wikipedia.org" and linked.path.startswith("/wiki/"):
            title = unquote(linked.path[len("/wiki/"):]).replace("_", " ")
        by_qid[qid].append((sid, latin, title))
    # A QID shared by multiple accepted AviList species cannot identify one archive.
    return {qid: matches[0] for qid, matches in by_qid.items() if len(matches) == 1}


def chinese_pages(targets):
    values = " ".join("wd:" + qid for qid in targets)
    query = f"""SELECT DISTINCT ?item ?title ?latin ?avibase WHERE {{
      VALUES ?item {{ {values} }}
      ?page schema:about ?item; schema:isPartOf <https://zh.wikipedia.org/>; schema:name ?title.
      ?item wdt:P105 wd:Q7432.
      OPTIONAL {{ ?item wdt:P225 ?latin }}
      OPTIONAL {{ ?item wdt:P2026 ?avibase }}
    }}"""
    rows = request_json(WDQS, {"query": query, "format": "json"})["results"]["bindings"]
    sitelinks = {}
    for row in rows:
        qid = row["item"]["value"].rsplit("/", 1)[1]
        sid, latin, _ = targets[qid]
        avibase = row.get("avibase", {}).get("value", "").upper()
        expected = sid.removeprefix("avibase-")
        if avibase and avibase[:8] != expected:
            continue
        if row.get("latin", {}).get("value") != latin and avibase[:8] != expected:
            continue
        sitelinks[qid] = row["title"]["value"]
    return sitelinks


def read_excerpts(titles, require_latin=None, fetch=request_json):
    result = fetch(WIKI, {
        "action": "query", "titles": "|".join(titles.values()),
        "prop": "extracts|revisions|pageprops", "exintro": 1, "explaintext": 1, "exlimit": "max",
        "rvprop": "ids", "ppprop": "wikibase_item|disambiguation", "redirects": 1, "converttitles": 1,
        "format": "json", "formatversion": 2, "maxlag": 5,
    })
    accounts = {}
    for page in result["query"]["pages"]:
        props = page.get("pageprops", {})
        qid = props.get("wikibase_item")
        if page.get("ns") != 0 or "disambiguation" in props or qid not in titles:
            continue
        revisions = page.get("revisions", [])
        introduction = page.get("extract", "")
        if require_latin and qid in require_latin and not re.search(r"(?<![A-Za-z])" + re.escape(require_latin[qid]) + r"(?![A-Za-z])", introduction):
            continue
        text = excerpt(introduction, "zh")
        if not text:
            # A long distribution sentence can fill the first paragraph; use another complete paragraph.
            for paragraph in introduction.splitlines()[1:]:
                text = excerpt(paragraph, "zh")
                if text:
                    break
        if not revisions or not re.search(r"[\u3400-\u9fff]", text):
            continue
        revision = revisions[0]["revid"]
        accounts[qid] = {
            "lang": "zh", "via": "wiki", "text": text, "qid": qid, "pageid": page["pageid"],
            "oldid": revision, "url": f"https://zh.wikipedia.org/w/index.php?oldid={revision}",
        }
    return accounts


def collect_by_name(root, archive, output, seconds, rank_verified_only=False):
    """Use known names, then scientific-name redirects, within a fixed time budget."""
    deadline = time.monotonic() + seconds
    data = root / "data"
    catalog = json.loads((data / "checklist.json").read_bytes())["species"]
    species = {row["latin"]: row["id"] for row in catalog}
    names = json.loads((data / "chinese-names.json").read_bytes())["names"]
    existing = {}
    for shard in (data / "accounts").glob("*.json"):
        existing.update(json.loads(shard.read_bytes()))
    featured = {row["latin"] for row in json.loads((data / "photos.json").read_bytes())}
    qids = {latin: {record["wikidata"]} for latin, record in names.items() if record.get("wikidata")}
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIP_SHA256:
        raise ValueError("Unexpected BirdNET+ release checksum")
    with ZipFile(archive) as package:
        for row in json.loads(package.read(ZIP_NAME.replace(".zip", ".json"))):
            latin, qid = row["scientific_name"], row.get("wikidata_qid") or ""
            if latin not in species or row["taxon_group"] != "Aves" or row["record_type"] != "species":
                continue
            if row.get("avibase_id") and species[latin] != "avibase-" + row["avibase_id"].upper():
                continue
            if re.fullmatch(r"Q[1-9]\d*", qid):
                qids.setdefault(latin, set()).add(qid)
    qid_counts = Counter(qid for values in qids.values() for qid in values)
    subjects = {next(iter(v)): k for k, v in qids.items() if len(v) == 1 and qid_counts[next(iter(v))] == 1}
    # The Chinese-name importer has already checked both P225 (exact scientific name)
    # and P105 (species rank) for records carrying its explicit wikidata identifier.
    verified_ranks = {qid for qid, latin in subjects.items() if names.get(latin, {}).get("wikidata") == qid}
    required_latin = {qid: latin for qid, latin in subjects.items() if qid not in verified_ranks}
    updates = json.loads(output.read_bytes()) if output.exists() else {}
    queue = sorted((q for q, latin in subjects.items() if existing.get(species[latin], {}).get("lang") != "zh"),
                   key=lambda q: (species[subjects[q]] in existing, subjects[q] not in featured, subjects[q]))
    if rank_verified_only:
        queue = [qid for qid in queue if qid in verified_ranks]

    def fetch(endpoint, params):
        remaining = deadline - time.monotonic()
        if remaining < 1:
            raise TimeoutError("Time budget reached")
        address = endpoint + "?" + urlencode(params)
        req = Request(address, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        with urlopen(req, timeout=min(12, remaining)) as response:
            payload = json.load(response)
        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return payload

    def save():
        output.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as tmp:
            temp = Path(tmp.name)
            json.dump(updates, tmp, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            tmp.write("\n")
        temp.replace(output)

    save()
    try:
        for start in range(0, len(queue), 20):
            batch = queue[start:start + 20]
            for by_latin in (False, True):
                titles = {}
                for qid in batch:
                    latin = subjects[qid]
                    if species[latin] in updates:
                        continue
                    title = latin if by_latin else names.get(latin, {}).get("zh")
                    if title:
                        titles[qid] = title
                if not titles:
                    continue
                found = read_excerpts(titles, required_latin, fetch)
                if found:
                    updates.update({species[subjects[qid]]: account for qid, account in found.items()})
                    save()
                time.sleep(0.5)
    except (HTTPError, TimeoutError, URLError, RuntimeError) as error:
        print(f"Collection paused: {error}")
    print(f"{len(updates)} checked Chinese accounts saved to {output}")


def save_accounts(root, updates):
    shards = defaultdict(dict)
    for sid, record in updates.items():
        shards[sid.removeprefix("avibase-")[:2].lower()][sid] = record
    saved = 0
    for prefix, records in shards.items():
        path = root / "data/accounts" / (prefix + ".json")
        shard = json.loads(path.read_text(encoding="utf-8"))
        changes = {sid: record for sid, record in records.items() if shard.get(sid, {}).get("lang") != "zh"}
        if not changes:
            continue
        shard.update(changes)
        with NamedTemporaryFile(dir=path.parent, mode="w", suffix=".part", encoding="utf-8", delete=False) as handle:
            temp = Path(handle.name)
            json.dump(shard, handle, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            handle.write("\n")
        try:
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
        saved += len(changes)
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--birdnet-zip", type=Path)
    parser.add_argument("--merge-supplement", type=Path, help="Import a reviewed by-name supplement into the Chinese-mode index.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--limit", type=int, help="Inspect only this many remaining English accounts")
    parser.add_argument("--linked-only", action="store_true", help="Check only the Chinese article links already present in BirdNET+")
    parser.add_argument("--by-name-output", type=Path, help="Look up Chinese or scientific names; save a separate JSON supplement and leave shards untouched")
    parser.add_argument("--seconds", type=int, default=165, help="Time limit in seconds for --by-name-output")
    parser.add_argument("--rank-verified-only", action="store_true", help="In name searches, only check QIDs already tied to the exact name and species rank by the Chinese-name importer")
    args = parser.parse_args()
    if args.merge_supplement:
        updates = json.loads(args.merge_supplement.read_bytes())
        ids = {row["id"] for row in json.loads((args.root / "data/checklist.json").read_bytes())["species"]}
        for sid, entry in updates.items():
            if (sid not in ids or entry.get("lang") != "zh" or entry.get("via") != "wiki"
                    or not entry.get("text") or not isinstance(entry.get("oldid"), int)
                    or entry.get("url") != f"https://zh.wikipedia.org/w/index.php?oldid={entry['oldid']}"):
                parser.error(f"Invalid species or revision in supplement: {sid}")
        print(f"{save_accounts(args.root, updates)} Chinese accounts imported")
        return
    if not args.birdnet_zip:
        parser.error("Provide --birdnet-zip to look up encyclopedia articles.")
    if args.by_name_output:
        collect_by_name(args.root, args.birdnet_zip, args.by_name_output, args.seconds, args.rank_verified_only)
        return
    targets = load_targets(args.root, args.birdnet_zip)
    queue = sorted(targets)
    if args.limit is not None:
        queue = queue[:max(0, args.limit)]
    stats = Counter()
    linked = [(qid, targets[qid][2]) for qid in queue if targets[qid][2]]
    recovered = set()
    for start in range(0, len(linked), 20):
        batch = dict(linked[start:start + 20])
        accounts = read_excerpts(batch, {qid: targets[qid][1] for qid in batch})
        updates = {}
        for qid, record in accounts.items():
            updates[targets[qid][0]] = record
            recovered.add(qid)
        stats["upgraded"] += save_accounts(args.root, updates)
        time.sleep(1)
    print(f"{len(linked)} existing article links checked, {stats['upgraded']} exact matches upgraded", flush=True)
    if args.linked_only:
        return
    queue = [qid for qid in queue if qid not in recovered]
    print(f"Checking {len(queue)} QIDs for Chinese Wikipedia pages", flush=True)
    for start in range(0, len(queue), 160):
        batch = {qid: targets[qid] for qid in queue[start:start + 160]}
        titles = chinese_pages(batch)
        stats["checked"] += len(batch)
        stats["sitelinks"] += len(titles)
        items = list(titles.items())
        for pos in range(0, len(items), 20):
            accounts = read_excerpts(dict(items[pos:pos + 20]))
            stats["upgraded"] += save_accounts(args.root, {targets[qid][0]: row for qid, row in accounts.items()})
            time.sleep(1)
        print(f"{stats['checked']}/{len(queue)} checked, {stats['sitelinks']} linked, {stats['upgraded']} upgraded", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
