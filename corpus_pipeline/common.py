import csv
import hashlib
import json
import re
import struct
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_PUBLIC_DIR = DATA_DIR / "raw" / "public"
FIGURES_DIR = DATA_DIR / "interim" / "figures"
TILES_DIR = DATA_DIR / "interim" / "tiles"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
EXPORTS_DIR = DATA_DIR / "exports" / "yolo-seg"
REPORTS_DIR = ROOT / "reports"

SOURCES_CSV = DATA_DIR / "sources.csv"
IMAGES_CSV = DATA_DIR / "images.csv"
CALIBRATION_CSV = DATA_DIR / "calibration.csv"
REVIEW_QUEUE_CSV = DATA_DIR / "review_queue.csv"
COCO_MASTER_JSON = ANNOTATIONS_DIR / "coco_master.json"

SOURCE_FIELDS = [
    "source_id",
    "input",
    "url",
    "doi",
    "domain",
    "title",
    "authors",
    "journal",
    "year",
    "publisher",
    "license",
    "license_url",
    "license_status",
    "modality",
    "abstract",
    "keywords",
    "source_type",
    "decision",
    "status",
    "reason",
    "local_path",
    "accessed_at",
]

IMAGE_FIELDS = [
    "image_id",
    "source_id",
    "file_path",
    "source_url",
    "license",
    "modality",
    "width",
    "height",
    "figure_label",
    "panel_label",
    "caption",
    "file_sha256",
    "original_file_name",
    "curation_status",
    "quality_status",
    "scale_status",
    "metadata_status",
    "scale_nm",
    "scale_px",
    "nm_per_px",
    "split",
    "notes",
    "created_at",
    "updated_at",
]

CALIBRATION_FIELDS = [
    "image_id",
    "scale_nm",
    "scale_px",
    "nm_per_px",
    "method",
    "scale_source",
    "scale_confidence",
    "magnification",
    "instrument",
    "sample_prep",
    "operator_notes",
    "updated_at",
]

REVIEW_FIELDS = [
    "image_id",
    "reason",
    "created_at",
]

ALLOWED_DOMAINS = (
    "ncbi.nlm.nih.gov",
    "pmc.ncbi.nlm.nih.gov",
    "zenodo.org",
    "figshare.com",
    "mdpi.com",
)

LICENSE_PATTERNS = (
    "cc by",
    "cc-by",
    "cc_by",
    "creative commons attribution",
    "creativecommons.org/licenses/by",
    "cc0",
    "public domain",
)

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AuSiO2CorpusBuilder/0.1"


def ensure_dirs():
    for path in [
        DATA_DIR,
        RAW_PUBLIC_DIR,
        FIGURES_DIR,
        TILES_DIR,
        ANNOTATIONS_DIR,
        EXPORTS_DIR,
        REPORTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(value, prefix):
    digest = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def read_csv(path, fields):
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for row in reader:
            normalized = {field: row.get(field, "") for field in fields}
            rows.append(normalized)
        return rows


def write_csv(path, fields, rows):
    ensure_dirs()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def upsert_rows(path, fields, rows, key):
    existing = read_csv(path, fields)
    by_key = {row.get(key): row for row in existing if row.get(key)}
    for row in rows:
        row_key = row.get(key)
        if row_key:
            current = by_key.get(row_key, {})
            current.update(row)
            by_key[row_key] = current
    write_csv(path, fields, list(by_key.values()))


def print_json(payload):
    print(json.dumps(payload, ensure_ascii=True))


def fetch_url(url, timeout=20):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("content-type", "")
        final_url = response.geturl()
        data = response.read()
    return data, content_type, final_url


def normalize_source(value):
    cleaned = value.strip()
    if not cleaned:
        return ""
    if cleaned.lower().startswith("doi:"):
        return "https://doi.org/" + cleaned.split(":", 1)[1].strip()
    if re.match(r"^10\.\d{4,9}/", cleaned, flags=re.I):
        return "https://doi.org/" + cleaned
    if not re.match(r"^https?://", cleaned, flags=re.I):
        return "https://" + cleaned
    return cleaned


def domain_for(url):
    return urlparse(url).netloc.lower().replace("www.", "")


def is_allowed_domain(domain):
    return any(domain == allowed or domain.endswith("." + allowed) for allowed in ALLOWED_DOMAINS)


def is_allowed_license(text):
    lowered = (text or "").lower()
    if any(term in lowered for term in ("noncommercial", "no derivatives", "no-derivatives")):
        return False
    if re.search(r"cc[-_\s]?by[-_\s]?(nc|nd)", lowered):
        return False
    return any(pattern in lowered for pattern in LICENSE_PATTERNS)


def license_status_for(text):
    if not text:
        return "missing"
    return "accepted" if is_allowed_license(text) else "rejected_for_public_corpus"


def infer_modality(text):
    haystack = (text or "").lower()
    if "haadf" in haystack:
        return "HAADF"
    if "bf-tem" in haystack or "bright-field tem" in haystack:
        return "BF-TEM"
    if "stem" in haystack:
        return "STEM"
    if "tem" in haystack or "transmission electron" in haystack:
        return "TEM"
    if "sem" in haystack or "scanning electron" in haystack:
        return "SEM"
    return "unknown"


class MetadataParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.title_parts = []
        self.in_title = False
        self.in_caption = False
        self.caption_parts = []
        self.meta = []
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            self.meta.append(attrs)
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "img" and attrs.get("src"):
            self.images.append(
                {
                    "src": urljoin(self.base_url, attrs.get("src")),
                    "alt": attrs.get("alt", ""),
                    "title": attrs.get("title", ""),
                }
            )
        elif tag in ("figcaption", "caption"):
            self.in_caption = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag in ("figcaption", "caption"):
            self.in_caption = False

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data.strip())
        if self.in_caption:
            self.caption_parts.append(data.strip())

    @property
    def title(self):
        return " ".join(part for part in self.title_parts if part).strip()

    @property
    def captions(self):
        caption = " ".join(part for part in self.caption_parts if part).strip()
        return [caption] if caption else []


