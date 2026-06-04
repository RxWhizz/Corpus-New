import argparse
import csv
import shutil
from pathlib import Path

from common_training import (
    CLASS_NAMES,
    DATA_DIR,
    DEFAULT_CVAT_DIR,
    has_confirmed_scale,
    is_public_license,
    read_csv,
    resolve_image_path,
    training_layer,
)


def source_index():
    return {row.get("source_id", ""): row for row in read_csv(DATA_DIR / "sources.csv")}


def should_export(row, source_row, layer, require_scale):
    if row.get("curation_status") != "accepted":
        return False, "curation_status_not_accepted"
    if require_scale and not has_confirmed_scale(row):
        return False, "missing_confirmed_scale"
    row_layer = training_layer(row, source_row)
    if layer != "all" and row_layer != layer:
        return False, f"layer_is_{row_layer}"
    if layer == "public_demo" and not (is_public_license(row) or is_public_license(source_row)):
        return False, "license_not_public"
    return True, ""


def export_package(output_dir, layer="all", require_scale=True):
    output_dir = Path(output_dir)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    skipped = {}
    sources = source_index()
    images_csv = DATA_DIR / "images.csv"
    if not images_csv.exists():
        raise SystemExit("No data/images.csv found. Curate corpus images first.")
    with images_csv.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            source_row = sources.get(row.get("source_id", ""), {})
            export, reason = should_export(row, source_row, layer, require_scale)
            if not export:
                skipped[reason] = skipped.get(reason, 0) + 1
                continue
            source = resolve_image_path(row.get("file_path", ""))
            if not source:
                skipped["missing_file"] = skipped.get("missing_file", 0) + 1
                continue
            target = images_dir / source.name
            shutil.copy2(source, target)
            row_layer = training_layer(row, source_row)
            rows.append(
                {
                    **row,
                    "dataset_layer": row_layer,
                    "cvat_file": str(target),
                    "doi": source_row.get("doi", ""),
                    "license_status": source_row.get("license_status", row.get("license_status", "")),
                    "source_title": source_row.get("title", ""),
                }
            )
    with (output_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=sorted(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    (output_dir / "labels.txt").write_text("\n".join(CLASS_NAMES) + "\n", encoding="utf-8")
    (output_dir / "annotation_policy.md").write_text(
        "# Corpus Au@SiO2 Core-Shell Annotation Policy\n\n"
        "- `Au_core`: closed polygon around the visible dark Au core.\n"
        "- `SiO2_outer`: closed polygon around the full visible outer particle boundary.\n"
        "- Exclude scale bars, panel letters, severe blur, clipped edge particles, and ambiguous overlaps.\n"
        "- Mark uncertain objects as `needs_review` in CVAT attributes if they must be preserved in the master COCO; they will be excluded from YOLO export.\n",
        encoding="utf-8",
    )
    return {"output": str(output_dir), "images": len(rows), "layer": layer, "skipped": skipped}


def main():
    parser = argparse.ArgumentParser(description="Export accepted Corpus images for CVAT annotation.")
    parser.add_argument("--out", default=str(DEFAULT_CVAT_DIR))
    parser.add_argument("--layer", choices=["all", "public_demo", "private_training", "synthetic_core_shell"], default="all")
    parser.add_argument("--allow-estimated-scale", action="store_true")
    args = parser.parse_args()
    print(export_package(args.out, layer=args.layer, require_scale=not args.allow_estimated_scale))


if __name__ == "__main__":
    main()
