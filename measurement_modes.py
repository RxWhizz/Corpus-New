import argparse
import json
import math
import os
from pathlib import Path

import cv2
import numpy as np


OUTPUT_IMAGE = "processed_image.jpg"
DIAMETERS_TXT = "diameters.txt"
MEASUREMENTS_JSON = "measurements.json"
AU_CLASS = "Au_decorations"
SIO2_CLASS = "SiO2_carrier"
INNER_COLOR = (0, 0, 255)
OUTER_COLOR = (255, 180, 0)
REVIEW_COLOR = (0, 220, 255)


def fail(message):
    print(json.dumps({"ok": False, "message": message}))
    raise SystemExit(1)


def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in ("0", "false", "no", "off")


def parse_args():
    parser = argparse.ArgumentParser(description="Measure Au/SiO2 particles without AI.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--mode", choices=["au", "sio2", "both"], default="au")
    parser.add_argument("--shape-preset", choices=["generic", "spheres", "pellets"], default="generic")
    parser.add_argument("--scale", required=True, type=float)
    parser.add_argument("--manual-scale-px", type=float, default=0)
    parser.add_argument("--manual-scale-line", default="")
    parser.add_argument("--exclude-edges", default="true")
    parser.add_argument("--watershed", default="auto")
    parser.add_argument("--watershed-min-distance-factor", type=float, default=0.55)
    parser.add_argument("--au-min-radius", type=float, default=1)
    parser.add_argument("--au-max-radius", type=float, default=50)
    parser.add_argument("--sio2-min-radius", type=float, default=20)
    parser.add_argument("--sio2-max-radius", type=float, default=500)
    parser.add_argument("--histogram-bin-width", type=float, default=5)
    return parser.parse_args()


def parse_manual_scale_line(value):
    if not value:
        return None
    try:
        coords = [float(part.strip()) for part in value.split(",")]
    except ValueError:
        fail("--manual-scale-line must be x1,y1,x2,y2")
    if len(coords) != 4:
        fail("--manual-scale-line must be x1,y1,x2,y2")
    x1, y1, x2, y2 = coords
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 0:
        fail("--manual-scale-line points must not be identical")
    return {
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "length": length
    }


def resolve_watershed(value, shape_preset):
    if str(value).strip().lower() == "auto":
        return shape_preset != "pellets"
    return parse_bool(value)


def read_image(image_path):
    image = cv2.imread(str(image_path))
    if image is not None:
        return image

    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        pil_image = Image.open(image_path).convert("RGB")
    except Exception:
        return None

    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def overlap_ratio(first, second):
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    return (ix * iy) / max(1, aw * ah)


def touches_edge(bbox, image_shape, margin=2):
    x, y, w, h = bbox
    height, width = image_shape[:2]
    return x <= margin or y <= margin or x + w >= width - margin or y + h >= height - margin


def collect_scale_candidates(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    min_bar_width = max(20, int(width * 0.08))
    image_area = height * width
    candidates = []

    _, binary = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w * h > image_area * 0.25:
            continue
        if y >= height - 10:
            continue
        if w >= min_bar_width and 1 <= h <= 35 and w / max(h, 1) > 6:
            confidence = scale_confidence(x, y, w, h, width, height)
            candidates.append({
                "x": x,
                "y": y,
                "width_px": float(w),
                "height_px": float(h),
                "method": "bright_contour",
                "confidence": confidence
            })

    x0 = int(width * 0.35)
    y0 = int(height * 0.55)
    roi = gray[y0:height, x0:width]
    edges = cv2.Canny(roi, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        1,
        math.pi / 180,
        threshold=15,
        minLineLength=min_bar_width,
        maxLineGap=4
    )
    if lines is not None:
        for line in lines[:, 0, :]:
            x1, y1, x2, y2 = [int(value) for value in line]
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)
            absolute_y = y0 + min(y1, y2)
            absolute_x = x0 + min(x1, x2)
            if abs(dy) <= 3 and length >= min_bar_width and absolute_y < height - 10:
                confidence = scale_confidence(absolute_x, absolute_y, length, max(1, abs(dy) + 1), width, height)
                candidates.append({
                    "x": int(absolute_x),
                    "y": int(absolute_y),
                    "width_px": float(length),
                    "height_px": float(max(1, abs(dy) + 1)),
                    "method": "hough_line",
                    "confidence": confidence
                })

    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    deduped = []
    for candidate in candidates:
        bbox = (candidate["x"], candidate["y"], int(candidate["width_px"]), max(1, int(candidate["height_px"])))
        if any(overlap_ratio(bbox, (row["x"], row["y"], int(row["width_px"]), max(1, int(row["height_px"])))) > 0.5 for row in deduped):
            continue
        deduped.append(candidate)
    return deduped


