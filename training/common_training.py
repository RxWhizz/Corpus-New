import csv
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
TRAINING_DIR = DATA_DIR / "training"
DEFAULT_IMPORTED_COCO = ANNOTATIONS_DIR / "cvat_coco_imported.json"
DEFAULT_YOLO_DIR = TRAINING_DIR / "yolo_seg"
DEFAULT_CVAT_DIR = TRAINING_DIR / "cvat_package"
SYNTHETIC_DIR = TRAINING_DIR / "synthetic_core_shell"
TRAINING_AUDIT_MD = ROOT / "reports" / "training_dataset_audit.md"

CLASS_NAMES = ["Au_core", "SiO2_outer"]
COCO_CATEGORIES = [
    {"id": 0, "name": "Au_core", "supercategory": "nanoparticle"},
    {"id": 1, "name": "SiO2_outer", "supercategory": "nanoparticle"},
]
CLASS_ALIASES = {
    "au_core": "Au_core",
    "au core": "Au_core",
    "core": "Au_core",
    "gold core": "Au_core",
    "gold_core": "Au_core",
    "au": "Au_core",
    "gold": "Au_core",
    "core_au": "Au_core",
    "sio2_outer": "SiO2_outer",
    "sio2 outer": "SiO2_outer",
    "sio2": "SiO2_outer",
    "silica": "SiO2_outer",
    "silica outer": "SiO2_outer",
    "silica_outer": "SiO2_outer",
    "sio2 carrier": "SiO2_outer",
    "sio2_carrier": "SiO2_outer",
    "carrier": "SiO2_outer",
    "shell": "SiO2_outer",
    "outer": "SiO2_outer",
}

PUBLIC_LICENSE_HINTS = ("cc by", "cc-by", "cc0", "public domain")
BLOCKED_LICENSE_HINTS = ("nc", "nd", "noncommercial", "no derivatives")
REVIEW_STATUSES = {"needs_review", "uncertain", "ambiguous", "ignore", "ignored", "difficult"}


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, payload):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def normalize_class_name(name):
    normalized = " ".join(str(name or "").replace("-", " ").replace("_", " ").split()).lower()
    return CLASS_ALIASES.get(normalized, name)


def category_mapping(categories):
    mapping = {}
    unknown = []
    for category in categories:
        canonical = normalize_class_name(category.get("name", ""))
        if canonical in CLASS_NAMES:
            mapping[category["id"]] = CLASS_NAMES.index(canonical)
        else:
            unknown.append(category.get("name", ""))
    return mapping, unknown


def canonical_categories():
    return [dict(category) for category in COCO_CATEGORIES]


def is_public_license(row):
    status = str(row.get("license_status", "")).strip().lower()
    license_text = " ".join(
        str(row.get(key, "")).lower()
        for key in ("license", "license_url", "rights", "usage_terms")
    )
    if status == "accepted" and not any(hint in license_text for hint in BLOCKED_LICENSE_HINTS):
        return True
    return any(hint in license_text for hint in PUBLIC_LICENSE_HINTS) and not any(
        hint in license_text for hint in BLOCKED_LICENSE_HINTS
    )


def has_confirmed_scale(row):
    status = str(row.get("scale_status", "")).strip().lower()
    nm_per_px = str(row.get("nm_per_px", "")).strip()
    return bool(nm_per_px) and status in {"confirmed", "manual_line", "manual", "metadata"}


def training_layer(row, source_row=None):
    source_row = source_row or {}
    if is_public_license(source_row) or is_public_license(row):
        return "public_demo"
    source_type = str(source_row.get("source_type", "") or row.get("source_type", "")).lower()
    notes = str(row.get("notes", "")).lower()
    if "synthetic" in source_type or "synthetic" in notes:
        return "synthetic_core_shell"
    return "private_training"


def annotation_review_status(annotation):
    attrs = annotation.get("attributes") or {}
    if isinstance(attrs, list):
        attrs = {
            str(item.get("name", "")).lower(): item.get("value", "")
            for item in attrs
            if isinstance(item, dict)
        }
    values = [
        annotation.get("review_status", ""),
        annotation.get("status", ""),
        annotation.get("quality_status", ""),
        attrs.get("review_status", ""),
        attrs.get("status", ""),
        attrs.get("quality_status", ""),
    ]
    if annotation.get("iscrowd"):
        return "needs_review"
    for value in values:
        if str(value).strip().lower() in REVIEW_STATUSES:
            return "needs_review"
    return "ready"


def resolve_image_path(file_name, coco_path=None):
    raw = Path(str(file_name))
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    if coco_path:
        candidates.append(Path(coco_path).resolve().parent / raw)
    candidates.append(ROOT / raw)
    candidates.append(DATA_DIR / raw)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def safe_stem(value):
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in str(value))
    return safe.strip("._") or "image"


def stable_hash(value):
    return hashlib.sha1(str(value).encode("utf-8", errors="ignore")).hexdigest()


def normalize_polygon(points, width, height):
    if len(points) < 6 or len(points) % 2:
        return None
    output = []
    for index, value in enumerate(points):
        limit = width if index % 2 == 0 else height
        if not limit:
            return None
        normalized = max(0.0, min(1.0, float(value) / float(limit)))
        output.append(normalized)
    return output


def read_csv(path):
    if not Path(path).exists():
        return []
    with Path(path).open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_manifest(path, rows):
    fields = [
        "image_id",
        "source_id",
        "split",
        "dataset_layer",
        "image_path",
        "label_path",
        "labels",
        "au_core_labels",
        "sio2_outer_labels",
        "nm_per_px",
        "license",
        "license_status",
        "doi",
        "source_url",
        "figure_label",
        "panel_label",
        "caption",
    ]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def copy_image(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