def parse_html_metadata(html, base_url):
    parser = MetadataParser(base_url)
    parser.feed(html)
    meta_texts = []
    doi = ""
    license_text = ""
    license_url = ""
    title = parser.title
    authors = []
    journal = ""
    year = ""
    publisher = ""
    abstract = ""
    keywords = ""

    for item in parser.meta:
        name = (item.get("name") or item.get("property") or "").lower()
        content = item.get("content") or ""
        if content:
            meta_texts.append(content)
        if name in ("citation_doi", "dc.identifier", "dc.identifier.doi"):
            doi = content
        if "license" in name or "rights" in name:
            license_text = content
            if content.startswith("http"):
                license_url = content
        if name in ("citation_title", "dc.title", "og:title") and content:
            title = content
        if name in ("citation_author", "dc.creator") and content:
            authors.append(content)
        if name in ("citation_journal_title", "dc.source", "prism.publicationname") and content:
            journal = content
        if name in ("citation_publication_date", "citation_date", "dc.date", "article:published_time") and content:
            match = re.search(r"\d{4}", content)
            if match:
                year = match.group(0)
        if name in ("citation_publisher", "dc.publisher") and content:
            publisher = content
        if name in ("description", "dc.description", "citation_abstract") and content and not abstract:
            abstract = content
        if name in ("keywords", "citation_keywords", "dc.subject") and content:
            keywords = content

    for link in parser.links:
        rel = (link.get("rel") or "").lower()
        href = link.get("href") or ""
        if "license" in rel and href:
            license_url = href
            license_text = href

    page_text = " ".join(meta_texts + [title, html[:5000]])
    if not license_text:
        match = re.search(
            r"(creativecommons\.org/licenses/[a-z0-9\-/\.]+|CC[-\s]?BY(?:[-\s]NC)?(?:[-\s]ND)?|CC0)",
            page_text,
            flags=re.I,
        )
        if match:
            license_text = match.group(1)
            if license_text.startswith("creativecommons"):
                license_url = "https://" + license_text
            elif license_text.startswith("http"):
                license_url = license_text

    return {
        "title": title,
        "doi": doi,
        "authors": "; ".join(authors),
        "journal": journal,
        "year": year,
        "publisher": publisher,
        "license": license_text,
        "license_url": license_url,
        "license_status": license_status_for(" ".join([license_text, license_url])),
        "modality": infer_modality(page_text),
        "abstract": abstract,
        "keywords": keywords,
        "source_type": "article",
        "images": parser.images,
        "captions": parser.captions,
    }


def image_size(path):
    path = Path(path)
    try:
        import cv2

        image = cv2.imread(str(path))
        if image is None:
            raise ValueError("OpenCV could not read image.")
        height, width = image.shape[:2]
        return str(width), str(height)
    except Exception:
        pass

    try:
        from PIL import Image

        with Image.open(path) as image:
            width, height = image.size
        return str(width), str(height)
    except Exception:
        pass

    try:
        with path.open("rb") as handle:
            header = handle.read(32)
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                width, height = struct.unpack(">II", header[16:24])
                return str(width), str(height)
            if header.startswith(b"\xff\xd8"):
                handle.seek(2)
                while True:
                    marker_start = handle.read(1)
                    if marker_start != b"\xff":
                        break
                    marker = handle.read(1)
                    while marker == b"\xff":
                        marker = handle.read(1)
                    length_bytes = handle.read(2)
                    if len(length_bytes) != 2:
                        break
                    length = struct.unpack(">H", length_bytes)[0]
                    if marker in [bytes([code]) for code in range(0xC0, 0xC4)]:
                        segment = handle.read(5)
                        height, width = struct.unpack(">HH", segment[1:5])
                        return str(width), str(height)
                    handle.seek(length - 2, 1)
    except Exception:
        pass

    return "", ""


def safe_name(value, fallback):
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", value or "").strip("_")
    return name[:120] or fallback


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def split_inputs(raw):
    pieces = re.split(r"[\n,;]+", raw or "")
    return [piece.strip() for piece in pieces if piece.strip()]


def zenodo_record_id(url):
    match = re.search(r"zenodo\.org/(?:records|record)/(\d+)", url)
    return match.group(1) if match else ""


def fetch_json(url, timeout=20):
    data, _, final_url = fetch_url(url, timeout=timeout)
    return json.loads(data.decode("utf-8", errors="ignore")), final_url


def relative_to_root(path):
    if not path:
        return ""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def resolve_path(value):
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return ROOT / path