def scale_confidence(x, y, w, h, image_width, image_height):
    length_score = min(1.0, w / max(image_width * 0.18, 1))
    bottom_score = min(1.0, max(0.0, y / max(image_height * 0.85, 1)))
    right_score = min(1.0, max(0.0, x / max(image_width * 0.65, 1)))
    thin_score = min(1.0, (w / max(h, 1)) / 12)
    edge_penalty = 0.45 if y >= image_height - 10 else 0
    return round(max(0.0, 0.45 * length_score + 0.25 * bottom_score + 0.2 * right_score + 0.1 * thin_score - edge_penalty), 4)


def resolve_scale(image, scale_length, manual_scale_px, manual_scale_line=None):
    candidates = collect_scale_candidates(image)
    if manual_scale_line:
        padding = 8
        min_x = int(math.floor(min(manual_scale_line["x1"], manual_scale_line["x2"]))) - padding
        min_y = int(math.floor(min(manual_scale_line["y1"], manual_scale_line["y2"]))) - padding
        max_x = int(math.ceil(max(manual_scale_line["x1"], manual_scale_line["x2"]))) + padding
        max_y = int(math.ceil(max(manual_scale_line["y1"], manual_scale_line["y2"]))) + padding
        height, width = image.shape[:2]
        x = max(0, min_x)
        y = max(0, min_y)
        w = max(1, min(width, max_x) - x)
        h = max(1, min(height, max_y) - y)
        selected = {
            "x": x,
            "y": y,
            "width_px": float(manual_scale_line["length"]),
            "height_px": float(max(1, h)),
            "method": "manual_line",
            "confidence": 1.0,
            "line": {
                "x1": float(manual_scale_line["x1"]),
                "y1": float(manual_scale_line["y1"]),
                "x2": float(manual_scale_line["x2"]),
                "y2": float(manual_scale_line["y2"])
            }
        }
        ignored_regions = [(x, y, w, h)]
    elif manual_scale_px and manual_scale_px > 0:
        selected = {
            "x": "",
            "y": "",
            "width_px": float(manual_scale_px),
            "height_px": "",
            "method": "manual_override",
            "confidence": 1.0
        }
        ignored_regions = []
    elif candidates:
        selected = candidates[0]
        ignored_regions = [(
            int(selected["x"]),
            int(selected["y"]),
            int(round(selected["width_px"])),
            max(1, int(round(float(selected["height_px"]))))
        )]
    else:
        fail("Could not detect a white scale bar. Enter Manual Scale px or use an image with a visible scale bar.")

    nm_per_px = scale_length / float(selected["width_px"])
    return nm_per_px, selected, candidates, ignored_regions


def watershed_split_contours(binary, min_radius_px, max_radius_px, distance_factor=0.55):
    foreground = np.uint8(binary > 0) * 255
    if not np.any(foreground):
        return []

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    foreground = cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2)
    original_contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not original_contours:
        return []

    distance = cv2.distanceTransform(foreground, cv2.DIST_L2, 5)
    if distance.max() <= 0:
        return original_contours

    marker_labels = None
    marker_count = 0
    for factor in (distance_factor, distance_factor * 0.85, distance_factor * 0.70):
        threshold = max(2.0, float(distance.max()) * max(0.20, factor))
        sure_foreground = np.uint8(distance >= threshold) * 255
        marker_count, marker_labels = cv2.connectedComponents(sure_foreground)
        if marker_count >= 2:
            break

    if marker_labels is None or marker_count <= 1:
        return original_contours

    sure_background = cv2.dilate(foreground, kernel, iterations=2)
    unknown = cv2.subtract(sure_background, np.uint8(marker_labels > 0) * 255)
    markers = marker_labels + 1
    markers[unknown == 255] = 0

    watershed_image = cv2.cvtColor(foreground, cv2.COLOR_GRAY2BGR)
    cv2.watershed(watershed_image, markers)

    split_contours = []
    for marker_id in range(2, marker_count + 1):
        region = np.uint8(markers == marker_id) * 255
        region = cv2.morphologyEx(region, cv2.MORPH_OPEN, kernel, iterations=1)
        contours, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            split_contours.append(max(contours, key=cv2.contourArea))

    return split_contours or original_contours


