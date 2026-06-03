import argparse
import csv
import shutil
from pathlib import Path

from common_training import DATA_DIR, ROOT, resolve_image_path


def export_package(output_dir):
    output_dir = Path(output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    images_csv = DATA_DIR / "images.csv"
    if not images_csv.exists():
        raise SystemExit("No data/images.csv found. Curate corpus images first.")
    with images_csv.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("curation_status") != "accepted":
                continue
            source = resolve_image_path(row.get("file_path", ""))
            if not source:
                continue
            target = images_dir / source.name
            shutil.copy2(source, target)
            rows.append({**row, "cvat_file": str(target)})
    with (output_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=sorted(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    return {"output": str(output_dir), "images": len(rows)}


def main():
    parser = argparse.ArgumentParser(description="Export accepted Corpus images for CVAT annotation.")
    parser.add_argument("--out", default=str(ROOT / "data" / "training" / "cvat_package"))
    args = parser.parse_args()
    print(export_package(args.out))


if __name__ == "__main__":
    main()
