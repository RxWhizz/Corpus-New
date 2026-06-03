import argparse
import csv
from pathlib import Path

from common_training import DEFAULT_YOLO_DIR, CLASS_NAMES


def audit_dataset(dataset_dir):
    dataset_dir = Path(dataset_dir)
    errors = []
    warnings = []
    counts = {"train": 0, "val": 0, "test": 0}
    label_rows = 0

    data_yaml = dataset_dir / "data.yaml"
    if not data_yaml.exists():
        errors.append("Missing data.yaml.")

    groups_by_split = {}
    manifest_path = dataset_dir / "manifest.csv"
    if manifest_path.exists():
        with manifest_path.open("r", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                groups_by_split.setdefault(row.get("source_id", ""), set()).add(row.get("split", ""))

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
                if class_id < 0 or class_id >= len(CLASS_NAMES):
                    errors.append(f"Invalid class id {class_id} in {label}:{line_number}.")
                if any(value < 0 or value > 1 for value in coords):
                    errors.append(f"Coordinates outside [0,1] in {label}:{line_number}.")
                label_rows += 1

    if counts["train"] == 0:
        errors.append("No training images.")
    if counts["val"] == 0:
        warnings.append("No validation images. Add more annotated sources before real training.")
    if counts["test"] == 0:
        warnings.append("No test images. This is acceptable for smoke tests, but not for dataset v0.")
    if label_rows == 0:
        errors.append("No label polygons found.")

    return {"ok": not errors, "counts": counts, "label_rows": label_rows, "errors": errors, "warnings": warnings}


def main():
    parser = argparse.ArgumentParser(description="Audit a prepared YOLO segmentation dataset.")
    parser.add_argument("--dataset", default=str(DEFAULT_YOLO_DIR))
    args = parser.parse_args()
    result = audit_dataset(args.dataset)
    print(result)
    raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
