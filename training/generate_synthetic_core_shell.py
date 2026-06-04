import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

from common_training import COCO_CATEGORIES, SYNTHETIC_DIR, write_json


def ellipse_polygon(cx, cy, ax, ay, angle_deg, points=48):
    theta = np.linspace(0, 2 * math.pi, points, endpoint=False)
    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    coords = []
    for value in theta:
        x = ax * math.cos(value)
        y = ay * math.sin(value)
        coords.extend([float(cx + x * cos_a - y * sin_a), float(cy + x * sin_a + y * cos_a)])
    return coords


def draw_core_shell(image, core_mask, outer_mask, rng, nm_per_px, overlap):
    height, width = image.shape
    core_d_nm = rng.uniform(8, 35)
    shell_nm = rng.uniform(2, 18)
    core_r = max(3, int((core_d_nm / 2) / nm_per_px))
    outer_r = max(core_r + 2, int(((core_d_nm / 2) + shell_nm) / nm_per_px))

    for _ in range(100):
        cx = int(rng.integers(outer_r + 3, width - outer_r - 3))
        cy = int(rng.integers(outer_r + 3, height - outer_r - 3))
        if overlap or rng.random() > 0.35:
            break

    angle = float(rng.uniform(0, 180))
    core_ax = max(2, int(core_r * rng.uniform(0.9, 1.1)))
    core_ay = max(2, int(core_r * rng.uniform(0.9, 1.1)))
    outer_ax = max(core_ax + 2, int(outer_r * rng.uniform(0.92, 1.08)))
    outer_ay = max(core_ay + 2, int(outer_r * rng.uniform(0.92, 1.08)))

    local_outer = np.zeros_like(image, dtype=np.uint8)
    local_core = np.zeros_like(image, dtype=np.uint8)
    cv2.ellipse(local_outer, (cx, cy), (outer_ax, outer_ay), angle, 0, 360, 255, -1)
    cv2.ellipse(local_core, (cx, cy), (core_ax, core_ay), angle, 0, 360, 255, -1)

    ring = (local_outer > 0) & (local_core == 0)
    core = local_core > 0
    image[ring] -= rng.uniform(18, 42)
    image[core] -= rng.uniform(75, 135)
    outer_mask[local_outer > 0] = 255
    core_mask[local_core > 0] = 255

    return {
        "core": ellipse_polygon(cx, cy, core_ax, core_ay, angle),
        "outer": ellipse_polygon(cx, cy, outer_ax, outer_ay, angle),
    }


def generate_image(index, output_dir, rng, size, particles, nm_per_px):
    height, width = size
    image = np.full((height, width), 235, dtype=np.float32)
    core_mask = np.zeros((height, width), dtype=np.uint8)
    outer_mask = np.zeros((height, width), dtype=np.uint8)
    annotations = []

    for particle_index in range(particles):
        polys = draw_core_shell(
            image,
            core_mask,
            outer_mask,
            rng,
            nm_per_px,
            overlap=rng.random() < 0.25,
        )
        annotations.append((0, polys["core"]))
        annotations.append((1, polys["outer"]))

    yy, xx = np.mgrid[0:height, 0:width]
    image += 7 * ((xx - width / 2) / width) + 5 * ((yy - height / 2) / height)
    image = cv2.GaussianBlur(image, (0, 0), sigmaX=1.2)
    image += rng.normal(0, 8, size=image.shape)
    image = np.clip(image, 0, 255).astype(np.uint8)

    image_name = f"synthetic_core_shell_{index:04d}.png"
    image_path = output_dir / "images" / image_name
    image_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(image_path), image)
    return {
        "image": {
            "id": index,
            "file_name": str(image_path),
            "width": width,
            "height": height,
            "source_id": f"synthetic_group_{(index - 1) % 6}",
            "dataset_layer": "synthetic_core_shell",
            "nm_per_px": nm_per_px,
            "metadata": {
                "source_id": f"synthetic_group_{(index - 1) % 6}",
                "dataset_layer": "synthetic_core_shell",
                "nm_per_px": nm_per_px,
                "license": "CC0-1.0",
                "license_status": "accepted",
            },
        },
        "annotations": annotations,
    }


def generate_dataset(output_dir, count, seed, height, width, min_particles, max_particles, nm_per_px):
    output_dir = Path(output_dir)
    rng = np.random.default_rng(seed)
    coco = {"images": [], "annotations": [], "categories": COCO_CATEGORIES}
    annotation_id = 1
    for index in range(1, count + 1):
        particles = int(rng.integers(min_particles, max_particles + 1))
        item = generate_image(index, output_dir, rng, (height, width), particles, nm_per_px)
        coco["images"].append(item["image"])
        for class_id, polygon in item["annotations"]:
            coco["annotations"].append(
                {
                    "id": annotation_id,
                    "image_id": index,
                    "category_id": class_id,
                    "segmentation": [polygon],
                    "iscrowd": 0,
                    "area": 0,
                    "bbox": [],
                    "attributes": {"review_status": "ready"},
                }
            )
            annotation_id += 1

    coco_path = output_dir / "synthetic_core_shell_coco.json"
    write_json(coco_path, coco)
    return {"ok": True, "output": str(output_dir), "coco": str(coco_path), "images": count}


def main():
    parser = argparse.ArgumentParser(description="Generate a simple synthetic Au@SiO2 core-shell COCO dataset.")
    parser.add_argument("--out", default=str(SYNTHETIC_DIR))
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--min-particles", type=int, default=8)
    parser.add_argument("--max-particles", type=int, default=24)
    parser.add_argument("--nm-per-px", type=float, default=0.25)
    args = parser.parse_args()
    print(
        generate_dataset(
            args.out,
            args.count,
            args.seed,
            args.height,
            args.width,
            args.min_particles,
            args.max_particles,
            args.nm_per_px,
        )
    )


if __name__ == "__main__":
    main()
