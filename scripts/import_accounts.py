"""Build small per-prefix shards of sourced Wikipedia excerpts from the BirdNET+ release."""

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from zipfile import ZipFile

from import_chinese_names import RELEASE, ZIP_NAME, ZIP_SHA256, read_url


ROOT = Path(__file__).resolve().parents[1]


def excerpt(description, language):
    text = " ".join(description.split())
    if not text or "may refer to:" in text.casefold() or "可以指：" in text or "可能指：" in text:
        return ""
    if language == "zh":
        sentences = re.findall(r"[^。！？]+[。！？]", text)
        limit = 440
    else:
        sentences = re.findall(r".+?[.!?](?=\s+[A-Z‘“(]|$)", text)
        limit = 650
    pieces = []
    for sentence in sentences:
        sentence = sentence.strip()
        if len(" ".join(pieces + [sentence])) > limit or len(pieces) >= 3:
            break
        pieces.append(sentence)
    return (" " if language == "en" else "").join(pieces)


def select_account(row, languages):
    for lang in languages:
        if (row.get("description_sources") or {}).get(lang) != "wikipedia":
            continue
        url = (row.get("wikipedia_urls") or {}).get(lang, "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname != f"{lang}.wikipedia.org" or not parsed.path.startswith("/wiki/"):
            continue
        text = excerpt((row.get("descriptions") or {}).get(lang, ""), lang)
        if text:
            return {"lang": lang, "url": url, "text": text}


def write_index(entries, output):
    shards = {f"{n:02x}": {} for n in range(256)}
    for sid, account in entries.items():
        prefix = sid.removeprefix("avibase-")[:2].lower()
        shards[prefix][sid] = account
    output.mkdir(parents=True, exist_ok=True)
    for prefix, shard in shards.items():
        with NamedTemporaryFile(dir=output, delete=False, suffix=".part", mode="w", encoding="utf-8") as handle:
            json.dump(shard, handle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
        Path(handle.name).replace(output / (prefix + ".json"))
    counts = Counter(entry["lang"] for entry in entries.values())
    print(f"{output.name}: {len(entries)} ({dict(counts)})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--birdnet-zip", type=Path)
    parser.add_argument("--english-only", action="store_true", help="Rebuild only the English-mode excerpts.")
    args = parser.parse_args()
    data = args.birdnet_zip.read_bytes() if args.birdnet_zip else read_url(f"{RELEASE}/{ZIP_NAME}")
    if hashlib.sha256(data).hexdigest() != ZIP_SHA256:
        raise ValueError("Unexpected BirdNET+ archive checksum")
    catalog = json.loads((ROOT / "data/checklist.json").read_text(encoding="utf-8"))
    species = {s["latin"]: s["id"] for s in catalog["species"]}
    preferred, english = {}, {}
    with ZipFile(BytesIO(data)) as archive:
        rows = json.loads(archive.read(ZIP_NAME.replace(".zip", ".json")))
    for row in rows:
        sid = species.get(row["scientific_name"])
        if not sid or row["taxon_group"] != "Aves" or row["record_type"] != "species":
            continue
        if row.get("avibase_id") and sid != "avibase-" + row["avibase_id"]:
            continue
        if sid in preferred or sid in english:
            raise ValueError(f"Duplicate source for {sid}")
        en = select_account(row, ("en",))
        if en:
            english[sid] = en
        if not args.english_only:
            best = select_account(row, ("zh",)) or en
            if best:
                preferred[sid] = best
    if not args.english_only:
        write_index(preferred, ROOT / "data/accounts")
    write_index(english, ROOT / "data/accounts-en")


if __name__ == "__main__":
    main()
