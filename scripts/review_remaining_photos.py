"""Review rare remaining taxa, including current synonyms and captive-only records."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import re
from zipfile import ZipFile

from import_checklist import read_source
from supplement_inaturalist import (
    BIRDNET_STEM, OBS_FIELDS, REPO, SHORT_LICENSES, Path, PublicAPI, batches, evidence, merge,
)


# Dead upstream IDs were independently checked at the small and large size.
DEAD = {
    "avibase-826C6C37": 348248779, "avibase-54BE5060": 223261416,
    "avibase-712D944F": 118442274, "avibase-33487D8B": 118300462,
    "avibase-9132B347": 119330421, "avibase-549E06B6": 457506124,
}
ZOO = re.compile(r"\b(zoo|zoologi\w*|aviary|aviaries|wildlife park|bird park|captive breeding|captive|parrot park|vol[iè]?[eè]re|bioparc|biopark|vogelpark)\b", re.I)
NONLIVING = re.compile(r"\b(mount(?:ed)?|museum specimen|taxiderm\w*|skeleton|stuffed|preserved|dead bird|illustration|painting|plush|drawing)\b", re.I)


def build_candidates(records, taxa, current):
    accepted_names = {a["latin"]: k for k, a in taxa.items()}
    aliases = defaultdict(set)
    for row in records:
        key = "avibase-" + str(row.get("avibase_id"))
        for name in row.get("scientific_name_aliases") or []:
            aliases[name].add(key)
    candidates = {}
    for row in records:
        key = "avibase-" + str(row.get("avibase_id"))
        t = taxa.get(key)
        if row["taxon_group"] != "Aves" or row["record_type"] != "species" or not row.get("inat_id"):
            continue
        if not t or row["scientific_name"] != t["latin"] or key in current and key not in DEAD:
            continue
        status = t.get("extinction", "")
        if status and "in the wild" not in status.lower():
            continue
        allowed_names = {t["latin"]}
        for name in row.get("scientific_name_aliases") or []:
            if aliases[name] == {key} and accepted_names.get(name, key) == key:
                allowed_names.add(name)
        candidates[int(row["inat_id"])] = {"key": key, "latin": t["latin"], "names": allowed_names,
                                           "status": status, "commonness": row.get("commonness") or 0}
    return candidates


def resolve_official_taxa(api, candidates):
    targets = {}
    for ids in batches(candidates, 30):
        res = api.get("taxa/" + ",".join(map(str, ids)), {
            "per_page": 30, "fields": "id,name,rank,is_active,observations_count",
        })
        for t in res["results"]:
            candidate = candidates.get(t["id"])
            if candidate and t["rank"] == "species" and t["is_active"] is True and t["name"] in candidate["names"]:
                targets[t["id"]] = {**candidate, "current": t["name"], "count": t.get("observations_count") or 0}
    return targets


def get_records(api, ids, captive, *, limit=135):
    return api.get("observations", {
        "taxon_id": ",".join(map(str, ids)), "quality_grade": "casual" if captive else "research",
        "captive": str(captive).lower(), "photos": "true", "photo_license": ",".join(SHORT_LICENSES),
        "per_page": limit, "order_by": "votes", "fields": OBS_FIELDS + ",taxon.ancestor_ids"
        + (",description,place_guess,observed_on" if captive else ""),
        **({"d1": "2015-01-01"} if captive else {}),
    })


def select_records(results, targets, used, captive, avilist_subspecies):
    matched = {}
    for obs in results:
        t = obs.get("taxon") or {}
        if obs.get("captive") is not captive or t.get("is_active") is not True or obs.get("community_taxon_id") != t.get("id"):
            continue
        rank, name = t.get("rank"), t.get("name") or ""
        if rank == "species":
            target_id = t["id"]
            if target_id not in targets or name != targets[target_id]["current"]:
                continue
        elif rank == "subspecies":
            parents = set(t.get("ancestor_ids") or []) & targets.keys()
            if len(parents) != 1:
                continue
            target_id = parents.pop()
            if name not in avilist_subspecies or " ".join(name.split()[:2]) != targets[target_id]["latin"]:
                continue
        else:
            continue
        target = targets[target_id]
        if target_id in matched:
            continue
        if captive:
            notes = (obs.get("description") or "") + " " + (obs.get("place_guess") or "")
            if not ZOO.search(notes) or NONLIVING.search(notes) or str(obs.get("observed_on") or "") < "2015-01-01":
                continue
        elif obs.get("quality_grade") != "research":
            continue
        for photo in obs.get("photos", []):
            row = evidence(photo, {"id": target_id, "name": target["latin"]}, target["key"],
                           "captive-observation" if captive else "research-observation", obs["id"])
            if not row or row["photo"] in used:
                continue
            row["observedName"] = name
            row["observedRank"] = rank
            row["parentSpeciesName"] = target["current"]
            used.add(row["photo"])
            matched[target_id] = row
            break
    return matched


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", required=True, type=Path)
    p.add_argument("--birdnet", required=True, type=Path)
    p.add_argument("--taxonomy", type=Path, help="Local copy of the pinned AviList v2026 Explorer JSON.")
    p.add_argument("--snapshot", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    if args.base.resolve() in (args.output.resolve(), args.snapshot.resolve()):
        p.error("The evidence, input and output need separate paths.")
    base = json.loads(args.base.read_bytes())
    taxa = {r["id"]: r for r in json.loads((REPO / "data" / "checklist.json").read_bytes())["species"]}
    with ZipFile(args.birdnet) as archive:
        with archive.open(BIRDNET_STEM + ".json") as h:
            candidates = build_candidates(json.load(h), taxa, base["bySpecies"])
    api = PublicAPI()
    avilist_subspecies = {r[5] for r in read_source(args.taxonomy) if r[1] == "subspecies"}
    targets = resolve_official_taxa(api, candidates)
    alive = {k: t for k, t in targets.items() if not t["status"] and t["count"] > 0}
    special = {k: t for k, t in targets.items() if t["status"] and t["count"] > 0}
    used = {int(r["photoId"]) for r in base["bySpecies"].values()} | set(DEAD.values())
    print(f"Exact official matches: {len(targets)}, with records: {len(alive)} unflagged and {len(special)} special-status.", flush=True)
    found, crowded = {}, []
    ranked = sorted(alive, key=lambda k: (alive[k]["count"],k))
    for group in batches(ranked, 12):
        subset = {k: alive[k] for k in group}
        data = get_records(api, group, False)
        additions = select_records(data["results"], subset, used, False, avilist_subspecies)
        found.update(additions)
        if data["total_results"] > len(data["results"]):
            crowded.extend(k for k in group if k not in found)
        print(f"{api.count} requests, {len(found)} additional records", flush=True)
    for group in batches(crowded, 2):
        subset = {k: alive[k] for k in group}
        data = get_records(api, group, False)
        found.update(select_records(data["results"], subset, used, False, avilist_subspecies))
    for k in special:
        data = get_records(api, [k], True, limit=60)
        found.update(select_records(data["results"], {k: special[k]}, used, True, avilist_subspecies))
    records = list(found.values())
    snapshot = {"checked": datetime.now(timezone.utc).date().isoformat(),
                "removed": [{"taxon": k, "photo": v, "reason": "Both upstream thumbnail and large image returned HTTP 404."} for k,v in DEAD.items()],
                "records": records}
    args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    output = merge(base, snapshot, taxa)
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Total {len(output['bySpecies']):,}. Added {dict(Counter(r['basis'] for r in records))}; {api.count} requests.")


if __name__ == "__main__":
    main()
