import argparse
import csv
import json
import shutil
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EMPS_DIR = ROOT / "data" / "external" / "emps"
DEFAULT_OUT = ROOT / "data" / "training" / "emps_yolo_seg"
CLASS_NAME = "particle"


def clean_dir(path):
    path = Path(path).resolve()
    allowed = (ROOT / "data" / "training").resolve()
    if path.exists():
        if not str(path).lower().startswith(str(allowed).lower()):
            raise ValueError(f"Refusing to remove outside data/training: {path}")
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def read_ids(path):
    if not Path(path).exists():
        return []
    return [line.strip().replace(".png", "") for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def deterministic_val_split(train_ids, val_fraction=0.15):
    train_ids = sorted(train_ids)
    val_count = max(1, round(len(train_ids) * val_fraction))
    val_ids = set(train_ids[:: max(1, len(train_ids) // val_count)][:val_count])
    final_train = [item for item in train_ids if item not in val_ids]
    final_val = [item for item in train_ids if item in val_ids]
    return final_train, final_val


def deterministic_group_val_split(train_ids, metadata, val_fraction=0.15):
    groups = {}
    for image_id in sorted(train_ids):
        group = metadata.get(image_id, {}).get("doi") or image_id
        groups.setdefault(group, []).append(image_id)
    target = max(1, round(len(train_ids) * val_fraction))
    val_groups = set()
    val_total = 0
    for group, ids in sorted(groups.items(), key=lambda item: (len(item[1]), item[0])):
        if val_total >= target and val_groups:
            break
        val_groups.add(group)
        val_total += len(ids)
    val_ids = {image_id for group in val_groups for image_id in groups[group]}
    final_train = [item for item in sorted(train_ids) if item not in val_ids]
    final_val = [item for item in sorted(train_ids) if item in val_ids]
    return final_train, final_val


def read_image_size(path):
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    height, width = image.shape[:2]
    return width, height


def contour_to_yolo(contour, width, height):
    area = cv2.contourArea(contour)
    if area < 8:
        return None
    epsilon = max(0.7, 0.0025 * cv2.arcLength(contour, True))
    approx = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(approx) < 3:
        return None
    values = []
    for x, y in approx:
        values.extend(
            [
                min(1.0, max(0.0, float(x) / width)),
                min(1.0, max(0.0, float(y) / height)),
            ]
        )
    return values


def segmap_to_yolo_labels(segmap_path, width, height):
    segmap = cv2.imread(str(segmap_path), cv2.IMREAD_UNCHANGED)
    if segmap is None:
        raise ValueError(f"Could not read segmentation map: {segmap_path}")
    if segmap.shape[:2] != (height, width):
        segmap = cv2.resize(segmap, (width, height), interpolation=cv2.INTER_NEAREST)
    labels = []
    for instance_id in sorted(int(value) for value in np.unique(segmap) if int(value) != 0):
        mask = (segmap == instance_id).astype(np.uint8) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        polygon = contour_to_yolo(contour, width, height)
        if polygon:
            labels.append("0 " + " ".join(f"{value:.6f}" for value in polygon))
    return labels


def metadata_index(emps_dir):
    path = Path(emps_dir) / "metadata.csv"
    if not path.exists():
        return {}
    rows = {}
    with path.open("r", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            stem = Path(row.get("filename", "")).stem
            if stem:
                rows[stem] = row
    return rows


def copy_split(emps_dir, out_dir, split, image_ids, metadata):
    images_dir = out_dir / "images" / split
    labels_dir = out_dir / "labels" / split
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    warnings = []
    annotation_count = 0

    for image_id in image_ids:
        image_path = emps_dir / "images" / f"{image_id}.png"
        segmap_path = emps_dir / "segmaps" / f"{image_id}.png"
        if not image_path.exists() or not segmap_path.exists():
            warnings.append(f"Missing image or segmap for {image_id}")
            continue
        width, height = read_image_size(image_path)
        labels = segmap_to_yolo_labels(segmap_path, width, height)
        if not labels:
            warnings.append(f"No valid particle polygons for {image_id}")
            continue
        target_image = images_dir / image_path.name
        target_label = labels_dir / f"{image_id}.txt"
        shutil.copy2(image_path, target_image)
        target_label.write_text("\n".join(labels) + "\n", encoding="utf-8")
        annotation_count += len(labels)
        meta = metadata.get(image_id, {})
        manifest_rows.append(
            {
                "image_id": image_id,
                "file_name": image_path.name,
                "split": split,
                "dataset_layer": "real_near_emps",
                "source_dataset": "EMPS",
                "source_group": meta.get("doi", "") or image_id,
                "source_url": "https://github.com/by256/emps",
                "license": "CC BY 4.0 data / MIT repository; verify before redistribution",
                "doi": meta.get("doi", ""),
                "locator": meta.get("locator", ""),
                "width": width,
                "height": height,
                "instances": len(labels),
            }
        )
    return manifest_rows, warnings, annotation_count


def write_data_yaml(out_dir):
    (out_dir / "data.yaml").write_text(
        "\n".join(
            [
                f"path: {out_dir.resolve().as_posix()}",
                "train: images/train",
                "val: images/val",
                "test: images/test",
                "names:",
                f"  0: {CLASS_NAME}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_manifest(out_dir, rows):
    path = out_dir / "manifest.csv"
    fields = [
        "image_id",
        "file_name",
        "split",
        "dataset_layer",
        "source_dataset",
        "source_group",
        "source_url",
        "license",
        "doi",
        "locator",
        "width",
        "height",
        "instances",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_audit(out_dir, payload):
    report = ROOT / "reports" / "emps_yolo_dataset_audit.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# EMPS YOLO-Seg Dataset Audit",
        "",
        f"- Images train: {payload['splits'].get('train', 0)}",
        f"- Images val: {payload['splits'].get('val', 0)}",
        f"- Images test: {payload['splits'].get('test', 0)}",
        f"- Particle instances: {payload['instances']}",
        f"- Warnings: {len(payload['warnings'])}",
        "",
        "## Intended Use",
        "",
        "Use this as `real_near_emps` pretraining for a general EM particle detector/segmenter.",
        "Do not treat it as Au@SiO2 core-shell truth; it has one class: `particle`.",
        "",
        "## Warnings",
    ]
    if payload["warnings"]:
        lines.extend(f"- {warning}" for warning in payload["warnings"][:100])
    else:
        lines.append("- None")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def prepare(emps_dir, out_dir, val_fraction=0.15, clean=False):
    emps_dir = Path(emps_dir)
    out_dir = Path(out_dir)
    if clean:
        clean_dir(out_dir)
    else:
        out_dir.mkdir(parents=True, exist_ok=True)
    train_ids = read_ids(emps_dir / "train.csv")
    test_ids = read_ids(emps_dir / "test.csv")
    if not train_ids or not test_ids:
        all_ids = sorted(path.stem for path in (emps_dir / "images").glob("*.png"))
        test_count = max(1, round(len(all_ids) * 0.20))
        test_ids = all_ids[:test_count]
        train_ids = all_ids[test_count:]
    metadata = metadata_index(emps_dir)
    train_ids, val_ids = deterministic_group_val_split(train_ids, metadata, val_fraction)

    manifest_rows = []
    warnings = []
    instances = 0
    splits = {}
    for split, ids in [("train", train_ids), ("val", val_ids), ("test", test_ids)]:
        rows, split_warnings, count = copy_split(emps_dir, out_dir, split, ids, metadata)
        manifest_rows.extend(rows)
        warnings.extend(split_warnings)
        instances += count
        splits[split] = len(rows)

    write_data_yaml(out_dir)
    manifest = write_manifest(out_dir, manifest_rows)
    payload = {"splits": splits, "instances": instances, "warnings": warnings, "manifest": manifest}
    report = write_audit(out_dir, payload)
    payload["report"] = report
    return payload


def main():
    parser = argparse.ArgumentParser(description="Convert EMPS particle segmentation data to YOLO-seg format.")
    parser.add_argument("--emps-dir", default=str(DEFAULT_EMPS_DIR))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()
    result = prepare(args.emps_dir, args.out, args.val_fraction, args.clean)
    print(
        json.dumps(
            {
                "ok": not result["warnings"],
                "message": f"Prepared EMPS YOLO-seg with {sum(result['splits'].values())} images and {result['instances']} particle instances.",
                "dataset": str(Path(args.out)),
                "splits": result["splits"],
                "instances": result["instances"],
                "manifest": str(result["manifest"]),
                "report": str(result["report"]),
                "warnings": result["warnings"][:25],
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
