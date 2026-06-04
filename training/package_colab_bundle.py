import argparse
import shutil
import zipfile
from pathlib import Path

from audit_training_dataset import audit_dataset, write_report
from common_training import DEFAULT_IMPORTED_COCO, DEFAULT_YOLO_DIR, ROOT, TRAINING_AUDIT_MD
from generate_synthetic_core_shell import generate_dataset
from prepare_yolo_seg import prepare_yolo


DEFAULT_OUT = ROOT / "data" / "training" / "colab_bundle"
DEFAULT_ZIP_NAME = "corpus_colab_training_bundle.zip"


def copy_if_exists(source, target):
    source = Path(source)
    if not source.exists():
        return False
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def copy_dataset(yolo_dir, target_dir):
    yolo_dir = Path(yolo_dir)
    target_dir = Path(target_dir)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    required = ["data.yaml", "images", "labels"]
    missing = [name for name in required if not (yolo_dir / name).exists()]
    if missing:
        raise SystemExit(f"YOLO dataset is missing required entries: {missing}")

    for name in required:
        source = yolo_dir / name
        target = target_dir / name
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    for optional in ("manifest.csv", "prepare_warnings.txt"):
        copy_if_exists(yolo_dir / optional, target_dir / optional)


def make_zip(stage_dir, zip_path):
    zip_path = Path(zip_path)
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(Path(stage_dir).rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(stage_dir).as_posix())
    return zip_path


def prepare_source_dataset(args, work_dir):
    work_dir = Path(work_dir)
    if args.synthetic_smoke:
        synthetic_dir = work_dir / "synthetic_core_shell"
        yolo_dir = work_dir / "synthetic_yolo_seg"
        result = generate_dataset(
            synthetic_dir,
            count=args.synthetic_count,
            seed=args.synthetic_seed,
            height=args.synthetic_size,
            width=args.synthetic_size,
            min_particles=args.synthetic_min_particles,
            max_particles=args.synthetic_max_particles,
            nm_per_px=args.synthetic_nm_per_px,
        )
        prepare_yolo(result["coco"], yolo_dir)
        return yolo_dir

    if args.coco:
        yolo_dir = work_dir / "yolo_from_coco"
        prepare_yolo(args.coco, yolo_dir)
        return yolo_dir

    if args.yolo_dir:
        return Path(args.yolo_dir)

    default_coco = Path(DEFAULT_IMPORTED_COCO)
    if default_coco.exists():
        yolo_dir = work_dir / "yolo_from_default_coco"
        prepare_yolo(default_coco, yolo_dir)
        return yolo_dir

    default_yolo = Path(DEFAULT_YOLO_DIR)
    if (default_yolo / "data.yaml").exists():
        return default_yolo

    raise SystemExit("Provide --synthetic-smoke, --coco, or --yolo-dir. No default prepared dataset was found.")


def package_bundle(args):
    out_dir = Path(args.out)
    work_dir = out_dir / "_work"
    stage_dir = out_dir / "bundle_contents"
    if args.clean and out_dir.exists():
        shutil.rmtree(out_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    yolo_dir = prepare_source_dataset(args, work_dir)
    audit = audit_dataset(
        yolo_dir,
        min_images=args.min_images,
        min_au_core=args.min_au_core,
        min_sio2_outer=args.min_sio2_outer,
        require_test=args.require_test,
    )
    report_path = out_dir / "training_dataset_audit.md"
    write_report(report_path, audit)
    if not audit["ok"] and not args.allow_failed_audit:
        raise SystemExit(f"Dataset audit failed. See {report_path}")

    copy_dataset(yolo_dir, stage_dir / "dataset")
    copy_if_exists(report_path, stage_dir / "reports" / "training_dataset_audit.md")
    copy_if_exists(ROOT / "docs" / "dataset_sources.md", stage_dir / "docs" / "dataset_sources.md")
    copy_if_exists(ROOT / "docs" / "local_pdf_sources.md", stage_dir / "docs" / "local_pdf_sources.md")
    copy_if_exists(ROOT / "docs" / "comparison.md", stage_dir / "docs" / "comparison.md")
    copy_if_exists(ROOT / "training" / "README.md", stage_dir / "training" / "README.md")
    copy_if_exists(ROOT / "training" / "seed_sources.json", stage_dir / "training" / "seed_sources.json")
    copy_if_exists(ROOT / "training" / "colab_run_training.py", stage_dir / "training" / "colab_run_training.py")
    copy_if_exists(ROOT / "training" / "colab_train_yolo_seg.ipynb", stage_dir / "training" / "colab_train_yolo_seg.ipynb")

    zip_path = out_dir / args.zip_name
    make_zip(stage_dir, zip_path)
    return {
        "ok": True,
        "zip": str(zip_path),
        "stage": str(stage_dir),
        "dataset": str(stage_dir / "dataset"),
        "audit": audit,
    }


def main():
    parser = argparse.ArgumentParser(description="Package a Corpus YOLO-seg dataset as a Colab-ready ZIP bundle.")
    parser.add_argument("--synthetic-smoke", action="store_true", help="Generate and package a synthetic smoke dataset.")
    parser.add_argument("--synthetic-count", type=int, default=30)
    parser.add_argument("--synthetic-seed", type=int, default=7)
    parser.add_argument("--synthetic-size", type=int, default=768)
    parser.add_argument("--synthetic-min-particles", type=int, default=4)
    parser.add_argument("--synthetic-max-particles", type=int, default=10)
    parser.add_argument("--synthetic-nm-per-px", type=float, default=0.25)
    parser.add_argument("--coco", default="", help="COCO instance segmentation JSON to convert and package.")
    parser.add_argument("--yolo-dir", default="", help="Existing YOLO-seg dataset folder to package.")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--zip-name", default=DEFAULT_ZIP_NAME)
    parser.add_argument("--clean", action="store_true", help="Remove output folder before packaging.")
    parser.add_argument("--allow-failed-audit", action="store_true")
    parser.add_argument("--min-images", type=int, default=1)
    parser.add_argument("--min-au-core", type=int, default=1)
    parser.add_argument("--min-sio2-outer", type=int, default=1)
    parser.add_argument("--require-test", action="store_true")
    args = parser.parse_args()
    print(package_bundle(args))


if __name__ == "__main__":
    main()