def contour_measurements(contours, class_name, min_radius_px, max_radius_px, nm_per_px, color, overlay, ignored_regions, exclude_edges, measurement_flags=None, separation_method="contour"):
    measurements = []
    min_area = math.pi * min_radius_px**2
    max_area = math.pi * max_radius_px**2 * 3.0
    measurement_flags = measurement_flags or []

    for contour in contours:
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if area <= 0 or perimeter <= 0:
            continue

        bbox = cv2.boundingRect(contour)
        edge = touches_edge(bbox, overlay.shape)
        if exclude_edges and edge:
            continue
        if any(overlap_ratio(bbox, region) > 0.2 for region in ignored_regions):
            continue

        rect = cv2.minAreaRect(contour)
        (x, y), (width, height), angle = rect
        major_px = max(width, height)
        minor_px = min(width, height)
        if major_px <= 0 or minor_px <= 0:
            continue

        circularity = 4 * math.pi * area / (perimeter * perimeter)
        aspect_ratio = major_px / minor_px
        radius_px = major_px / 2
        is_round = circularity >= 0.55 and aspect_ratio < 1.8
        is_elongated = circularity >= 0.25 and aspect_ratio >= 1.8
        if not (is_round or is_elongated):
            continue
        if not (min_radius_px <= radius_px <= max_radius_px):
            continue
        if not (min_area * 0.65 <= area <= max_area):
            continue

        flags = list(measurement_flags)
        if "watershed_split" in flags and (area < min_area * 0.55 or circularity < 0.35):
            flags.append("low_split_confidence")
        if edge:
            flags.append("edge")

        shape = "elongated" if is_elongated else "round"
        draw_detection(overlay, contour, rect, shape, color)
        measurement = flat_measurement(
            class_name=class_name,
            center_x=x,
            center_y=y,
            major_px=major_px,
            minor_px=minor_px,
            area_px=area,
            angle=angle,
            shape=shape,
            confidence=circularity,
            nm_per_px=nm_per_px,
            flags=flags,
            separation_method=separation_method
        )
        measurements.append(measurement)

    return measurements


def draw_detection(overlay, contour, rect, shape, color):
    if shape == "elongated":
        box = cv2.boxPoints(rect)
        box = np.intp(box)
        cv2.drawContours(overlay, [box], -1, color, 2)
    else:
        (x, y), radius = cv2.minEnclosingCircle(contour)
        cv2.circle(overlay, (int(x), int(y)), int(radius), color, 2)
    cv2.drawContours(overlay, [contour], -1, color, 1)


def flat_measurement(class_name, center_x, center_y, major_px, minor_px, area_px, angle, shape, confidence, nm_per_px, flags=None, separation_method="contour"):
    flags = flags or []
    major_axis = float(major_px * nm_per_px)
    minor_axis = float(minor_px * nm_per_px)
    return {
        "class": class_name,
        "diameter": major_axis,
        "major_axis": major_axis,
        "minor_axis": minor_axis,
        "equivalent_diameter": float(math.sqrt(4 * area_px / math.pi) * nm_per_px) if area_px > 0 else 0,
        "radius_px": float(major_px / 2),
        "center_x": float(center_x),
        "center_y": float(center_y),
        "area_px": float(area_px),
        "aspect_ratio": round(float(major_px / max(minor_px, 1e-6)), 4),
        "shape": shape,
        "angle": float(angle),
        "separation_method": separation_method,
        "confidence_hint": round(float(confidence), 4),
        "flags": flags
    }


