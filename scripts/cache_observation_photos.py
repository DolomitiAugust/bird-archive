"""Cache sourced bird photographs as small WebP previews, with resumable downloads."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
from pathlib import Path
import re
import threading
import time
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data/observations.json"
CONTACT = "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"
FILE = re.compile(r"https://static\.avicommons\.org/([a-z0-9]+)-([0-9]+)-320\.jpg")
INAT = re.compile(r"https://inaturalist-open-data\.s3\.amazonaws\.com/photos/([0-9]+)/medium\.(?:jpe?g|png|webp)", re.IGNORECASE)
ID = re.compile(r"avibase-([A-F0-9]{8})")


class RequestPace:
    """Share the request interval and rate-limit pauses across workers."""

    def __init__(self, rate):
        self.interval = 1 / rate
        self.next_start = 0
        self.lock = threading.Lock()

    def wait(self):
        while True:
            with self.lock:
                now = time.monotonic()
                delay = self.next_start - now
                if delay <= 0:
                    self.next_start = now + self.interval
                    return
            time.sleep(delay)

    def pause(self, duration):
        with self.lock:
            self.next_start = max(self.next_start, time.monotonic() + duration)


def get_image(url, pace, max_bytes=2_000_000, max_edge=1000):
    for attempt in range(3):
        pace.wait()
        try:
            with urlopen(Request(url, headers={"User-Agent": CONTACT}), timeout=15) as response:
                content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                raise ValueError("unexpected source size")
            with Image.open(BytesIO(content)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP") or max(image.size) > max_edge:
                    raise ValueError("unexpected image format or dimensions")
                return image.convert("RGB")
        except HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            delay = exc.headers.get("Retry-After", "")
            pace.pause(int(delay) if delay.isdigit() else 3 * (attempt + 1))
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def cache_one(item, root, pace):
    species_id, record = item
    url = record.get("thumbUrl", "")
    source = FILE.fullmatch(url)
    inat = INAT.fullmatch(url)
    identifier = ID.fullmatch(species_id)
    if not (source or inat) or not identifier:
        return species_id, None, "unsupported source or identifier"
    photo_id = source[2] if source else inat[1]
    relative = Path("photos/archive") / identifier[1][:2].lower() / f"{identifier[1].lower()}-{photo_id}.webp"
    path = root / relative
    try:
        if path.is_file():
            with Image.open(path) as existing:
                existing.load()
                if existing.format == "WEBP" and max(existing.size) <= 320:
                    return species_id, relative.as_posix(), None
    except (ValueError, OSError):
        pass
    temporary = None
    try:
        try:
            image = get_image(url, pace)
        except HTTPError as error:
            if error.code != 404:
                raise
            # Some originals have no exported small size. Only try the larger size
            # of this exact photograph at the same provider.
            alternate = url.replace("-320.jpg", "-900.jpg") if source else url.replace("/medium.", "/large.")
            if alternate != record.get("imageUrl"):
                raise
            image = get_image(alternate, pace, max_bytes=8_000_000, max_edge=4096)
        image.thumbnail((320, 320), Image.Resampling.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=path.parent, delete=False, suffix=".part") as output:
            temporary = Path(output.name)
            image.save(output, format="WEBP", quality=82, method=4)
        temporary.replace(path)
        return species_id, relative.as_posix(), None
    except (OSError, ValueError) as error:
        return species_id, None, str(error)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--workers", type=int, choices=range(1, 17), default=8, metavar="1..16")
    parser.add_argument("--rate", type=int, choices=range(1, 16), default=8, metavar="1..15")
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    records = index["bySpecies"]
    pace = RequestPace(args.rate)
    failures = 0
    ready = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for species_id, local, error in pool.map(lambda item: cache_one(item, args.root, pace), records.items()):
            if error:
                records[species_id].pop("localThumb", None)
                print(f"{species_id}: {error}", flush=True)
                failures += 1
            else:
                records[species_id]["localThumb"] = local
                ready += 1
            if (ready + failures) % 500 == 0:
                print(f"{ready + failures}/{len(records)} checked; {ready} cached", flush=True)
    with NamedTemporaryFile(dir=args.index.parent, delete=False, suffix=".part", mode="w", encoding="utf-8") as output:
        temp = Path(output.name)
        metadata = {key: value for key, value in index.items() if key != "bySpecies"}
        output.write("{\n")
        for key, value in metadata.items():
            output.write(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},\n")
        output.write('  "bySpecies": {\n')
        for number, (key, value) in enumerate(records.items()):
            if number:
                output.write(",\n")
            output.write(f"    {json.dumps(key)}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}")
        output.write("\n  }\n}\n")
    try:
        temp.replace(args.index)
    finally:
        temp.unlink(missing_ok=True)
    print(f"{ready}/{len(records)} thumbnails cached; {failures} to retry", flush=True)
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
