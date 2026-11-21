"""Screen local archive photographs for manual visual review at gallery scale.

The scores describe the whole frame, not a species identification or a judgment
about the bird. Real grey plumage, silhouettes, fog and camera-trap records can
all trigger the review thresholds.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps, ImageStat

ROOT = Path(__file__).resolve().parents[1]
COLUMNS = ["file", "species", "scientific_name", "width", "height", "chroma_spread",
           "chroma_residual", "edge_p98", "edge_p995", "central_detail", "flags"]


def photo_names(root):
    observations = json.loads((root / "data/observations.json").read_text(encoding="utf8"))
    names = {row[field]: (key, row["scientificName"]) for key, row in observations["bySpecies"].items()
             for field in ("localThumb", "localFull") if row.get(field)}
    curated = json.loads((root / "data/photos.json").read_text(encoding="utf8"))
    for row in curated:
        for version in (row, row.get("historicalPhoto", {})):
            for photo in (version, version.get("thumbnail", {})):
                if photo.get("file"):
                    names["photos/" + photo["file"]] = (row["id"], row["latin"])
    return names


def percentile(histogram, fraction):
    target = sum(histogram) * fraction
    count = 0
    for level, value in enumerate(histogram):
        count += value
        if count >= target:
            return level
    return len(histogram) - 1


def color_metrics(image):
    sample = image.resize((40, 40), Image.Resampling.BOX).convert("YCbCr")
    _, cb_std, cr_std = ImageStat.Stat(sample).stddev
    # Measure variation after accounting for an overall tint and a tint varying
    # with paper brightness (for example, sepia or old captioned plates).
    sums = [[0, 0, 0, 0] for _ in range(16)]
    luminance, cb_values, cr_values = (band.tobytes() for band in sample.split())
    for light, cb, cr in zip(luminance, cb_values, cr_values):
        bucket = sums[light // 16]
        bucket[0] += 1
        bucket[1] += cb
        bucket[2] += cr
        bucket[3] += cb * cb + cr * cr
    residual = sum(max(0., square - (cb * cb + cr * cr) / n)
                   for n, cb, cr, square in sums if n)
    return round((cb_std * cb_std + cr_std * cr_std) ** .5, 2), round((residual / 1600) ** .5, 2)


def scan_one(path, root, names):
    relative = path.relative_to(root).as_posix()
    species, latin = names.get(relative, ("", ""))
    with Image.open(path) as source:
        size = source.size
        # Evaluate the view visitors actually see, independently of the
        # dimensions of the original photograph on a third-party server.
        image = ImageOps.fit(source.convert("RGB"), (180, 135), Image.Resampling.LANCZOS)
    spread, residual = color_metrics(image)
    gray = image.convert("L")
    edges = ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(1.15)))
    histogram = edges.histogram()
    p98 = percentile(histogram, .98)
    p995 = percentile(histogram, .995)
    center = ImageStat.Stat(edges.crop((27, 20, 153, 115))).mean[0]
    flags = []
    if residual <= 2.7:
        flags.append("possible-monochrome")
    if min(size) < 100 or max(size) < 200:
        flags.append("small")
    if p98 <= 9 or p995 <= 15 or center < 1.05:
        flags.append("low-detail")
    return dict(zip(COLUMNS, (relative, species, latin, *size, spread, residual, p98,
                              p995, round(center, 2), ",".join(flags))))


def contact_sheets(root, rows, folder, label):
    folder.mkdir(parents=True, exist_ok=True)
    per_page = 48
    for offset in range(0, len(rows), per_page):
        batch = rows[offset:offset + per_page]
        sheet = Image.new("RGB", (960, 112 * ((len(batch) + 7) // 8)), "#f6f3e9")
        draw = ImageDraw.Draw(sheet)
        for i, row in enumerate(batch):
            x, y = 120 * (i % 8), 112 * (i // 8)
            with Image.open(root / row["file"]) as source:
                thumb = ImageOps.contain(source.convert("RGB"), (115, 77))
            sheet.paste(thumb, (x + (120 - thumb.width) // 2, y))
            draw.text((x + 2, y + 77), row["species"].removeprefix("avibase-"), fill="black")
            draw.text((x + 2, y + 91), row["scientific_name"][:20], fill="black")
        sheet.save(folder / f"{label}-{offset // per_page + 1:03}.jpg", quality=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--csv", type=Path, help="Write one row per scanned file, including unflagged files.")
    parser.add_argument("--sheets", type=Path, help="Write labelled contact sheets for each review group.")
    args = parser.parse_args()
    names = photo_names(args.root)
    paths = sorted((args.root / "photos").rglob("*.webp"))
    with ThreadPoolExecutor(max_workers=8) as workers:
        rows = list(workers.map(lambda path: scan_one(path, args.root, names), paths))
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8-sig") as out:
            writer = csv.DictWriter(out, COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
    print(f"Scanned {len(rows)} files. {sum(bool(r['flags']) for r in rows)} require visual review.")
    for label, key in [("possible-monochrome", "chroma_residual"), ("small", "width"), ("low-detail", "edge_p98")]:
        candidates = sorted((r for r in rows if label in r["flags"]), key=lambda r: (r[key], r["file"]))
        print(f"{label}: {len(candidates)}")
        if args.sheets:
            contact_sheets(args.root, candidates, args.sheets, label)


if __name__ == "__main__":
    main()
