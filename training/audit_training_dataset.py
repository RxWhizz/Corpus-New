import argparse
import csv
import re
from pathlib import Path

from common_training import DEFAULT_YOLO_DIR, CLASS_NAMES, TRAINING_AUDIT_MD


def write_report(path, result):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Corpus Training Dataset Audit",
        "",
        f"- OK: {result['ok']}",
        f"- Images train/val/test: {result['counts']}",
        f"- Label rows: {result['label_rows']}",
        f"- Class counts: {result['class_counts']}",
        f"- Dataset layers: {result['dataset_layers']}",
        "",
        "## Errors",
    ]
    lines.extend(f"- {item}" for item in result["errors"]) if result["errors"] else lines.append("- None")
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in result["warnings"]) if result["warnings"] else lines.append("- None")
    path.write_text("\n".join(lines), encoding="utf-8")


def class_names_from_data_yaml(data_yaml):
    if not data_yaml.exists():
        return list(CLASS_NAMES)
    names = {}
    in_names = False
    for raw_line in data_yaml.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if re.match(r"^\s*names\s*:", line):
            in_names = True
            continue
        if in_names:
            if not line.strip():
                continue
            if not raw_line.startswith((" ", "\t")):
                break
            match = re.match(r"^\s*(\d+)\s*:\s*(.+?)\s*$", raw_line)
            if match:
                names[int(match.group(1))] = match.group(2).strip().strip("'\"")
    if not names:
        return list(CLASS_NAMES)
    return [names[index] for index in sorted(names)]


def audit_dataset(dataset_dir, min_images=0, min_au_core=0, min_sio2_outer=0, require_test=False):
    dataset_dir = Path(dataset_dir)
    errors = []
    warnings = []
    counts = {"train": 0, "val": 0, "test": 0}
    dataset_layers = {}
    label_rows = 0

    data_yaml = dataset_dir / "data.yaml"
    if not data_yaml.exists():
        errors.append("Missing data.yaml.")
    class_names = class_names_from_data_yaml(data_yaml)
    class_counts = {name: 0 for name in class_names}

    groups_by_split = {}
    manifest_path = dataset_dir / "manifest.csv"
    if manifest_path.exists():
        with manifest_path.open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                group = row.get("source_id") or row.get("source_group") or row.get("doi") or row.get("image_id") or row.get("file_name", "")
                groups_by_split.setdefault(group, set()).add(row.get("split", ""))
                layer = row.get("dataset_layer", "") or "unspecified"
                dataset_layers[layer] = dataset_layers.get(layer, 0) + 1
                if not row.get("nm_per_px") and layer not in {"real_near_emps"}:
                    warnings.append(f"Missing nm_per_px in manifest for {row.get('image_id') or row.get('image_path')}.")
                if layer == "public_demo" and row.get("license_status") not in {"accepted", "public", "cc_by", "cc0"}:
                    warnings.append(f"Public demo row lacks accepted license status: {row.get('image_id') or row.get('image_path')}.")

    for group, splits in groups_by_split.items():
        if len(splits) > 1:
            errors.append(f"Source group appears in multiple splits: {group} -> {sorted(splits)}")

    for split in counts:
        image_dir = dataset_dir / "images" / split
        label_dir = dataset_dir / "labels" / split
        images = sorted(path for path in image_dir.glob("*") if path.is_file()) if image_dir.exists() else []
        counts[split] = len(images)
        if images and not label_dir.exists():
            errors.append(f"Missing label directory for split {split}.")
        for image in images:
            label = label_dir / f"{image.stem}.txt"
            if not label.exists():
                errors.append(f"Missing label for {image}.")
                continue
            lines = [line.strip() for line in label.read_text(encoding="utf-8").splitlines() if line.strip()]
            if not lines:
                errors.append(f"Empty label file for {image}.")
                continue
            for line_number, line in enumerate(lines, start=1):
                parts = line.split()
                if len(parts) < 7 or len(parts) % 2 == 0:
                    errors.append(f"Invalid polygon line {label}:{line_number}.")
                    continue
                try:
                    class_id = int(parts[0])
                    coords = [float(value) for value in parts[1:]]
                except ValueError:
                    errors.append(f"Non-numeric label values {label}:{line_number}.")
                    continue
                if class_id < 0 or class_id >= len(class_names):
                    errors.append(f"Invalid class id {class_id} in {label}:{line_number}.")
                else:
                    class_counts[class_names[class_id]] += 1
                if any(value < 0 or value > 1 for value in coords):
                    errors.append(f"Coordinates outside [0,1] in {label}:{line_number}.")
                label_rows += 1

    if counts["train"] == 0:
        errors.append("No training images.")
    if counts["val"] == 0:
        warnings.append("No validation images. Add more annotated sources before real training.")
    if counts["test"] == 0 and require_test:
        errors.append("No test images.")
    elif counts["test"] == 0:
        warnings.append("No test images. This is acceptable for smoke tests, but not for dataset v0.")
    if label_rows == 0:
        errors.append("No label polygons found.")
    if sum(counts.values()) < min_images:
        errors.append(f"Dataset has {sum(counts.values())} images; minimum required is {min_images}.")
    if "Au_core" in class_counts and class_counts["Au_core"] < min_au_core:
        errors.append(f"Au_core labels {class_counts['Au_core']} below minimum {min_au_core}.")
    if "SiO2_outer" in class_counts and class_counts["SiO2_outer"] < min_sio2_outer:
        errors.append(f"SiO2_outer labels {class_counts['SiO2_outer']} below minimum {min_sio2_outer}.")

    return {
        "ok": not errors,
        "counts": counts,
        "label_rows": label_rows,
        "class_counts": class_counts,
        "dataset_layers": dataset_layers,
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit a prepared YOLO segmentation dataset.")
    parser.add_argument("--dataset", default=str(DEFAULT_YOLO_DIR))
    parser.add_argument("--min-images", type=int, default=0)
    parser.add_argument("--min-au-core", type=int, default=0)
    parser.add_argument("--min-sio2-outer", type=int, default=0)
    parser.add_argument("--require-test", action="store_true")
    parser.add_argument("--report", default=str(TRAINING_AUDIT_MD))
    args = parser.parse_args()
    result = audit_dataset(
        args.dataset,
        min_images=args.min_images,
        min_au_core=args.min_au_core,
        min_sio2_outer=args.min_sio2_outer,
        require_test=args.require_test,
    )
    write_report(args.report, result)
    print(result)
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
