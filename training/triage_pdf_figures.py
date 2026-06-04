import argparse
import csv
import json
import math
import re
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "data" / "interim" / "figures" / "pdf_extracted"
DEFAULT_OUTPUT = ROOT / "data" / "interim" / "figures" / "triaged"
DEFAULT_REPORT = ROOT / "reports" / "figure_triage_audit.md"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp"}

MANIFEST_FIELDS = [
    "source_pdf",
    "page",
    "image_path",
    "crop_path",
    "tile_path",
    "classification",
    "confidence",
    "panel_label",
    "scale_bar_detected",
    "is_multipanel",
    "is_crowded",
    "review_status",
    "reason",
    "tem_score",
    "graph_score",
    "abstract_score",
    "panel_score",
    "crowding_score",
    "width",
    "height",
]


def rel(path):
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def safe_name(value, fallback="item"):
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("_")
    return (cleaned[:90] or fallback)


def image_read(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def image_write(path, image):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".png"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        raise ValueError(f"Could not encode image: {path}")
    encoded.tofile(str(path))


def copy_image(src, dst):
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def clamp01(value):
    return max(0.0, min(1.0, float(value)))


def band_ranges(mask, min_width=8):
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


def split_positions_from_white_gutters(gray, axis):
    if axis == "x":
        projection = gray.mean(axis=0)
        spread = gray.std(axis=0)
        length = gray.shape[1]
    else:
        projection = gray.mean(axis=1)
        spread = gray.std(axis=1)
        length = gray.shape[0]
    gutters = (projection > 242) & (spread < 12)
    positions = []
    for start, end in band_ranges(gutters, max(8, length // 180)):
        center = (start + end) // 2
        if length * 0.08 < center < length * 0.92:
            positions.append(center)
    return positions


def crop_boxes_for_positions(width, height, x_positions, y_positions):
    if x_positions and (not y_positions or len(x_positions) >= len(y_positions)):
        edges = [0] + sorted(x_positions) + [width]
        return [(edges[i], 0, edges[i + 1], height) for i in range(len(edges) - 1)]
    if y_positions:
        edges = [0] + sorted(y_positions) + [height]
        return [(0, edges[i], width, edges[i + 1]) for i in range(len(edges) - 1)]
    return []


def fallback_aspect_panel_boxes(width, height):
    ratio = width / max(1, height)
    if ratio > 2.25:
        count = min(4, max(2, round(ratio)))
        step = width / count
        return [(round(i * step), 0, round((i + 1) * step), height) for i in range(count)]
    if ratio < 0.44:
        count = min(4, max(2, round(1 / ratio)))
        step = height / count
        return [(0, round(i * step), width, round((i + 1) * step)) for i in range(count)]
    return []


def detect_panel_boxes(image):
    height, width = image.shape[:2]
    if min(width, height) < 380:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    x_positions = split_positions_from_white_gutters(gray, "x")
    y_positions = split_positions_from_white_gutters(gray, "y")
    boxes = crop_boxes_for_positions(width, height, x_positions, y_positions)
    if not boxes:
        boxes = fallback_aspect_panel_boxes(width, height)
    clean = []
    for x1, y1, x2, y2 in boxes:
        crop_w = x2 - x1
        crop_h = y2 - y1
        if crop_w >= 300 and crop_h >= 300 and crop_w * crop_h >= 0.12 * width * height:
            clean.append((max(0, x1), max(0, y1), min(width, x2), min(height, y2)))
    return clean if len(clean) >= 2 else []


def detect_scale_bar(gray):
    height, width = gray.shape[:2]
    roi_y0 = int(height * 0.55)
    roi = gray[roi_y0:, :]
    candidates = []
    masks = [
        cv2.threshold(roi, 235, 255, cv2.THRESH_BINARY)[1],
        cv2.threshold(roi, 35, 255, cv2.THRESH_BINARY_INV)[1],
    ]
    for mask in masks:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if max(35, width * 0.06) <= w <= width * 0.45 and 2 <= h <= max(28, height * 0.04) and w / max(1, h) >= 5:
                if y + roi_y0 > height * 0.62 and x > width * 0.25:
                    candidates.append((x, y + roi_y0, w, h))
    if not candidates:
        return False, 0.0
    best = max(candidates, key=lambda box: box[2] / max(1, box[3]))
    confidence = clamp01((best[2] / max(1, width * 0.18)) * 0.6 + 0.3)
    return True, confidence


def line_features(gray):
    height, width = gray.shape[:2]
    edges = cv2.Canny(gray, 60, 160)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(60, min(width, height) // 4), minLineLength=max(80, min(width, height) // 3), maxLineGap=12)
    horizontal = 0
    vertical = 0
    long_lines = 0
    if lines is not None:
        for line in lines[:, 0, :]:
            x1, y1, x2, y2 = line
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            length = math.hypot(dx, dy)
            if length < min(width, height) * 0.25:
                continue
            long_lines += 1
            if dy <= max(4, dx * 0.08):
                horizontal += 1
            if dx <= max(4, dy * 0.08):
                vertical += 1
    axis_score = clamp01((min(horizontal, 4) + min(vertical, 4)) / 6)
    return axis_score, long_lines, float(edges.mean() / 255.0)


def component_text_score(gray):
    height, width = gray.shape[:2]
    _, binary_dark = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary_dark)
    small = 0
    for label in range(1, count):
        x, y, w, h, area = stats[label]
        if 4 <= w <= 80 and 5 <= h <= 60 and 12 <= area <= 1600:
            if y < height * 0.20 or y > height * 0.70 or x < width * 0.20 or x > width * 0.70:
                small += 1
    return clamp01(small / 70)


def classify_image(image):
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation_mean = float(hsv[:, :, 1].mean())
    saturation_high = float((hsv[:, :, 1] > 70).mean())
    white_fraction = float((gray > 238).mean())
    dark_fraction = float((gray < 45).mean())
    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    texture_score = clamp01(math.log1p(lap_var) / math.log(900))
    scale_detected, scale_confidence = detect_scale_bar(gray)
    axis_score, long_lines, edge_density = line_features(gray)
    text_score = component_text_score(gray)
    color_score = clamp01(saturation_mean / 95 + saturation_high * 0.6)
    gray_score = clamp01(1 - saturation_mean / 45)
    panel_boxes = detect_panel_boxes(image)
    panel_score = clamp01(len(panel_boxes) / 3)
    crowding_score = clamp01((dark_fraction * 2.5) + (edge_density * 4.0) + max(0.0, texture_score - 0.55) * 0.9)

    graph_score = clamp01(axis_score * 0.55 + white_fraction * 0.25 + text_score * 0.25 + (long_lines >= 2) * 0.15 - scale_confidence * 0.20)
    abstract_score = clamp01(color_score * 0.65 + (1 - texture_score) * 0.15 + text_score * 0.15 + white_fraction * 0.08 - scale_confidence * 0.20)
    tem_score = clamp01(gray_score * 0.34 + texture_score * 0.28 + scale_confidence * 0.22 + edge_density * 0.18 + (1 - axis_score) * 0.18 - color_score * 0.22)

    if panel_boxes and panel_score >= 0.65:
        classification = "mixed_figure"
        confidence = max(0.62, panel_score)
        reason = f"detected {len(panel_boxes)} likely panel crops"
    elif abstract_score >= 0.48 and color_score >= 0.25 and scale_confidence < 0.25 and axis_score < 0.75:
        classification = "abstract_or_scheme"
        confidence = clamp01(0.55 + color_score * 0.35 - axis_score * 0.15)
        reason = "color/schematic features without scale bar or graph axes"
    else:
        scores = {
            "tem": tem_score,
            "graph": graph_score,
            "abstract_or_scheme": abstract_score,
        }
        classification, top_score = max(scores.items(), key=lambda item: item[1])
        sorted_scores = sorted(scores.values(), reverse=True)
        margin = sorted_scores[0] - sorted_scores[1]
        confidence = clamp01(top_score * 0.72 + margin * 0.55)
        if confidence < 0.48:
            classification = "needs_review"
            reason = "low confidence between visual classes"
        elif classification == "tem":
            reason = "grayscale textured image with TEM-like contrast"
        elif classification == "graph":
            reason = "axis/line/text structure resembles a graph"
        else:
            reason = "color/schematic/text features resemble an abstract or scheme"

    return {
        "classification": classification,
        "confidence": confidence,
        "reason": reason,
        "tem_score": tem_score,
        "graph_score": graph_score,
        "abstract_score": abstract_score,
        "panel_score": panel_score,
        "crowding_score": crowding_score,
        "scale_bar_detected": bool(scale_detected),
        "is_multipanel": bool(panel_boxes),
        "is_crowded": bool(crowding_score >= 0.58 and classification in {"tem", "mixed_figure"}),
        "panel_boxes": panel_boxes,
        "width": width,
        "height": height,
    }


def output_dir_for_class(out_root, classification):
    mapping = {
        "tem": "tem_candidates",
        "graph": "graphs",
        "abstract_or_scheme": "abstracts_or_schemes",
        "mixed_figure": "mixed",
        "needs_review": "needs_review",
    }
    return Path(out_root) / mapping.get(classification, "needs_review")


def page_from_name(path):
    match = re.match(r"(\d{3})_", Path(path).name)
    return str(int(match.group(1))) if match else ""


def load_source_pdf_map(input_root):
    summary = Path(input_root) / "extraction_summary.csv"
    mapping = {}
    if not summary.exists():
        return mapping
    with summary.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            out_dir = Path(row.get("output_dir", ""))
            if out_dir.name:
                mapping[out_dir.name] = row.get("pdf", "")
    return mapping


def base_row(source_pdf, source_path, derived_path, tile_path, features, classification=None, panel_label=""):
    row_class = classification or features["classification"]
    confidence = features["confidence"]
    review_status = "auto_candidate" if row_class == "tem" and confidence >= 0.55 else "needs_review"
    if row_class in {"graph", "abstract_or_scheme"} and confidence >= 0.55:
        review_status = "auto_rejected"
    return {
        "source_pdf": source_pdf,
        "page": page_from_name(source_path),
        "image_path": rel(source_path),
        "crop_path": rel(derived_path) if derived_path else "",
        "tile_path": rel(tile_path) if tile_path else "",
        "classification": row_class,
        "confidence": f"{confidence:.4f}",
        "panel_label": panel_label,
        "scale_bar_detected": str(bool(features["scale_bar_detected"])).lower(),
        "is_multipanel": str(bool(features["is_multipanel"])).lower(),
        "is_crowded": str(bool(features["is_crowded"])).lower(),
        "review_status": review_status,
        "reason": features["reason"],
        "tem_score": f"{features['tem_score']:.4f}",
        "graph_score": f"{features['graph_score']:.4f}",
        "abstract_score": f"{features['abstract_score']:.4f}",
        "panel_score": f"{features['panel_score']:.4f}",
        "crowding_score": f"{features['crowding_score']:.4f}",
        "width": str(features["width"]),
        "height": str(features["height"]),
    }


def should_keep_tile(tile, features):
    gray = cv2.cvtColor(tile, cv2.COLOR_BGR2GRAY)
    white_fraction = float((gray > 242).mean())
    dark_fraction = float((gray < 70).mean())
    if white_fraction > 0.88 or dark_fraction < 0.015:
        return False
    tile_features = classify_image(tile)
    return tile_features["tem_score"] >= 0.42 or features["tem_score"] >= 0.55


def tile_tem_image(image, out_dir, stem, tile_size=1024, overlap=0.20):
    height, width = image.shape[:2]
    if width < tile_size * 1.15 and height < tile_size * 1.15:
        return []
    step = max(128, int(tile_size * (1 - overlap)))
    paths = []
    y_values = list(range(0, max(1, height - tile_size + 1), step))
    x_values = list(range(0, max(1, width - tile_size + 1), step))
    if y_values[-1] != max(0, height - tile_size):
        y_values.append(max(0, height - tile_size))
    if x_values[-1] != max(0, width - tile_size):
        x_values.append(max(0, width - tile_size))
    for y in y_values:
        for x in x_values:
            tile = image[y : min(height, y + tile_size), x : min(width, x + tile_size)]
            if tile.shape[0] < 420 or tile.shape[1] < 420:
                continue
            tile_path = out_dir / f"{stem}_tile_y{y}_x{x}.png"
            paths.append((tile_path, tile))
    return paths


def process_one_image(path, input_root, out_root, source_map, tile_size, overlap):
    image = image_read(path)
    source_pdf = source_map.get(Path(path).parent.name, Path(path).parent.name)
    stem = safe_name(f"{Path(path).parent.name}_{Path(path).stem}")
    rows = []
    features = classify_image(image)

    if features["classification"] == "mixed_figure" and features["panel_boxes"]:
        mixed_path = output_dir_for_class(out_root, "mixed_figure") / f"{stem}.png"
        copy_image(path, mixed_path)
        rows.append(base_row(source_pdf, path, mixed_path, "", features, "mixed_figure"))
        for index, (x1, y1, x2, y2) in enumerate(features["panel_boxes"], start=1):
            crop = image[y1:y2, x1:x2]
            crop_features = classify_image(crop)
            panel_label = chr(ord("A") + index - 1) if index <= 26 else str(index)
            crop_class = crop_features["classification"]
            crop_path = output_dir_for_class(out_root, crop_class) / f"{stem}_panel_{panel_label}.png"
            image_write(crop_path, crop)
            rows.append(base_row(source_pdf, path, crop_path, "", crop_features, crop_class, panel_label))
            if crop_class == "tem" and crop_features["is_crowded"]:
                tile_dir = Path(out_root) / "tiles"
                for tile_path, tile in tile_tem_image(crop, tile_dir, f"{stem}_panel_{panel_label}", tile_size, overlap):
                    if should_keep_tile(tile, crop_features):
                        image_write(tile_path, tile)
                        tile_features = classify_image(tile)
                        tile_features["is_crowded"] = True
                        rows.append(base_row(source_pdf, path, crop_path, tile_path, tile_features, "tem", panel_label))
        return rows

    output_path = output_dir_for_class(out_root, features["classification"]) / f"{stem}.png"
    copy_image(path, output_path)
    rows.append(base_row(source_pdf, path, output_path, "", features))
    if features["classification"] == "tem" and features["is_crowded"]:
        tile_dir = Path(out_root) / "tiles"
        for tile_path, tile in tile_tem_image(image, tile_dir, stem, tile_size, overlap):
            if should_keep_tile(tile, features):
                image_write(tile_path, tile)
                tile_features = classify_image(tile)
                tile_features["is_crowded"] = True
                rows.append(base_row(source_pdf, path, output_path, tile_path, tile_features, "tem"))
    return rows


def write_manifest(rows, out_root):
    manifest = Path(out_root) / "figure_triage_manifest.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in MANIFEST_FIELDS})
    return manifest


def write_audit(rows, report_path):
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    class_counts = Counter(row["classification"] for row in rows)
    review_counts = Counter(row["review_status"] for row in rows)
    tile_count = sum(1 for row in rows if row.get("tile_path"))
    scale_count = sum(1 for row in rows if row.get("scale_bar_detected") == "true")
    lines = [
        "# Figure Triage Audit",
        "",
        f"- Rows: {len(rows)}",
        f"- Tile rows: {tile_count}",
        f"- Scale bar detected rows: {scale_count}",
        "",
        "## Classifications",
    ]
    lines.extend(f"- {name}: {count}" for name, count in sorted(class_counts.items()))
    lines.extend(["", "## Review Status"])
    lines.extend(f"- {name}: {count}" for name, count in sorted(review_counts.items()))
    lines.extend(["", "## Notes", "- Graphs and abstract/scheme images are retained for audit but excluded from CVAT candidates.", "- TEM tiles are candidates for manual review/annotation, not final particle masks."])
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_triage(input_dir, out_dir, tile_size=1024, overlap=0.20, clean=False, report_path=DEFAULT_REPORT):
    input_dir = Path(input_dir)
    out_dir = Path(out_dir)
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    for folder in ["tem_candidates", "graphs", "abstracts_or_schemes", "mixed", "needs_review", "tiles"]:
        (out_dir / folder).mkdir(parents=True, exist_ok=True)
    source_map = load_source_pdf_map(input_dir)
    image_paths = [path for path in sorted(input_dir.rglob("*")) if path.suffix.lower() in IMAGE_EXTS]
    rows = []
    errors = []
    for path in image_paths:
        try:
            rows.extend(process_one_image(path, input_dir, out_dir, source_map, tile_size, overlap))
        except Exception as exc:
            errors.append({"image_path": rel(path), "error": str(exc)})
            features = {
                "classification": "needs_review",
                "confidence": 0,
                "reason": f"triage_error: {exc}",
                "tem_score": 0,
                "graph_score": 0,
                "abstract_score": 0,
                "panel_score": 0,
                "crowding_score": 0,
                "scale_bar_detected": False,
                "is_multipanel": False,
                "is_crowded": False,
                "width": "",
                "height": "",
            }
            rows.append(base_row(Path(path).parent.name, path, "", "", features, "needs_review"))
    manifest = write_manifest(rows, out_dir)
    report = write_audit(rows, report_path)
    return {
        "input_images": len(image_paths),
        "rows": len(rows),
        "manifest": manifest,
        "report": report,
        "errors": errors,
        "counts": dict(Counter(row["classification"] for row in rows)),
        "tiles": sum(1 for row in rows if row.get("tile_path")),
    }


def make_self_test_images(root):
    root.mkdir(parents=True, exist_ok=True)
    tem = np.full((700, 900, 3), 200, np.uint8)
    noise = np.random.default_rng(7).normal(0, 16, tem.shape[:2]).astype(np.int16)
    for channel in range(3):
        tem[:, :, channel] = np.clip(tem[:, :, channel].astype(np.int16) + noise, 0, 255)
    for x, y, r in [(220, 260, 75), (320, 285, 70), (490, 300, 82), (610, 280, 65), (510, 430, 80)]:
        cv2.circle(tem, (x, y), r, (120, 120, 120), -1)
        cv2.circle(tem, (x, y), max(15, r // 3), (35, 35, 35), -1)
    cv2.rectangle(tem, (650, 630), (820, 642), (255, 255, 255), -1)
    image_write(root / "001_01_tem.png", tem)

    graph = np.full((650, 850, 3), 255, np.uint8)
    cv2.line(graph, (90, 560), (780, 560), (0, 0, 0), 4)
    cv2.line(graph, (90, 80), (90, 560), (0, 0, 0), 4)
    for i in range(8):
        x = 120 + i * 80
        cv2.line(graph, (x, 560), (x, 545), (0, 0, 0), 2)
        cv2.circle(graph, (x, 480 - i * 38), 8, (30, 70, 220), -1)
    image_write(root / "002_01_graph.png", graph)

    abstract = np.full((650, 850, 3), 250, np.uint8)
    cv2.circle(abstract, (220, 300), 130, (40, 160, 240), -1)
    cv2.rectangle(abstract, (420, 180), (720, 430), (240, 120, 50), -1)
    cv2.arrowedLine(abstract, (340, 300), (420, 300), (30, 30, 30), 8)
    image_write(root / "003_01_abstract.png", abstract)

    graph_panel = cv2.resize(graph[:, :450], (450, tem.shape[0]))
    mixed = np.concatenate([tem[:, :450], graph_panel], axis=1)
    image_write(root / "004_01_mixed.png", mixed)


def self_test():
    with tempfile.TemporaryDirectory(prefix="corpus_triage_") as tmp:
        input_dir = Path(tmp) / "input" / "pdf_001_fixture"
        out_dir = Path(tmp) / "out"
        make_self_test_images(input_dir)
        result = run_triage(input_dir.parent, out_dir, tile_size=512, clean=True, report_path=Path(tmp) / "audit.md")
        counts = Counter()
        with (out_dir / "figure_triage_manifest.csv").open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                counts[row["classification"]] += 1
        assert counts["tem"] >= 1, counts
        assert counts["graph"] >= 1, counts
        assert counts["abstract_or_scheme"] >= 1, counts
        assert counts["mixed_figure"] >= 1, counts
        return result


def main():
    parser = argparse.ArgumentParser(description="Classify extracted paper figures into TEM, graphs, abstracts/schemes, mixed figures, and review candidates.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Folder containing extracted PDF figure images.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT), help="Output folder for triaged images and manifest.")
    parser.add_argument("--tile-size", type=int, default=1024)
    parser.add_argument("--overlap", type=float, default=0.20)
    parser.add_argument("--clean", action="store_true", help="Delete the triage output folder before running.")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--self-test", action="store_true", help="Run synthetic smoke tests for the triage heuristics.")
    args = parser.parse_args()

    if args.self_test:
        result = self_test()
    else:
        result = run_triage(args.input, args.out, args.tile_size, args.overlap, args.clean, args.report)

    payload = {
        "ok": not result["errors"],
        "message": f"Triaged {result['input_images']} image(s) into {result['rows']} manifest row(s); {result['tiles']} tile row(s).",
        "manifest": rel(result["manifest"]),
        "report": rel(result["report"]),
        "counts": result["counts"],
        "tiles": result["tiles"],
        "errors": result["errors"],
    }
    print(json.dumps(payload, ensure_ascii=True))


if __name__ == "__main__":
    main()
