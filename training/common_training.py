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

CLASS_NAMES = ["Au_core", "SiO2_outer"]
CLASS_ALIASES = {
    "au_core": "Au_core",
    "au core": "Au_core",
    "core": "Au_core",
    "gold core": "Au_core",
    "au": "Au_core",
    "sio2_outer": "SiO2_outer",
    "sio2 outer": "SiO2_outer",
    "sio2": "SiO2_outer",
    "silica": "SiO2_outer",
    "silica outer": "SiO2_outer",
    "shell": "SiO2_outer",
    "outer": "SiO2_outer",
}


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
    fields = ["image_id", "source_id", "split", "image_path", "label_path", "labels"]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def copy_image(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
