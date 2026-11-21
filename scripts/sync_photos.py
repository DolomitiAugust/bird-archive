"""Restore missing WebP files from the reviewed photo manifest. Requires Pillow."""

import argparse
import hashlib
import json
import sys
import tempfile
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path
from typing import NamedTuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
PHOTO_DIR = ROOT / "photos"
CONTACT = "BirdArchive/1.0 (+https://github.com/DolomitiAugust/bird-archive)"
MAX_SOURCE_BYTES = 48 * 1024 * 1024


class Rendition(NamedTuple):
    file: str
    edge: int
    quality: int
    size: list | None
    crop: list | None


def media_records(records):
    for row in records:
        yield row["id"], row
        if "historicalPhoto" in row:
            yield row["id"], row["historicalPhoto"]


def renditions(row):
    has_large_detail = "thumbnail" in row or row.get("kind") == "specimen"
    yield Rendition(row["file"], 1920 if has_large_detail else 900, 88 if has_large_detail else 82,
                    row.get("size"), row.get("crop"))
    if "thumbnail" in row:
        thumb = row["thumbnail"]
        yield Rendition(thumb["file"], 480, 82, thumb["size"], thumb.get("crop", row.get("crop")))


def pixel_size(value):
    return isinstance(value, list) and len(value) == 2 and all(type(v) is int and v > 0 for v in value)


def check_crop(box, source_size):
    if not isinstance(box, list) or len(box) != 4 or not all(type(v) is int for v in box):
        raise ValueError(f"Invalid source crop: {box}")
    left, top, right, bottom = box
    if not (0 <= left < right <= source_size[0] and 0 <= top < bottom <= source_size[1]):
        raise ValueError(f"Crop {box} is outside the source image {source_size}")


def validate_manifest(records):
    for key in ("id", "latin"):
        values = [row[key] for row in records]
        if len(values) != len(set(values)):
            raise ValueError(f"Duplicate {key} in photo manifest")
    filenames = set()
    for _, row in media_records(records):
        source_size = row.get("sourceSize")
        if source_size is not None and not pixel_size(source_size):
            raise ValueError(f"Invalid source image dimensions: {row['file']}")
        for version in renditions(row):
            filename = Path(version.file)
            if filename.name != version.file or filename.suffix != ".webp" or version.file in filenames:
                raise ValueError(f"Invalid or duplicate image filename: {filename}")
            if version.size is not None and (not pixel_size(version.size) or max(version.size) > version.edge):
                raise ValueError(f"Invalid rendition size: {filename}")
            if version.crop is not None:
                if source_size is None:
                    raise ValueError(f"Missing source dimensions for crop: {filename}")
                check_crop(version.crop, source_size)
            filenames.add(version.file)
        credit = row["credit"]
        if not all(credit.get(key) for key in ("author", "license", "licenseUrl", "filePage", "imageUrl")):
            raise ValueError(f"Missing photo credit: {filename}")
        for field in ("licenseUrl", "filePage", "imageUrl"):
            if urlsplit(credit[field]).scheme != "https":
                raise ValueError(f"Invalid {field} for {filename}")


def valid_webp(path, version):
    try:
        with Image.open(path) as image:
            image.load()
            return (image.format == "WEBP" and 0 < max(image.size) <= version.edge and
                    (not version.size or list(image.size) == version.size))
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


def read_original(row):
    data = download(row["credit"]["imageUrl"])
    if row.get("sourceSHA1") and hashlib.sha1(data).hexdigest() != row["sourceSHA1"]:
        raise ValueError("The reviewed source image has changed")
    with Image.open(BytesIO(data)) as original:
        image = ImageOps.exif_transpose(original).convert("RGB")
    if row.get("sourceSize") and list(image.size) != row["sourceSize"]:
        raise ValueError("Source image dimensions do not match the record")
    return image


def restore_rendition(original, path, version):
    if version.crop is not None:
        check_crop(version.crop, original.size)
        image = original.crop(version.crop)
    else:
        image = original.copy()
    # Declared sizes may be smaller than the format limit, e.g. a 400px preview.
    edge = max(version.size) if version.size is not None else version.edge
    image.thumbnail((edge, edge), Image.Resampling.LANCZOS)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as output:
        temp = Path(output.name)
    try:
        image.save(temp, format="WEBP", quality=version.quality, method=6)
        if not valid_webp(temp, version):
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
    total = 0
    for record_id, row in media_records(records):
        versions = list(renditions(row))
        total += len(versions)
        missing = [v for v in versions if not valid_webp(PHOTO_DIR / v.file, v)]
        if not missing:
            continue
        if args.verify_only:
            for version in missing:
                print(f"{record_id}: missing or invalid {version.file}", file=sys.stderr)
            failures += len(missing)
            continue
        try:
            original = read_original(row)
        except (OSError, ValueError) as error:
            print(f"{record_id} ({row['file']}): {error}", file=sys.stderr)
            failures += len(missing)
        else:
            for version in missing:
                try:
                    restore_rendition(original, PHOTO_DIR / version.file, version)
                    print(f"{record_id}: restored {version.file}")
                except (OSError, ValueError) as error:
                    print(f"{record_id} ({version.file}): {error}", file=sys.stderr)
                    failures += 1
        time.sleep(1)
    print(f"{total - failures}/{total} photo files ready")
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
