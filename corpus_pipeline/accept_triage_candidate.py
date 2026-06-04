import argparse
import shutil
from pathlib import Path

from common import (
    FIGURES_DIR,
    IMAGE_FIELDS,
    IMAGES_CSV,
    SOURCE_FIELDS,
    SOURCES_CSV,
    image_size,
    now_iso,
    print_json,
    relative_to_root,
    resolve_path,
    sha256_file,
    stable_id,
    upsert_rows,
)


def accept_candidate(path_value, source_pdf="", page="", panel_label=""):
    source_path = resolve_path(path_value)
    if not source_path or not source_path.exists():
        raise SystemExit(f"Triage candidate file does not exist: {path_value}")

    source_id = stable_id(source_pdf or "local_pdf_triage", "src")
    image_id = stable_id(str(source_path.resolve()), "img")
    target_dir = FIGURES_DIR / "triage_accepted" / source_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{image_id}{source_path.suffix.lower() or '.png'}"
    shutil.copy2(source_path, target)
    width, height = image_size(target)
    timestamp = now_iso()

    source_row = {
        "source_id": source_id,
        "input": source_pdf or "local_pdf_triage",
        "url": "",
        "doi": "",
        "domain": "local_pdf",
        "title": source_pdf or "Local PDF triage source",
        "authors": "",
        "journal": "",
        "year": "",
        "publisher": "",
        "license": "Creative Commons local PDF; verify exact license URL before publication",
        "license_url": "",
        "license_status": "missing",
        "modality": "TEM",
        "abstract": "",
        "keywords": "",
        "source_type": "local_pdf_triage",
        "decision": "accepted",
        "status": "triage_candidate",
        "reason": "Accepted from Figure Triage for CVAT/manual review.",
        "local_path": "",
        "accessed_at": timestamp,
    }
    image_row = {
        "image_id": image_id,
        "source_id": source_id,
        "file_path": relative_to_root(target),
        "source_url": "",
        "license": source_row["license"],
        "modality": "TEM",
        "width": width,
        "height": height,
        "figure_label": f"page {page}" if page else "",
        "panel_label": panel_label,
        "caption": "",
        "file_sha256": sha256_file(target),
        "original_file_name": source_path.name,
        "curation_status": "accepted",
        "quality_status": "needs_review",
        "scale_status": "needs_manual_scale",
        "metadata_status": "needs_manual_review",
        "scale_nm": "",
        "scale_px": "",
        "nm_per_px": "",
        "split": "",
        "notes": f"Accepted from triage. Source PDF: {source_pdf}; page: {page}; panel: {panel_label}.",
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    upsert_rows(SOURCES_CSV, SOURCE_FIELDS, [source_row], "source_id")
    upsert_rows(IMAGES_CSV, IMAGE_FIELDS, [image_row], "image_id")
    return {"source": source_row, "image": image_row}


def main():
    parser = argparse.ArgumentParser(description="Accept one triaged figure crop/tile as a Corpus CVAT candidate.")
    parser.add_argument("--path", required=True)
    parser.add_argument("--source-pdf", default="")
    parser.add_argument("--page", default="")
    parser.add_argument("--panel-label", default="")
    args = parser.parse_args()
    result = accept_candidate(args.path, args.source_pdf, args.page, args.panel_label)
    print_json(
        {
            "ok": True,
            "message": "Accepted triage candidate for Corpus/CVAT review.",
            "image": result["image"],
        }
    )


if __name__ == "__main__":
    main()