def detect_au_contours(image, min_radius_px, max_radius_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled=False, watershed_factor=0.55):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)
    watershed_binary = binary.copy()
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=1)
    original_contours, _ = cv2.findContours(watershed_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    legacy_contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if watershed_enabled:
        contours = watershed_split_contours(watershed_binary, min_radius_px, max_radius_px, watershed_factor)
        if len(contours) > len(original_contours):
            return contour_measurements(
                contours,
                AU_CLASS,
                min_radius_px,
                max_radius_px,
                nm_per_px,
                INNER_COLOR,
                overlay,
                ignored_regions,
                exclude_edges,
                ["watershed_split"],
                "watershed"
            )
    return contour_measurements(legacy_contours, AU_CLASS, min_radius_px, max_radius_px, nm_per_px, INNER_COLOR, overlay, ignored_regions, exclude_edges)


def hough_circle_measurements(gray, class_name, min_radius_px, max_radius_px, nm_per_px, color, overlay, ignored_regions, exclude_edges):
    blur = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(
        blur,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(12, int(min_radius_px * 1.7)),
        param1=90,
        param2=28,
        minRadius=max(1, int(round(min_radius_px))),
        maxRadius=max(2, int(round(max_radius_px)))
    )
    measurements = []
    if circles is None:
        return measurements

    image_area = gray.shape[0] * gray.shape[1]
    max_circle_area = image_area * 0.25

    for circle in np.round(circles[0]).astype(int):
        x, y, radius = [int(value) for value in circle]
        if math.pi * radius * radius > max_circle_area:
            continue
        bbox = (x - radius, y - radius, radius * 2, radius * 2)
        edge = touches_edge(bbox, overlay.shape)
        if exclude_edges and edge:
            continue
        if any(overlap_ratio(bbox, region) > 0.2 for region in ignored_regions):
            continue
        measurement = flat_measurement(
            class_name=class_name,
            center_x=x,
            center_y=y,
            major_px=2 * radius,
            minor_px=2 * radius,
            area_px=math.pi * radius * radius,
            angle=0,
            shape="round",
            confidence=0.75,
            nm_per_px=nm_per_px,
            flags=["edge"] if edge else [],
            separation_method="hough"
        )
        if is_duplicate(measurement, measurements):
            continue
        cv2.circle(overlay, (x, y), radius, color, 2)
        measurements.append(measurement)
    return measurements


def is_duplicate(measurement, measurements, factor=0.65):
    for existing in measurements:
        dx = measurement["center_x"] - existing["center_x"]
        dy = measurement["center_y"] - existing["center_y"]
        distance = math.sqrt(dx * dx + dy * dy)
        radius = max(measurement["radius_px"], existing["radius_px"], 1)
        if distance < radius * factor:
            return True
    return False


def nearest_measurement(center, candidates, max_distance):
    best = None
    best_distance = None
    for candidate in candidates:
        dx = center[0] - candidate["center_x"]
        dy = center[1] - candidate["center_y"]
        distance = math.sqrt(dx * dx + dy * dy)
        if distance <= max_distance and (best_distance is None or distance < best_distance):
            best = candidate
            best_distance = distance
    return best, best_distance


def object_row(index, preset, inner=None, outer=None, extra_flags=None):
    flags = list(extra_flags or [])
    for measurement in (inner, outer):
        if measurement:
            flags.extend(measurement.get("flags", []))
    if not inner:
        flags.append("unpaired_inner")
    if not outer:
        flags.append("unpaired_outer")

    inner_major = inner.get("major_axis", 0) if inner else 0
    outer_major = outer.get("major_axis", 0) if outer else 0
    inner_minor = inner.get("minor_axis", 0) if inner else 0
    outer_minor = outer.get("minor_axis", 0) if outer else 0
    shell = (outer_major - inner_major) / 2 if inner and outer and outer_major >= inner_major else 0
    ratio = inner_major / outer_major if inner and outer and outer_major else 0
    center_x = (outer or inner or {}).get("center_x", 0)
    center_y = (outer or inner or {}).get("center_y", 0)

    if inner and outer and (ratio < 0.25 or ratio > 0.85):
        flags.append("ratio_outlier")
    confidence = 1.0
    if "unpaired_inner" in flags or "unpaired_outer" in flags:
        confidence -= 0.3
    if "edge" in flags:
        confidence -= 0.2
    if "ratio_outlier" in flags:
        confidence -= 0.2
    if "low_split_confidence" in flags:
        confidence -= 0.2
    confidence = max(0.0, round(confidence, 3))
    if confidence < 0.7 and "low_confidence" not in flags:
        flags.append("low_confidence")
    review_flags = set(flags) - {"watershed_split"}

    return {
        "object_id": f"obj_{index:04d}",
        "preset": preset,
        "class": "core_shell_object",
        "center_x": center_x,
        "center_y": center_y,
        "inner_major_axis": inner_major,
        "inner_minor_axis": inner_minor,
        "outer_major_axis": outer_major,
        "outer_minor_axis": outer_minor,
        "equivalent_diameter": outer.get("equivalent_diameter", 0) if outer else inner.get("equivalent_diameter", 0) if inner else 0,
        "shell_thickness_estimate": shell,
        "inner_outer_ratio": ratio,
        "pair_status": "paired" if inner and outer else "partial",
        "review_status": "ready" if confidence >= 0.7 and not review_flags else "needs_review",
        "confidence_score": confidence,
        "separation_method": "watershed" if "watershed_split" in flags else "contour/hough",
        "flags": sorted(set(flags)),
        "inner": inner,
        "outer": outer
    }


def sio2_mask(image):
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 35, 3)
    return cv2.morphologyEx(adaptive, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)


