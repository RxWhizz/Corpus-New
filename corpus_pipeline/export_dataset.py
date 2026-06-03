import argparse
import json
import sys
from pathlib import Path

from common import (
    ANNOTATIONS_DIR,
    CALIBRATION_CSV,
    CALIBRATION_FIELDS,
    COCO_MASTER_JSON,
    EXPORTS_DIR,
    IMAGE_FIELDS,
    IMAGES_CSV,
    REPORTS_DIR,
    ROOT,
    SOURCE_FIELDS,
    SOURCES_CSV,
    print_json,
    read_csv,
)
from metadata import validate_metadata


CATEGORIES = [
    {"id": 0, "name": "Au_core", "supercategory": "nanoparticle"},
    {"id": 1, "name": "SiO2_outer", "supercategory": "nanoparticle"},
]


def create_coco_template(images, sources=None, public_only=False):
    sources_by_id = {source["source_id"]: source for source in (sources or []) if source.get("source_id")}
    coco_images = []
    for index, image in enumerate(images, start=1):
        if image.get("curation_status") != "accepted":
            continue
        source = sources_by_id.get(image.get("source_id", ""), {})
        if public_only and source.get("license_status") != "accepted":
            continue
        coco_images.append(
            {
                "id": index,
                "file_name": image["file_path"].replace("\\", "/"),
                "width": int(image["width"] or 0),
                "height": int(image["height"] or 0),
                "image_id": image["image_id"],
                "source_id": image["source_id"],
                "license": image["license"],
                "license_status": source.get("license_status", ""),
                "nm_per_px": image["nm_per_px"],
                "split": image["split"] or "train",
                "metadata": {
                    "source_url": image.get("source_url", ""),
                    "doi": source.get("doi", ""),
                    "title": source.get("title", ""),
                    "authors": source.get("authors", ""),
                    "journal": source.get("journal", ""),
                    "year": source.get("year", ""),
                    "license_url": source.get("license_url", ""),
                    "figure_label": image.get("figure_label", ""),
                    "panel_label": image.get("panel_label", ""),
                    "caption": image.get("caption", ""),
                    "file_sha256": image.get("file_sha256", ""),
                    "quality_status": image.get("quality_status", ""),
                    "scale_status": image.get("scale_status", ""),
                    "metadata_status": image.get("metadata_status", ""),
                    "notes": image.get("notes", ""),
                },
            }
        )
    return {"images": coco_images, "annotations": [], "categories": CATEGORIES}


def export_coco():
    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    coco = create_coco_template(images, sources)
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
    COCO_MASTER_JSON.write_text(json.dumps(coco, indent=2), encoding="utf-8")
    return {"path": str(COCO_MASTER_JSON), "images": len(coco["images"])}


def normalize_polygon(points, width, height):
    normalized = []
    for idx, value in enumerate(points):
        limit = width if idx % 2 == 0 else height
        normalized.append(max(0.0, min(1.0, float(value) / float(limit or 1))))
    return normalized


def export_yolo():
    imported_coco = ANNOTATIONS_DIR / "cvat_coco_imported.json"
    if not imported_coco.exists():
        return {
            "path": str(EXPORTS_DIR),
            "labels": 0,
            "message": "No CVAT COCO annotations found. Import CVAT COCO before YOLO-seg export.",
        }
    sys.path.insert(0, str(ROOT / "training"))
    from prepare_yolo_seg import prepare_yolo

    return prepare_yolo(imported_coco, EXPORTS_DIR)


def generate_audit():
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    calibration = read_csv(CALIBRATION_CSV, CALIBRATION_FIELDS)
    metadata_report = validate_metadata(write_report=True)
    accepted_sources = [row for row in sources if row["decision"] == "accepted"]
    accepted_images = [row for row in images if row["curation_status"] == "accepted"]
    missing_scale = [row for row in accepted_images if not row.get("nm_per_px")]
    rejected_images = [row for row in images if row["curation_status"] == "rejected"]

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Corpus Audit Report",
        "",
        f"- Sources total: {len(sources)}",
        f"- Sources accepted: {len(accepted_sources)}",
        f"- Images total: {len(images)}",
        f"- Images accepted: {len(accepted_images)}",
        f"- Images rejected: {len(rejected_images)}",
        f"- Accepted images missing scale: {len(missing_scale)}",
        f"- Calibrations: {len(calibration)}",
        f"- Publication-ready sources: {metadata_report['publication_ready_sources']}",
        f"- License-blocked sources: {metadata_report['license_blocked_sources']}",
        f"- Images missing caption/notes: {metadata_report['images_missing_caption']}",
        f"- Images missing checksum: {metadata_report['images_missing_checksum']}",
        f"- Metadata-ready images: {metadata_report['metadata_ready_images']}",
        "",
        "## Accepted Sources",
    ]
    for row in accepted_sources:
        lines.append(f"- {row['source_id']} | {row['license']} | {row['url']}")
    if missing_scale:
        lines.extend(["", "## Accepted Images Missing Scale"])
        for row in missing_scale:
            lines.append(f"- {row['image_id']} | {row['file_path']}")
    audit_path = REPORTS_DIR / "audit.md"
    audit_path.write_text("\n".join(lines), encoding="utf-8")
    return {"path": str(audit_path), "accepted_images": len(accepted_images), "missing_scale": len(missing_scale)}


def main():
    parser = argparse.ArgumentParser(description="Export corpus annotations and reports.")
    parser.add_argument("--coco", action="store_true")
    parser.add_argument("--yolo", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    outputs = {}
    if args.coco or not (args.coco or args.yolo or args.audit):
        outputs["coco"] = export_coco()
    if args.yolo:
        outputs["yolo"] = export_yolo()
    if args.audit:
        outputs["audit"] = generate_audit()

    print_json({"ok": True, "message": "Export complete.", "outputs": outputs})


if __name__ == "__main__":
    main()
