import argparse
from collections import defaultdict
from pathlib import Path

from common_training import (
    CLASS_NAMES,
    DATA_DIR,
    DEFAULT_IMPORTED_COCO,
    DEFAULT_YOLO_DIR,
    ROOT,
    category_mapping,
    copy_image,
    load_json,
    normalize_polygon,
    read_csv,
    resolve_image_path,
    safe_stem,
    stable_hash,
    write_manifest,
)


def split_for_group(group, ranked_groups):
    if len(ranked_groups) == 1:
        return "train"
    if len(ranked_groups) == 2:
        return "train" if group == ranked_groups[0] else "val"
    index = ranked_groups.index(group)
    train_cut = max(1, int(round(len(ranked_groups) * 0.7)))
    val_cut = max(train_cut + 1, int(round(len(ranked_groups) * 0.85)))
    if index < train_cut:
        return "train"
    if index < val_cut:
        return "val"
    return "test"


def corpus_image_index():
    rows = read_csv(DATA_DIR / "images.csv")
    by_name = {}
    by_id = {}
    for row in rows:
        file_path = row.get("file_path", "")
        if file_path:
            by_name[Path(file_path).name] = row
        if row.get("image_id"):
            by_id[row["image_id"]] = row
    return by_name, by_id


def annotations_by_image(coco, category_map):
    grouped = defaultdict(list)
    warnings = []
    for annotation in coco.get("annotations", []):
        image_id = annotation.get("image_id")
        category_id = annotation.get("category_id")
        if category_id not in category_map:
            warnings.append(f"Annotation {annotation.get('id')} uses unknown category {category_id}.")
            continue
        segmentation = annotation.get("segmentation") or []
        if not isinstance(segmentation, list):
            warnings.append(f"Annotation {annotation.get('id')} uses RLE segmentation; skipped.")
            continue
        grouped[image_id].append((category_map[category_id], segmentation))
    return grouped, warnings


def prepare_yolo(coco_path, output_dir):
    coco = load_json(coco_path)
    category_map, unknown = category_mapping(coco.get("categories", []))
    if unknown:
        raise SystemExit(f"Unsupported category names: {unknown}.")

    output_dir = Path(output_dir)
    by_name, by_id = corpus_image_index()
    annotations, warnings = annotations_by_image(coco, category_map)

    image_infos = []
    groups = set()
    for image in coco.get("images", []):
        image_id = image.get("id")
        file_name = image.get("file_name", "")
        source_path = resolve_image_path(file_name, coco_path)
        if not source_path:
            warnings.append(f"Missing image file: {file_name}")
            continue
        corpus_row = by_id.get(str(image.get("image_id", ""))) or by_name.get(Path(file_name).name, {})
        group = corpus_row.get("source_id") or image.get("source_id") or image.get("metadata", {}).get("source_id") or Path(file_name).stem
        split = corpus_row.get("split") or image.get("split") or image.get("metadata", {}).get("split") or ""
        image_infos.append((image, source_path, corpus_row, group, split))
        groups.add(group)

    ranked_groups = sorted(groups, key=stable_hash)
    manifest = []
    exported_images = 0
    exported_labels = 0
    skipped_without_labels = 0

    for image, source_path, corpus_row, group, split in image_infos:
        split = split if split in {"train", "val", "test"} else split_for_group(group, ranked_groups)
        width = int(image.get("width") or corpus_row.get("width") or 0)
        height = int(image.get("height") or corpus_row.get("height") or 0)
        label_lines = []
        for class_id, polygons in annotations.get(image.get("id"), []):
            for polygon in polygons:
                normalized = normalize_polygon(polygon, width, height)
                if not normalized:
                    warnings.append(f"Invalid polygon in image {image.get('id')}; skipped.")
                    continue
                label_lines.append(" ".join([str(class_id)] + [f"{value:.6f}" for value in normalized]))

        if not label_lines:
            skipped_without_labels += 1
            continue

        stem = f"{image.get('id')}_{safe_stem(Path(source_path).stem)}"
        image_target = output_dir / "images" / split / f"{stem}{source_path.suffix.lower()}"
        label_target = output_dir / "labels" / split / f"{stem}.txt"
        copy_image(source_path, image_target)
        label_target.parent.mkdir(parents=True, exist_ok=True)
        label_target.write_text("\n".join(label_lines), encoding="utf-8")
        exported_images += 1
        exported_labels += len(label_lines)
        manifest.append(
            {
                "image_id": image.get("id"),
                "source_id": group,
                "split": split,
                "image_path": str(image_target),
                "label_path": str(label_target),
                "labels": len(label_lines),
            }
        )

    data_yaml = output_dir / "data.yaml"
    data_yaml.write_text(
        f"path: {output_dir.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n"
        "  0: Au_core\n"
        "  1: SiO2_outer\n",
        encoding="utf-8",
    )
    write_manifest(output_dir / "manifest.csv", manifest)
    (output_dir / "prepare_warnings.txt").write_text("\n".join(warnings), encoding="utf-8")
    return {
        "output": str(output_dir),
        "data_yaml": str(data_yaml),
        "images": exported_images,
        "labels": exported_labels,
        "skipped_without_labels": skipped_without_labels,
        "warnings": len(warnings),
    }


def main():
    parser = argparse.ArgumentParser(description="Prepare an Ultralytics YOLO instance-segmentation dataset.")
    parser.add_argument("--coco", default=str(DEFAULT_IMPORTED_COCO))
    parser.add_argument("--out", default=str(DEFAULT_YOLO_DIR))
    args = parser.parse_args()

    print(prepare_yolo(args.coco, args.out))


if __name__ == "__main__":
    main()