def detect_sio2_watershed(image, min_radius_px, max_radius_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_factor=0.55):
    binary = sio2_mask(image)
    original_contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = watershed_split_contours(binary, min_radius_px, max_radius_px, watershed_factor)
    if len(contours) <= len(original_contours):
        return []
    return contour_measurements(
        contours,
        SIO2_CLASS,
        min_radius_px,
        max_radius_px,
        nm_per_px,
        OUTER_COLOR,
        overlay,
        ignored_regions,
        exclude_edges,
        ["watershed_split"],
        "watershed"
    )


def run_spheres(image, mode, au_min_px, au_max_px, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled=False, watershed_factor=0.55):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    inner = detect_au_contours(image, au_min_px, au_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, watershed_factor) if mode in ("au", "both") else []
    outer = hough_circle_measurements(gray, SIO2_CLASS, sio2_min_px, sio2_max_px, nm_per_px, OUTER_COLOR, overlay, ignored_regions, exclude_edges) if mode in ("sio2", "both") else []
    if watershed_enabled and mode in ("sio2", "both"):
        for row in detect_sio2_watershed(image, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_factor):
            if not is_duplicate(row, outer):
                outer.append(row)

    objects = []
    used_inner = set()
    index = 1
    for outer_measurement in outer:
        match, _ = nearest_measurement(
            (outer_measurement["center_x"], outer_measurement["center_y"]),
            [row for row in inner if id(row) not in used_inner],
            max(outer_measurement["radius_px"] * 0.8, 8)
        )
        if match:
            used_inner.add(id(match))
        objects.append(object_row(index, "spheres", match, outer_measurement))
        index += 1

    if mode == "au":
        for row in inner:
            objects.append(object_row(index, "spheres", row, None))
            index += 1
    elif mode == "both":
        for row in inner:
            if id(row) not in used_inner:
                objects.append(object_row(index, "spheres", row, None))
                index += 1

    return objects, inner + outer


def anchored_pellet_outer(gray, anchors, min_radius_px, max_radius_px, nm_per_px, overlay, ignored_regions, exclude_edges):
    measurements = []
    window_radius = max(12, int(round(max_radius_px * 0.86)))
    for anchor in anchors:
        center_x = int(round(anchor["center_x"]))
        center_y = int(round(anchor["center_y"]))
        x1 = max(0, center_x - window_radius)
        y1 = max(0, center_y - window_radius)
        x2 = min(gray.shape[1], center_x + window_radius)
        y2 = min(gray.shape[0], center_y + window_radius)
        patch = gray[y1:y2, x1:x2]
        if patch.size == 0:
            continue

        _, binary = cv2.threshold(patch, 175, 255, cv2.THRESH_BINARY_INV)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        label_count, labels, _, _ = cv2.connectedComponentsWithStats(binary)
        local_x = center_x - x1
        local_y = center_y - y1
        if not (0 <= local_x < labels.shape[1] and 0 <= local_y < labels.shape[0]):
            continue
        label = labels[local_y, local_x]
        if label == 0 or label_count <= label:
            continue

        mask = np.uint8(labels == label) * 255
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        if area <= 0:
            continue

        rect = cv2.minAreaRect(contour)
        (local_cx, local_cy), (width, height), angle = rect
        major_px = max(width, height)
        minor_px = min(width, height)
        if minor_px <= 0:
            continue
        radius_px = major_px / 2
        if not (min_radius_px <= radius_px <= max_radius_px * 1.15):
            continue

        global_cx = local_cx + x1
        global_cy = local_cy + y1
        bbox = (int(global_cx - major_px / 2), int(global_cy - major_px / 2), int(major_px), int(major_px))
        edge = touches_edge(bbox, gray.shape)
        if exclude_edges and edge:
            continue
        if any(overlap_ratio(bbox, region) > 0.2 for region in ignored_regions):
            continue

        box = cv2.boxPoints(rect)
        box[:, 0] += x1
        box[:, 1] += y1
        box = np.intp(box)
        cv2.drawContours(overlay, [box], -1, OUTER_COLOR, 2)
        measurements.append(flat_measurement(
            class_name=SIO2_CLASS,
            center_x=global_cx,
            center_y=global_cy,
            major_px=major_px,
            minor_px=minor_px,
            area_px=area,
            angle=angle,
            shape="elongated",
            confidence=0.7,
            nm_per_px=nm_per_px,
            flags=["edge"] if edge else []
        ))

    return measurements


