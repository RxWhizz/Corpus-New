import argparse
import csv
import json
import shutil
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "data" / "interim" / "figures" / "triaged" / "manual_review_summary.csv"
DEFAULT_OUT = ROOT / "data" / "interim" / "figures" / "triaged" / "tem_separated"
DEFAULT_CVAT = ROOT / "data" / "interim" / "figures" / "triaged" / "tem_for_cvat"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def safe_stem(value):
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value).strip("_")[:90]


def read_image(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def write_image(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(path.suffix or ".png", image)
    if not ok:
        raise ValueError(f"Could not encode image: {path}")
    encoded.tofile(str(path))


def clean_dir(path):
    path = Path(path).resolve()
    allowed = (ROOT / "data" / "interim" / "figures" / "triaged").resolve()
    if path.exists():
        if not str(path).lower().startswith(str(allowed).lower()):
            raise ValueError(f"Refusing to clean outside triaged folder: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def content_ranges(mask, min_width=12):
    ranges = []
    start = None
    for index, keep in enumerate(mask):
        if keep and start is None:
            start = index
        elif not keep and start is not None:
            if index - start >= min_width:
                ranges.append((start, index))
            start = None
    if start is not None and len(mask) - start >= min_width:
        ranges.append((start, len(mask)))
    return ranges


def vertical_content_boxes(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    row_content = (gray < 248).mean(axis=1) > 0.08
    ranges = content_ranges(row_content, max(20, image.shape[0] // 18))
    if 2 <= len(ranges) <= 5:
        boxes = []
        for y1, y2 in ranges:
            crop_mask = (gray[y1:y2, :] < 248).mean(axis=0) > 0.03
            x_ranges = content_ranges(crop_mask, 10)
            if x_ranges:
                x1 = max(0, x_ranges[0][0] - 4)
                x2 = min(image.shape[1], x_ranges[-1][1] + 4)
            else:
                x1, x2 = 0, image.shape[1]
            boxes.append((x1, y1, x2, y2))
        return boxes
    return []


def two_by_two_boxes(width, height):
    mid_x = width // 2
    mid_y = height // 2
    return [
        (0, 0, mid_x, mid_y),
        (mid_x, 0, width, mid_y),
        (0, mid_y, mid_x, height),
        (mid_x, mid_y, width, height),
    ]


def two_top_one_bottom_boxes(image):
    height, width = image.shape[:2]
    mid_x = width // 2
    mid_y = height // 2
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    bottom = gray[mid_y:, :]
    non_black_cols = (bottom > 35).mean(axis=0) > 0.40
    x_ranges = content_ranges(non_black_cols, 20)
    if x_ranges:
        x1 = max(0, x_ranges[0][0] - 4)
        x2 = min(width, x_ranges[-1][1] + 4)
    else:
        x1, x2 = 0, width
    return [
        (0, 0, mid_x, mid_y),
        (mid_x, 0, width, mid_y),
        (x1, mid_y, x2, height),
    ]


def left_right_boxes(width, height):
    mid_x = width // 2
    return [(0, 0, mid_x, height), (mid_x, 0, width, height)]


def boxes_for_image(path, image):
    height, width = image.shape[:2]
    name = path.name.lower()
    if width > 1400 and 0.42 <= height / width <= 0.60:
        return left_right_boxes(width, height), "left_right_large_figure"
    if width < 520 and height > width * 1.8:
        boxes = vertical_content_boxes(image)
        return boxes or [(0, 0, width, height)], "vertical_panel_stack"
    if 0.82 <= width / max(1, height) <= 1.15 and min(width, height) > 900:
        if path.stem.lower() == "separar":
            return two_top_one_bottom_boxes(image), "two_top_one_bottom"
        return two_by_two_boxes(width, height), "two_by_two_grid"
    return [(0, 0, width, height)], "fallback_original"


def load_rows(summary_path):
    with Path(summary_path).open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_manifest(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_file",
        "output_file",
        "output_role",
        "panel_id",
        "split_method",
        "x1",
        "y1",
        "x2",
        "y2",
        "width",
        "height",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_contact_sheet(image_paths, out_path, thumb_width=260):
    if not image_paths:
        return
    thumbs = []
    for path in image_paths:
        image = read_image(path)
        h, w = image.shape[:2]
        scale = thumb_width / max(1, w)
        thumb = cv2.resize(image, (thumb_width, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        label = Path(path).stem[:34]
        canvas = np.full((thumb.shape[0] + 26, thumb.shape[1], 3), 255, dtype=np.uint8)
        canvas[: thumb.shape[0], :, :] = thumb
        cv2.putText(canvas, label, (4, canvas.shape[0] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (10, 10, 10), 1, cv2.LINE_AA)
        thumbs.append(canvas)
    columns = 4
    rows = []
    for index in range(0, len(thumbs), columns):
        group = thumbs[index : index + columns]
        max_h = max(item.shape[0] for item in group)
        padded = []
        for item in group:
            if item.shape[0] < max_h:
                pad = np.full((max_h - item.shape[0], item.shape[1], 3), 255, dtype=np.uint8)
                item = np.vstack([item, pad])
            padded.append(item)
        while len(padded) < columns:
            padded.append(np.full((max_h, thumb_width, 3), 255, dtype=np.uint8))
        rows.append(np.hstack(padded))
    sheet = np.vstack(rows)
    write_image(out_path, sheet)


def run(summary_path, separated_dir, cvat_dir, clean=False):
    separated_dir = Path(separated_dir)
    cvat_dir = Path(cvat_dir)
    if clean:
        clean_dir(separated_dir)
        clean_dir(cvat_dir)
    else:
        separated_dir.mkdir(parents=True, exist_ok=True)
        cvat_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(summary_path)
    manifest_rows = []
    separated_paths = []
    cvat_paths = []

    for row in rows:
        if row.get("manual_label") != "tem":
            continue
        source = ROOT / row["file_path"]
        if not source.exists() or source.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        stem = safe_stem(source.stem)
        if row.get("needs_split") == "true":
            image = read_image(source)
            boxes, method = boxes_for_image(source, image)
            for index, (x1, y1, x2, y2) in enumerate(boxes, start=1):
                crop = image[y1:y2, x1:x2]
                if crop.shape[0] < 120 or crop.shape[1] < 120:
                    continue
                panel_id = f"panel_{index:02d}"
                out_path = separated_dir / f"{stem}_{panel_id}.png"
                write_image(out_path, crop)
                separated_paths.append(out_path)
                cvat_path = cvat_dir / out_path.name
                shutil.copy2(out_path, cvat_path)
                cvat_paths.append(cvat_path)
                manifest_rows.append(
                    {
                        "source_file": rel(source),
                        "output_file": rel(out_path),
                        "output_role": "separated_panel",
                        "panel_id": panel_id,
                        "split_method": method,
                        "x1": x1,
                        "y1": y1,
                        "x2": x2,
                        "y2": y2,
                        "width": crop.shape[1],
                        "height": crop.shape[0],
                    }
                )
        else:
            cvat_path = cvat_dir / f"{stem}{source.suffix.lower()}"
            shutil.copy2(source, cvat_path)
            cvat_paths.append(cvat_path)
            image = read_image(source)
            manifest_rows.append(
                {
                    "source_file": rel(source),
                    "output_file": rel(cvat_path),
                    "output_role": "ready_tem_original",
                    "panel_id": "",
                    "split_method": "none",
                    "x1": 0,
                    "y1": 0,
                    "x2": image.shape[1],
                    "y2": image.shape[0],
                    "width": image.shape[1],
                    "height": image.shape[0],
                }
            )

    manifest = separated_dir / "tem_separation_manifest.csv"
    write_manifest(manifest, manifest_rows)
    make_contact_sheet(separated_paths, separated_dir / "tem_separated_contact_sheet.png")
    make_contact_sheet(cvat_paths, cvat_dir / "tem_for_cvat_contact_sheet.png")
    return {
        "ready_tem_originals": sum(1 for row in manifest_rows if row["output_role"] == "ready_tem_original"),
        "separated_panels": sum(1 for row in manifest_rows if row["output_role"] == "separated_panel"),
        "total_cvat_candidates": len(cvat_paths),
        "separated_dir": separated_dir,
        "cvat_dir": cvat_dir,
        "manifest": manifest,
    }


def main():
    parser = argparse.ArgumentParser(description="Separate TEM files marked with 'Separar' in the triage manual review summary.")
    parser.add_argument("--summary", default=str(DEFAULT_SUMMARY))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--cvat-out", default=str(DEFAULT_CVAT))
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    result = run(args.summary, args.out, args.cvat_out, args.clean)
    print(
        json.dumps(
            {
                "ok": True,
                "message": f"Separated {result['separated_panels']} panel(s) and prepared {result['total_cvat_candidates']} TEM CVAT candidate(s).",
                "ready_tem_originals": result["ready_tem_originals"],
                "separated_panels": result["separated_panels"],
                "total_cvat_candidates": result["total_cvat_candidates"],
                "separated_dir": rel(result["separated_dir"]),
                "cvat_dir": rel(result["cvat_dir"]),
                "manifest": rel(result["manifest"]),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
