import argparse
from pathlib import Path

from common_training import (
    CLASS_NAMES,
    DEFAULT_IMPORTED_COCO,
    category_mapping,
    load_json,
    write_json,
)


def import_cvat_coco(coco_path, output_path):
    coco = load_json(coco_path)
    mapping, unknown = category_mapping(coco.get("categories", []))
    if unknown:
        raise SystemExit(f"Unsupported CVAT category names: {unknown}. Expected {CLASS_NAMES}.")
    if set(mapping.values()) != {0, 1}:
        raise SystemExit(f"CVAT COCO must include both classes: {CLASS_NAMES}.")

    imported = dict(coco)
    imported["categories"] = [
        {"id": 0, "name": "Au_core", "supercategory": "nanoparticle"},
        {"id": 1, "name": "SiO2_outer", "supercategory": "nanoparticle"},
    ]

    remapped = []
    for annotation in imported.get("annotations", []):
        old_category = annotation.get("category_id")
        if old_category not in mapping:
            continue
        new_annotation = dict(annotation)
        new_annotation["category_id"] = mapping[old_category]
        remapped.append(new_annotation)
    imported["annotations"] = remapped
    imported.setdefault("corpus_import", {})
    imported["corpus_import"].update(
        {
            "source": str(Path(coco_path).resolve()),
            "format": "CVAT COCO instance segmentation",
            "classes": CLASS_NAMES,
        }
    )
    write_json(output_path, imported)
    return imported


def main():
    parser = argparse.ArgumentParser(description="Import and normalize a CVAT COCO instance-segmentation export.")
    parser.add_argument("--coco", required=True, help="Path to CVAT COCO JSON.")
    parser.add_argument("--out", default=str(DEFAULT_IMPORTED_COCO), help="Normalized COCO output path.")
    args = parser.parse_args()

    imported = import_cvat_coco(args.coco, args.out)
    print(
        {
            "ok": True,
            "output": args.out,
            "images": len(imported.get("images", [])),
            "annotations": len(imported.get("annotations", [])),
        }
    )


if __name__ == "__main__":
    main()
