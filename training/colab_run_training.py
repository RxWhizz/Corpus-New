import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


CLASS_NAMES = ["Au_core", "SiO2_outer"]


def run(command):
    print("+", " ".join(str(part) for part in command), flush=True)
    subprocess.check_call([str(part) for part in command])


def ensure_ultralytics():
    try:
        import ultralytics  # noqa: F401
        return
    except Exception:
        run([sys.executable, "-m", "pip", "install", "-q", "ultralytics"])


def resolve_project_dir():
    drive_dir = Path("/content/drive/MyDrive")
    if drive_dir.exists():
        return drive_dir / "corpus_runs"
    return Path("/content/corpus_runs") if Path("/content").exists() else Path("runs")


def extract_bundle(bundle_path, work_dir):
    bundle_path = Path(bundle_path)
    if not bundle_path.exists():
        raise SystemExit(f"Bundle not found: {bundle_path}")
    work_dir = Path(work_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path, "r") as archive:
        archive.extractall(work_dir)
    dataset_dir = work_dir / "dataset"
    if not (dataset_dir / "data.yaml").exists():
        raise SystemExit(f"Bundle does not contain dataset/data.yaml: {bundle_path}")
    return dataset_dir


def patch_data_yaml(dataset_dir):
    dataset_dir = Path(dataset_dir)
    yaml_path = dataset_dir / "data.yaml"
    abs_path = dataset_dir.resolve().as_posix()
    lines = yaml_path.read_text(encoding="utf-8").splitlines()

    def has_images(split):
        d = dataset_dir / "images" / split
        return d.exists() and any(d.iterdir())

    patched = []
    for line in lines:
        if line.startswith("path:"):
            patched.append(f"path: {abs_path}")
        elif line.startswith("val:") and not has_images("val"):
            patched.append("val: images/train")
        elif line.startswith("test:") and not has_images("test"):
            patched.append("test: images/train")
        else:
            patched.append(line)
    yaml_path.write_text("\n".join(patched) + "\n", encoding="utf-8")


def resolve_dataset(args):
    if args.bundle:
        dataset_dir = extract_bundle(args.bundle, args.work_dir)
    elif args.dataset:
        dataset_dir = Path(args.dataset)
        if not (dataset_dir / "data.yaml").exists():
            raise SystemExit(f"Dataset does not contain data.yaml: {dataset_dir}")
    else:
        raise SystemExit("Provide --bundle or --dataset.")
    patch_data_yaml(dataset_dir)
    return dataset_dir


def audit_dataset(dataset_dir):
    dataset_dir = Path(dataset_dir)
    errors = []
    warnings = []
    counts = {"train": 0, "val": 0, "test": 0}
    class_counts = {name: 0 for name in CLASS_NAMES}
    label_rows = 0

    data_yaml = dataset_dir / "data.yaml"
    if not data_yaml.exists():
        errors.append("Missing data.yaml.")

    for split in counts:
        image_dir = dataset_dir / "images" / split
        label_dir = dataset_dir / "labels" / split
        images = sorted(path for path in image_dir.glob("*") if path.is_file()) if image_dir.exists() else []
        counts[split] = len(images)
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
                else:
                    class_counts[CLASS_NAMES[class_id]] += 1
                if any(value < 0 or value > 1 for value in coords):
                    errors.append(f"Coordinates outside [0,1] in {label}:{line_number}.")
                label_rows += 1

    if counts["train"] == 0:
        errors.append("No training images.")
    if counts["val"] == 0:
        warnings.append("No validation images. OK for smoke, not for v0.")
    if class_counts["Au_core"] == 0:
        errors.append("No Au_core labels.")
    if class_counts["SiO2_outer"] == 0:
        errors.append("No SiO2_outer labels.")

    result = {
        "ok": not errors,
        "counts": counts,
        "class_counts": class_counts,
        "label_rows": label_rows,
        "errors": errors,
        "warnings": warnings,
    }
    print(json.dumps(result, indent=2), flush=True)
    return result


def load_segment_model(preferred, fallback):
    from ultralytics import YOLO

    try:
        print(f"Loading {preferred}")
        return YOLO(preferred), preferred
    except Exception as exc:
        print(f"Could not load {preferred}: {exc}")
        print(f"Falling back to {fallback}")
        return YOLO(fallback), fallback


def train(dataset_dir, args):
    ensure_ultralytics()
    model_name = args.full_model if args.full and not args.smoke_only else args.smoke_model
    model, loaded_name = load_segment_model(model_name, args.fallback_model)
    project = Path(args.project) if args.project else resolve_project_dir()
    project.mkdir(parents=True, exist_ok=True)
    epochs = args.epochs if args.full and not args.smoke_only else 1
    batch = args.batch if args.full and not args.smoke_only else args.smoke_batch
    run_name = args.name if args.full and not args.smoke_only else "smoke_yolo_seg"
    results = model.train(
        data=str(Path(dataset_dir) / "data.yaml"),
        epochs=epochs,
        imgsz=args.imgsz,
        batch=batch,
        patience=args.patience,
        project=str(project),
        name=run_name,
    )
    print({"model": loaded_name, "project": str(project), "results": str(results)}, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Run Corpus YOLO-Seg training from a Colab bundle or dataset folder.")
    parser.add_argument("--bundle", default="", help="Path to corpus_colab_training_bundle.zip.")
    parser.add_argument("--dataset", default="", help="Path to a prepared YOLO-seg dataset folder.")
    parser.add_argument("--work-dir", default="/content/corpus_bundle" if Path("/content").exists() else "colab_bundle_work")
    parser.add_argument("--project", default="")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--smoke-model", default="yolo11n-seg.pt")
    parser.add_argument("--full-model", default="yolo11s-seg.pt")
    parser.add_argument("--fallback-model", default="yolo11n-seg.pt")
    parser.add_argument("--epochs", type=int, default=75)
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--smoke-batch", type=int, default=2)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--name", default="corpus_yolo_seg_v0")
    args = parser.parse_args()

    dataset_dir = resolve_dataset(args)
    audit = audit_dataset(dataset_dir)
    if not audit["ok"]:
        raise SystemExit("Dataset audit failed.")
    if args.audit_only:
        return
    train(dataset_dir, args)


if __name__ == "__main__":
    main()
