"""Restore missing WebP files from the reviewed photo manifest. Requires Pillow."""

import argparse
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT / "photos"
CONTACT = "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"
MAX_SOURCE_BYTES = 48 * 1024 * 1024


def validate_manifest(records):
    for key in ("id", "file", "latin"):
        values = [row[key] for row in records]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {key} in photo manifest")
    for row in records:
        filename = Path(row["file"])
        if filename.name != row["file"] or filename.suffix != ".webp":
            raise ValueError(f"Invalid image filename: {filename}")
        credit = row["credit"]
        if not all(credit.get(key) for key in ("author", "license", "licenseUrl", "filePage", "imageUrl")):
            raise ValueError(f"Missing photo credit: {filename}")
        for field in ("licenseUrl", "filePage", "imageUrl"):
            if urlsplit(credit[field]).scheme != "https":
                raise ValueError(f"Invalid {field} for {filename}")


def valid_webp(path):
    try:
        with Image.open(path) as image:
            image.load()
            return image.format == "WEBP" and 0 < max(image.size) <= 900
    except (OSError, ValueError):
        return False


def retry_delay(header, attempt):
    if not header:
        return 2 ** attempt
    try:
        return max(0, float(header))
    except ValueError:
        return max(0, (parsedate_to_datetime(header) - datetime.now(timezone.utc)).total_seconds())


def download(url):
    request = Request(url, headers={"User-Agent": CONTACT})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise ValueError("Source image exceeds 48 MiB; record a smaller authorized source")
            return data
        except HTTPError as error:
            if attempt == 2 or error.code not in (429, 500, 502, 503, 504):
                raise
            delay = retry_delay(error.headers.get("Retry-After"), attempt)
            if delay > 60:
                raise
        except (URLError, TimeoutError):
            if attempt == 2:
                raise
            delay = 2 ** attempt
        time.sleep(delay)


def restore_photo(path, url):
    data = download(url)
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    image.thumbnail((900, 900), Image.Resampling.LANCZOS)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as output:
        temp = Path(output.name)
    try:
        image.save(temp, format="WEBP", quality=82, method=6)
        if not valid_webp(temp):
            raise ValueError("WebP validation failed")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="check the manifest and local images without downloading")
    args = parser.parse_args()
    records = json.loads((ROOT / "data/photos.json").read_text(encoding="utf-8"))
    validate_manifest(records)
    if not args.verify_only:
        PHOTO_DIR.mkdir(exist_ok=True)
    failures = 0
    for row in records:
        photo = PHOTO_DIR / row["file"]
        if valid_webp(photo):
            continue
        if args.verify_only:
            print(f"{row['id']}: missing or invalid {photo.name}", file=sys.stderr)
            failures += 1
            continue
        try:
            restore_photo(photo, row["credit"]["imageUrl"])
            print(f"{row['id']}: restored {photo.name}")
        except (OSError, ValueError) as error:
            print(f"{row['id']}: {error}", file=sys.stderr)
            failures += 1
        time.sleep(1)
    print(f"{len(records) - failures}/{len(records)} photos ready")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