def run_pellets(image, mode, au_min_px, au_max_px, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled=False, watershed_factor=0.55):
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    inner = detect_au_contours(image, au_min_px, au_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, watershed_factor) if mode in ("au", "both") else []
    anchors = [row for row in inner if row.get("aspect_ratio", 1) >= 1.45] or inner
    outer = anchored_pellet_outer(gray, anchors, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges) if mode in ("sio2", "both") else []

    objects = []
    used_outer = set()
    index = 1
    for inner_measurement in inner:
        match, _ = nearest_measurement(
            (inner_measurement["center_x"], inner_measurement["center_y"]),
            [row for row in outer if id(row) not in used_outer],
            max(inner_measurement["radius_px"] * 1.4, 12)
        )
        if match:
            used_outer.add(id(match))
        objects.append(object_row(index, "pellets", inner_measurement, match))
        index += 1

    if mode == "sio2":
        for row in outer:
            objects.append(object_row(index, "pellets", None, row))
            index += 1
    elif mode == "both":
        for row in outer:
            if id(row) not in used_outer:
                objects.append(object_row(index, "pellets", None, row))
                index += 1

    return objects, inner + outer


def detect_sio2_generic(image, min_radius_px, max_radius_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled=False, watershed_factor=0.55):
    gray = cv2.GaussianBlur(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    closed = sio2_mask(image)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if watershed_enabled:
        split_contours = watershed_split_contours(closed, min_radius_px, max_radius_px, watershed_factor)
        if len(split_contours) > len(contours):
            measurements = contour_measurements(split_contours, SIO2_CLASS, min_radius_px, max_radius_px, nm_per_px, OUTER_COLOR, overlay, ignored_regions, exclude_edges, ["watershed_split"], "watershed")
        else:
            measurements = contour_measurements(contours, SIO2_CLASS, min_radius_px, max_radius_px, nm_per_px, OUTER_COLOR, overlay, ignored_regions, exclude_edges)
    else:
        measurements = contour_measurements(contours, SIO2_CLASS, min_radius_px, max_radius_px, nm_per_px, OUTER_COLOR, overlay, ignored_regions, exclude_edges)

    for row in hough_circle_measurements(gray, SIO2_CLASS, min_radius_px, max_radius_px, nm_per_px, OUTER_COLOR, overlay, ignored_regions, exclude_edges):
        if not is_duplicate(row, measurements):
            measurements.append(row)
    return measurements


def run_generic(image, mode, au_min_px, au_max_px, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled=False, watershed_factor=0.55):
    inner = detect_au_contours(image, au_min_px, au_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, watershed_factor) if mode in ("au", "both") else []
    outer = detect_sio2_generic(image, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, watershed_factor) if mode in ("sio2", "both") else []
    objects = []
    index = 1
    for row in inner:
        objects.append(object_row(index, "generic", row, None))
        index += 1
    for row in outer:
        objects.append(object_row(index, "generic", None, row))
        index += 1
    return objects, inner + outer


def summarize_class_measurements(class_measurements):
    summary = {}
    for class_name in sorted({row["class"] for row in class_measurements}):
        values = [row["diameter"] for row in class_measurements if row["class"] == class_name]
        summary[class_name] = {
            "count": len(values),
            "mean_diameter": sum(values) / len(values) if values else 0,
            "min_diameter": min(values) if values else 0,
            "max_diameter": max(values) if values else 0
        }
    return summary


def summarize_objects(objects):
    paired = [row for row in objects if row["pair_status"] == "paired"]
    ready = [row for row in objects if row["review_status"] == "ready"]
    watershed_splits = [row for row in objects if "watershed_split" in row.get("flags", [])]
    inner_values = [row["inner_major_axis"] for row in objects if row.get("inner_major_axis")]
    outer_values = [row["outer_major_axis"] for row in objects if row.get("outer_major_axis")]
    shell_values = [row["shell_thickness_estimate"] for row in objects if row.get("shell_thickness_estimate")]
    return {
        "objects": len(objects),
        "paired": len(paired),
        "ready": len(ready),
        "needs_review": len(objects) - len(ready),
        "watershed_splits": len(watershed_splits),
        "mean_inner_major_axis": sum(inner_values) / len(inner_values) if inner_values else 0,
        "mean_outer_major_axis": sum(outer_values) / len(outer_values) if outer_values else 0,
        "mean_shell_thickness": sum(shell_values) / len(shell_values) if shell_values else 0
    }


def write_compat_files(nm_per_px, class_measurements, preferred_class):
    preferred = [row for row in class_measurements if row["class"] == preferred_class]
    rows = preferred or class_measurements
    with open(DIAMETERS_TXT, "w", encoding="utf-8") as file:
        file.write(f"{nm_per_px}\n")
        for row in rows:
            file.write(f"{row['diameter']}\n")


def main():
    args = parse_args()
    image_path = Path(args.image)
    if not image_path.exists():
        fail(f"Image not found: {image_path}")

    image = read_image(image_path)
    if image is None:
        fail(f"Could not read image: {image_path}")

    exclude_edges = parse_bool(args.exclude_edges)
    watershed_enabled = resolve_watershed(args.watershed, args.shape_preset)
    manual_scale_line = parse_manual_scale_line(args.manual_scale_line)
    nm_per_px, selected_scale, scale_candidates, ignored_regions = resolve_scale(
        image,
        args.scale,
        args.manual_scale_px,
        manual_scale_line
    )
    overlay = image.copy()

    au_min_px = args.au_min_radius / nm_per_px
    au_max_px = args.au_max_radius / nm_per_px
    sio2_min_px = args.sio2_min_radius / nm_per_px
    sio2_max_px = args.sio2_max_radius / nm_per_px

    if args.shape_preset == "spheres":
        objects, class_measurements = run_spheres(image, args.mode, au_min_px, au_max_px, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, args.watershed_min_distance_factor)
    elif args.shape_preset == "pellets":
        objects, class_measurements = run_pellets(image, args.mode, au_min_px, au_max_px, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, args.watershed_min_distance_factor)
    else:
        objects, class_measurements = run_generic(image, args.mode, au_min_px, au_max_px, sio2_min_px, sio2_max_px, nm_per_px, overlay, ignored_regions, exclude_edges, watershed_enabled, args.watershed_min_distance_factor)

    for row in objects:
        if row["review_status"] != "ready":
            x = int(row.get("center_x", 0))
            y = int(row.get("center_y", 0))
            cv2.circle(overlay, (x, y), 4, REVIEW_COLOR, -1)

    cv2.imwrite(OUTPUT_IMAGE, overlay)
    payload = {
        "ok": True,
        "mode": args.mode,
        "shape_preset": args.shape_preset,
        "exclude_edges": exclude_edges,
        "watershed": watershed_enabled,
        "separation_method": "watershed" if watershed_enabled else "contour/hough",
        "processed_image_path": os.path.abspath(OUTPUT_IMAGE),
        "measurements_path": os.path.abspath(MEASUREMENTS_JSON),
        "nm_per_px": nm_per_px,
        "scale_bar_px": selected_scale["width_px"],
        "selected_scale": selected_scale,
        "scale_candidates": scale_candidates,
        "histogram_bin_width": args.histogram_bin_width,
        "measurements": objects,
        "class_measurements": class_measurements,
        "summary": summarize_class_measurements(class_measurements),
        "object_summary": summarize_objects(objects)
    }

    preferred_class = AU_CLASS if args.mode != "sio2" else SIO2_CLASS
    write_compat_files(nm_per_px, class_measurements, preferred_class)
    with open(MEASUREMENTS_JSON, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    print(json.dumps(payload))


if __name__ == "__main__":
    main()
