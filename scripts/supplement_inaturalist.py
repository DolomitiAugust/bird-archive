"""Fill remaining exact taxon matches using the public iNaturalist v2 API."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zipfile import ZipFile

from import_observations import BIRDNET_STEM, REPO, SHORT_LICENSES, license_details


API = "https://api.inaturalist.org/v2/"
PHOTO_URL = re.compile(r"https://inaturalist-open-data\.s3\.amazonaws\.com/photos/(\d+)/(?:square|medium)\.(jpe?g|png)", re.I)
PHOTO_FIELDS = "id,license_code,attribution,attribution_name,medium_url,url,flags,hidden"
TAXON_FIELDS = "id,name,rank,is_active," + ",".join("taxon_photos.photo." + f for f in PHOTO_FIELDS.split(","))
OBS_FIELDS = "id,quality_grade,captive,community_taxon_id,taxon.id,taxon.name,taxon.rank,taxon.is_active," + ",".join("photos." + f for f in PHOTO_FIELDS.split(","))


class PublicAPI:
    def __init__(self):
        self.count = 0
        self.last_call = 0

    def get(self, path, params):
        url = API + path + "?" + urlencode(params)
        for attempt in range(3):
            time.sleep(max(0, 1.2 - (time.monotonic() - self.last_call)))
            self.count += 1
            self.last_call = time.monotonic()
            try:
                req = Request(url, headers={"User-Agent": "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)", "Accept": "application/json"})
                with urlopen(req, timeout=40) as response:
                    return json.load(response)
            except HTTPError as exc:
                if exc.code not in {429, 502, 503, 504} or attempt == 2:
                    raise
                delay = exc.headers.get("Retry-After", "")
                time.sleep(int(delay) if delay.isdecimal() else 3 * (attempt + 1))
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))


def batches(items, size):
    items = list(items)
    for start in range(0, len(items), size):
        yield items[start:start + size]


def original_credit(photo):
    name = (photo.get("attribution_name") or "").strip()
    if not name:
        match = re.match(r"^(?:\(c\)|©)\s*(.+?),\s*(?:some rights reserved|all rights reserved)", photo.get("attribution", ""), re.I)
        name = match[1].strip() if match else ""
    return name if name.lower() not in {"", "unknown", "anonymous", "no rights reserved"} else ""


def evidence(photo, taxon, taxon_id, kind, observation=None):
    raw_url = photo.get("medium_url") or photo.get("url") or ""
    matched = PHOTO_URL.fullmatch(raw_url)
    pid = str(photo.get("id"))
    license_code = photo.get("license_code")
    if not matched or matched[1] != pid or license_code not in SHORT_LICENSES:
        return None
    if photo.get("hidden") or photo.get("flags") or not original_credit(photo):
        return None
    return {
        "taxon": taxon_id, "latin": taxon["name"], "inat": taxon["id"],
        "photo": int(pid), "credit": original_credit(photo), "license": license_code,
        "image": raw_url, "basis": kind, **({"observation": observation} if observation else {}),
    }


def candidates(taxonomy, known, birdnet):
    targets = {}
    for r in birdnet:
        aid = "avibase-" + str(r["avibase_id"])
        taxon = taxonomy.get(aid)
        if r["taxon_group"] != "Aves" or r["record_type"] != "species" or not r.get("inat_id"):
            continue
        if not taxon or taxon["latin"] != r["scientific_name"] or taxon.get("extinction") or aid in known:
            continue
        key = int(r["inat_id"])
        if key in targets:
            raise ValueError(f"Duplicate iNaturalist identifier {key}")
        targets[key] = (aid, taxon["latin"], r.get("commonness") or 0)
    return targets


def matches(taxon, expected):
    return (taxon.get("id") in expected and taxon.get("rank") == "species" and taxon.get("is_active") is True
            and taxon.get("name") == expected[taxon["id"]][1])


def fetch_evidence(api, targets, avicommons, base_ids, max_batches):
    problem = {r["sciName"]: str(r["key"]) for r in avicommons if r["key"].isdecimal() and
               r["license"].startswith("CC0 ") and r["license"] != "CC0 1.0"}
    remaining = dict(targets)
    used = set(base_ids)
    found = {}

    def accept(record):
        if record and record["photo"] not in used:
            used.add(record["photo"])
            found[record["taxon"]] = record
            remaining.pop(record["inat"], None)
            return True
        return False

    for group in batches([k for k, t in targets.items() if t[1] in problem], 30):
        data = api.get("taxa/" + ",".join(map(str, group)), {"per_page": 30, "fields": TAXON_FIELDS})
        for taxon in data["results"]:
            if not matches(taxon, remaining):
                continue
            aid, latin, _ = remaining[taxon["id"]]
            for item in taxon.get("taxon_photos", []):
                photo = item.get("photo") or {}
                if str(photo.get("id")) == problem.get(latin):
                    accept(evidence(photo, taxon, aid, "verified-taxon-photo"))
                    break
    print(f"Verified original conflicting candidate photographs: {len(found)}.", flush=True)

    # Requery only missing taxa. Group taxa of similar commonness so the most
    # frequently observed birds don't crowd out rare species in every response.
    budget = max_batches
    while remaining and budget:
        ranked = sorted(remaining, key=lambda k: (remaining[k][2], k))
        before = len(remaining)
        for group in batches(ranked, 42):
            if not budget:
                break
            budget -= 1
            params = {"taxon_id": ",".join(map(str, group)), "quality_grade": "research",
                      "captive": "false", "photos": "true", "lrank": "species", "hrank": "species",
                      "photo_license": ",".join(SHORT_LICENSES), "per_page": 160, "order_by": "votes",
                      "fields": OBS_FIELDS}
            data = api.get("observations", params)
            for observation in data["results"]:
                taxon = observation.get("taxon") or {}
                if not matches(taxon, remaining) or observation.get("community_taxon_id") != taxon["id"]:
                    continue
                if observation.get("quality_grade") != "research" or observation.get("captive") is not False:
                    continue
                for photo in observation.get("photos", []):
                    if accept(evidence(photo, taxon, remaining[taxon["id"]][0], "research-observation", observation["id"])):
                        break
            print(f"{api.count} requests; {len(found)} accepted; {len(remaining)} remaining", flush=True)
        if len(remaining) == before:
            break
    return list(found.values())


def merge(base, snapshot, taxonomy):
    entries = base["bySpecies"]
    for item in snapshot.get("removed", []):
        current = entries.get(item["taxon"])
        if current and str(current["photoId"]) == str(item["photo"]):
            del entries[item["taxon"]]
    used = {str(r["photoId"]) for r in entries.values()}
    for e in snapshot["records"]:
        taxon, pid = e["taxon"], str(e["photo"])
        if taxon not in taxonomy or taxonomy[taxon]["latin"] != e["latin"]:
            raise ValueError(f"Taxonomy differs for {taxon}")
        if taxon in entries or pid in used:
            continue
        match = PHOTO_URL.fullmatch(e["image"])
        if not match or match[1] != pid or not e["credit"] or e["license"] not in SHORT_LICENSES:
            raise ValueError(f"Invalid source record for {taxon}")
        label, license_url = license_details(e["license"])
        prefix = e["image"].rsplit("/", 1)[0]
        original = f"https://www.inaturalist.org/photos/{pid}"
        row = {"sourceId": "inaturalist-api", "id": pid, "photoId": pid, "scientificName": e["latin"],
               "author": e["credit"], "license": label, "licenseUrl": license_url, "sourceUrl": original,
               "filePage": original, "imageUrl": f"{prefix}/large.{match[2]}", "thumbUrl": f"{prefix}/medium.{match[2]}",
               "basis": e["basis"]}
        if e.get("observation"):
            row["observationId"] = e["observation"]
            row["observationUrl"] = f"https://www.inaturalist.org/observations/{e['observation']}"
        if e.get("observedName"):
            row["observedScientificName"] = e["observedName"]
        if e["basis"] == "captive-observation":
            row["captive"] = True
        entries[taxon] = row
        used.add(pid)
    base["sources"]["inaturalist-api"] = {"url": "https://www.inaturalist.org/", "checked": snapshot["checked"]}
    return base


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--snapshot", type=Path, default=REPO / "data" / "inaturalist-evidence.json")
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--birdnet", type=Path)
    p.add_argument("--photos", type=Path)
    p.add_argument("--max-batches", type=int, default=60)
    args = p.parse_args()
    if args.base.resolve() == args.output.resolve():
        p.error("Choose a different output path and verify before replacing a published index.")
    base = json.loads(args.base.read_bytes())
    taxonomy = {r["id"]: r for r in json.loads((REPO / "data" / "checklist.json").read_bytes())["species"]}
    if args.refresh:
        if not args.birdnet or not args.photos:
            p.error("--refresh needs matching --birdnet and --photos source files")
        with ZipFile(args.birdnet) as archive:
            with archive.open(BIRDNET_STEM + ".json") as h:
                targets = candidates(taxonomy, base["bySpecies"], json.load(h))
        api = PublicAPI()
        records = fetch_evidence(api, targets, json.loads(args.photos.read_bytes()), {int(r["photoId"]) for r in base["bySpecies"].values()}, args.max_batches)
        snapshot = {"checked": datetime.now(timezone.utc).date().isoformat(), "records": records}
        args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    else:
        snapshot = json.loads(args.snapshot.read_bytes())
    combined = merge(base, snapshot, taxonomy)
    args.output.write_text(json.dumps(combined, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(combined['bySpecies']):,} species with photography. Snapshot: {dict(Counter(r['basis'] for r in snapshot['records']))}")


if __name__ == "__main__":
    main()
