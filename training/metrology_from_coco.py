import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

from common_training import CLASS_NAMES, DEFAULT_IMPORTED_COCO, category_mapping, load_json


def polygon_area(points):
    pairs = list(zip(points[0::2], points[1::2]))
    if len(pairs) < 3:
        return 0.0
    total = 0.0
    for index, (x1, y1) in enumerate(pairs):
        x2, y2 = pairs[(index + 1) % len(pairs)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def polygon_centroid(points):
    pairs = list(zip(points[0::2], points[1::2]))
    if not pairs:
        return 0.0, 0.0
    return sum(x for x, _ in pairs) / len(pairs), sum(y for _, y in pairs) / len(pairs)


def equivalent_diameter(area_px, nm_per_px):
    if area_px <= 0 or nm_per_px <= 0:
        return 0.0
    return 2.0 * math.sqrt((area_px * nm_per_px * nm_per_px) / math.pi)


def first_polygon(segmentation):
    if isinstance(segmentation, list) and segmentation and isinstance(segmentation[0], list):
        return segmentation[0]
    return None


def build_rows(coco):
    category_map, unknown = category_mapping(coco.get("categories", []))
    if unknown:
        raise SystemExit(f"Unsupported category names: {unknown}. Expected {CLASS_NAMES}.")

    images = {image["id"]: image for image in coco.get("images", [])}
    by_image = defaultdict(lambda: {"Au_core": [], "SiO2_outer": []})
    for annotation in coco.get("annotations", []):
        image = images.get(annotation.get("image_id"))
        if not image:
            continue
        polygon = first_polygon(annotation.get("segmentation"))
        if not polygon:
            continue
        category_id = annotation.get("category_id")
        if category_id not in category_map:
            continue
        class_name = CLASS_NAMES[category_map[category_id]]
        nm_per_px = float(image.get("nm_per_px") or image.get("metadata", {}).get("nm_per_px") or 0)
        area_px = polygon_area(polygon)
        cx, cy = polygon_centroid(polygon)
        by_image[image["id"]][class_name].append(
            {
                "class": class_name,
                "cx": cx,
                "cy": cy,
                "area_px": area_px,
                "diameter_nm": equivalent_diameter(area_px, nm_per_px),
                "nm_per_px": nm_per_px,
            }
        )

    rows = []
    for image_id, groups in by_image.items():
        image = images[image_id]
        cores = groups["Au_core"]
        outers = groups["SiO2_outer"]
        used_cores = set()
        for outer_index, outer in enumerate(outers, start=1):
            best_index = None
            best_distance = None
            for core_index, core in enumerate(cores):
                if core_index in used_cores:
                    continue
                distance = math.hypot(core["cx"] - outer["cx"], core["cy"] - outer["cy"])
                if best_distance is None or distance < best_distance:
                    best_index = core_index
                    best_distance = distance
            core = cores[best_index] if best_index is not None else None
            if best_index is not None:
                used_cores.add(best_index)
            d_core = core["diameter_nm"] if core else 0.0
            d_total = outer["diameter_nm"]
            rows.append(
                {
                    "image_id": image_id,
                    "file_name": image.get("file_name", ""),
                    "object_id": f"{image_id}_{outer_index:04d}",
                    "D_core_nm": d_core,
                    "D_total_nm": d_total,
                    "t_shell_nm": max(0.0, (d_total - d_core) / 2.0) if d_core else "",
                    "pair_status": "paired" if core else "missing_core",
                    "center_distance_px": best_distance if best_distance is not None else "",
                    "nm_per_px": outer["nm_per_px"],
                }
            )
    return rows


def write_csv(path, rows):
    fields = [
        "image_id",
        "file_name",
        "object_id",
        "D_core_nm",
        "D_total_nm",
        "t_shell_nm",
        "pair_status",
        "center_distance_px",
        "nm_per_px",
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Calculate Au@SiO2 metrology rows from a COCO instance-segmentation file.")
    parser.add_argument("--coco", default=str(DEFAULT_IMPORTED_COCO))
    parser.add_argument("--out", default="data/training/metrology_from_coco.csv")
    args = parser.parse_args()
    rows = build_rows(load_json(args.coco))
    write_csv(args.out, rows)
    print({"ok": True, "rows": len(rows), "output": args.out})


if __name__ == "__main__":
    main()
