import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from common import (
    FIGURES_DIR,
    IMAGE_FIELDS,
    IMAGES_CSV,
    RAW_PUBLIC_DIR,
    REPORTS_DIR,
    SOURCE_FIELDS,
    SOURCES_CSV,
    domain_for,
    ensure_dirs,
    fetch_json,
    fetch_url,
    image_size,
    infer_modality,
    license_status_for,
    normalize_source,
    now_iso,
    parse_html_metadata,
    print_json,
    read_csv,
    relative_to_root,
    safe_name,
    split_inputs,
    stable_id,
    upsert_rows,
    write_csv,
    zenodo_record_id,
)


IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp")
HTML_SUFFIXES = ("", ".html", ".htm")


def source_template(raw_input, url):
    domain = domain_for(url)
    return {
        "source_id": stable_id(url, "src"),
        "input": raw_input,
        "url": url,
        "doi": "",
        "domain": domain,
        "title": "",
        "authors": "",
        "journal": "",
        "year": "",
        "publisher": "",
        "license": "",
        "license_url": "",
        "license_status": "missing",
        "modality": "unknown",
        "abstract": "",
        "keywords": "",
        "source_type": detect_adapter(url),
        "decision": "rejected",
        "status": "validated",
        "reason": "",
        "local_path": "",
        "accessed_at": now_iso(),
    }


def detect_adapter(url):
    domain = domain_for(url)
    if domain == "doi.org":
        return "doi"
    if "zenodo.org" in domain:
        return "zenodo"
    if "figshare.com" in domain:
        return "figshare"
    if "pmc.ncbi.nlm.nih.gov" in domain or "ncbi.nlm.nih.gov" in domain:
        return "pmc"
    if "mdpi.com" in domain:
        return "mdpi"
    path = urlparse(url).path.lower()
    if path.endswith(IMAGE_SUFFIXES):
        return "direct_image"
    return "generic_html"


def is_supported_adapter(adapter):
    return adapter in {"doi", "zenodo", "figshare", "pmc", "mdpi", "direct_image", "generic_html"}


def finalize_license(row, accepted_reason="Allowed public license detected."):
    row["license_status"] = license_status_for(" ".join([row.get("license", ""), row.get("license_url", "")]))
    if row["license_status"] == "accepted":
        row["decision"] = "accepted"
        row["reason"] = accepted_reason
    elif row["license_status"] == "missing":
        row["decision"] = "rejected"
        row["reason"] = "No accepted public license detected."
    else:
        row["decision"] = "rejected"
        row["reason"] = "License is not accepted for the public corpus."
    return row


def apply_html_metadata(row, html, base_url):
    metadata = parse_html_metadata(html, base_url)
    for field in [
        "title",
        "doi",
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
    ]:
        if metadata.get(field):
            row[field] = metadata[field]
    row["modality"] = row.get("modality") or infer_modality(" ".join([row.get("title", ""), row.get("abstract", "")]))
    return row, metadata


def validate_zenodo(row):
    zenodo_id = zenodo_record_id(row["url"])
    if not zenodo_id:
        row["reason"] = "Zenodo record id was not found in URL."
        return row
    record, _ = fetch_json(f"https://zenodo.org/api/records/{zenodo_id}")
    metadata = record.get("metadata", {})
    license_data = metadata.get("license") or {}
    license_text = " ".join(
        str(value)
        for value in [license_data.get("id"), license_data.get("title"), license_data.get("url")]
        if value
    )
    row.update(
        {
            "doi": record.get("doi", ""),
            "title": metadata.get("title", ""),
            "authors": "; ".join(creator.get("name", "") for creator in metadata.get("creators", []) if creator.get("name")),
            "year": str(metadata.get("publication_date", ""))[:4],
            "publisher": "Zenodo",
            "license": license_text,
            "license_url": license_data.get("url", ""),
            "abstract": metadata.get("description", ""),
            "keywords": "; ".join(metadata.get("keywords", [])),
            "modality": infer_modality(" ".join([metadata.get("title", ""), metadata.get("description", "")])),
            "source_type": "zenodo",
        }
    )
    return finalize_license(row, "Allowed Zenodo license detected via API.")


def figshare_article_id(url):
    match = re.search(r"/articles/(?:[^/]+/)?(\d+)", url)
    return match.group(1) if match else ""


def validate_figshare(row):
    article_id = figshare_article_id(row["url"])
    if not article_id:
        row["reason"] = "Figshare article id was not found in URL."
        return row
    article, _ = fetch_json(f"https://api.figshare.com/v2/articles/{article_id}")
    license_data = article.get("license") or {}
    row.update(
        {
            "doi": article.get("doi", ""),
            "title": article.get("title", ""),
            "authors": "; ".join(author.get("full_name", "") for author in article.get("authors", []) if author.get("full_name")),
            "year": str(article.get("published_date", ""))[:4],
            "publisher": "Figshare",
            "license": " ".join(str(value) for value in [license_data.get("name"), license_data.get("url")] if value),
            "license_url": license_data.get("url", ""),
            "abstract": article.get("description", ""),
            "keywords": "; ".join(article.get("tags", [])),
            "modality": infer_modality(" ".join([article.get("title", ""), article.get("description", "")])),
            "source_type": "figshare",
        }
    )
    return finalize_license(row, "Allowed Figshare license detected via API.")


def validate_html_like(row):
    data, content_type, final_url = fetch_url(row["url"])
    row["url"] = final_url
    row["domain"] = domain_for(final_url)
    row["source_type"] = detect_adapter(final_url)
    if "html" in content_type.lower() or data[:300].lower().find(b"<html") >= 0:
        row, _ = apply_html_metadata(row, data.decode("utf-8", errors="ignore"), final_url)
        return finalize_license(row)
    if urlparse(final_url).path.lower().endswith(IMAGE_SUFFIXES):
        row["source_type"] = "direct_image"
        row["modality"] = infer_modality(final_url)
        row["reason"] = "Direct image found, but source license was not detectable."
        return row
    row["reason"] = "Unsupported content type or file without detectable license."
    return row


def validate_one(raw_input):
    url = normalize_source(raw_input)
    row = source_template(raw_input, url)
    adapter = row["source_type"]
    if not is_supported_adapter(adapter):
        row["reason"] = "Source adapter is not supported."
        return row
    try:
        if adapter == "doi":
            _, _, final_url = fetch_url(url)
            row = source_template(raw_input, final_url)
            adapter = row["source_type"]
        if adapter == "zenodo":
            row = validate_zenodo(row)
        elif adapter == "figshare":
            row = validate_figshare(row)
        elif adapter in {"pmc", "mdpi", "generic_html", "direct_image"}:
            row = validate_html_like(row)
        else:
            row["reason"] = "Unsupported source adapter."
    except Exception as exc:
        row["status"] = "error"
        row["reason"] = str(exc)
    row["accessed_at"] = now_iso()
    return row


def validate_sources(raw_sources):
    ensure_dirs()
    inputs = split_inputs(raw_sources)
    rows = [validate_one(item) for item in inputs]
    if rows:
        upsert_rows(SOURCES_CSV, SOURCE_FIELDS, rows, "source_id")
    generate_scraper_audit()
    return rows


def download_accepted():
    ensure_dirs()
    rows = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    downloaded = []
    errors = []
    for row in rows:
        if row.get("decision") != "accepted" or row.get("license_status") != "accepted":
            continue
        source_dir = RAW_PUBLIC_DIR / row["source_id"]
        source_dir.mkdir(parents=True, exist_ok=True)
        try:
            if row.get("source_type") == "zenodo":
                record_id = zenodo_record_id(row["url"])
                record, _ = fetch_json(f"https://zenodo.org/api/records/{record_id}")
                output = source_dir / "zenodo_record.json"
                output.write_text(json.dumps(record, indent=2), encoding="utf-8")
            elif row.get("source_type") == "figshare":
                article_id = figshare_article_id(row["url"])
                article, _ = fetch_json(f"https://api.figshare.com/v2/articles/{article_id}")
                output = source_dir / "figshare_article.json"
                output.write_text(json.dumps(article, indent=2), encoding="utf-8")
            else:
                data, content_type, final_url = fetch_url(row["url"])
                suffix = ".html" if "html" in content_type.lower() else Path(urlparse(final_url).path).suffix or ".bin"
                output = source_dir / (safe_name(row.get("title") or row["source_id"], row["source_id"]) + suffix)
                output.write_bytes(data)
                row["url"] = final_url
            row["local_path"] = str(output)
            row["status"] = "downloaded"
            row["accessed_at"] = now_iso()
            downloaded.append({"source_id": row["source_id"], "path": str(output)})
        except Exception as exc:
            row["status"] = "download_error"
            row["reason"] = str(exc)
            errors.append({"source_id": row["source_id"], "error": str(exc)})
    write_csv(SOURCES_CSV, SOURCE_FIELDS, rows)
    generate_scraper_audit()
    return downloaded, errors


def should_keep_image(url, text):
    lowered = f"{url} {text}".lower()
    path = urlparse(url).path.lower()
    if not path.endswith(IMAGE_SUFFIXES) and not any(suffix + "?" in lowered for suffix in IMAGE_SUFFIXES):
        return False
    blocked = ("logo", "icon", "avatar", "sprite", "banner", "ads", "placeholder")
    if any(token in lowered for token in blocked):
        return False
    return any(token in lowered for token in ("fig", "figure", "image", "tem", "stem", "sem", "graph", "media", ".tif", ".jpg", ".png"))


def image_row(source, output, final_url, caption="", original_name="", figure_label="", panel_label=""):
    width, height = image_size(output)
    timestamp = now_iso()
    return {
        "image_id": stable_id(final_url or str(output), "img"),
        "source_id": source["source_id"],
        "file_path": relative_to_root(output),
        "source_url": final_url or source.get("url", ""),
        "license": source.get("license", ""),
        "modality": source.get("modality", ""),
        "width": width,
        "height": height,
        "figure_label": figure_label,
        "panel_label": panel_label,
        "caption": caption[:500],
        "file_sha256": "",
        "original_file_name": original_name or Path(output).name,
        "curation_status": "needs_review",
        "quality_status": "needs_review",
        "scale_status": "missing",
        "metadata_status": "needs_manual_review",
        "scale_nm": "",
        "scale_px": "",
        "nm_per_px": "",
        "split": "",
        "notes": caption[:250],
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def extract_from_json_record(source, local_path, source_dir, max_per_source):
    record = json.loads(local_path.read_text(encoding="utf-8"))
    rows = []
    if local_path.name == "zenodo_record.json":
        files = record.get("files", [])
        for item in files[:max_per_source]:
            key = item.get("key", "")
            links = item.get("links", {})
            file_url = links.get("self") or links.get("download")
            if not file_url or not key.lower().endswith(IMAGE_SUFFIXES):
                continue
            data, _, final_url = fetch_url(file_url)
            output = source_dir / safe_name(f"{stable_id(final_url, 'img')}_{Path(key).name}", Path(key).name)
            output.write_bytes(data)
            rows.append(image_row(source, output, final_url, f"Zenodo file: {key}", key))
    elif local_path.name == "figshare_article.json":
        for item in record.get("files", [])[:max_per_source]:
            file_url = item.get("download_url")
            name = item.get("name", "")
            if not file_url or not name.lower().endswith(IMAGE_SUFFIXES):
                continue
            data, _, final_url = fetch_url(file_url)
            output = source_dir / safe_name(f"{stable_id(final_url, 'img')}_{name}", name)
            output.write_bytes(data)
            rows.append(image_row(source, output, final_url, f"Figshare file: {name}", name))
    return rows


def extract_figures(max_per_source=20):
    ensure_dirs()
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    new_images = []
    errors = []
    for source in sources:
        if source.get("decision") != "accepted" or source.get("license_status") != "accepted" or not source.get("local_path"):
            continue
        local_path = Path(source["local_path"])
        if not local_path.exists():
            errors.append({"source_id": source["source_id"], "error": "Downloaded local_path does not exist."})
            continue
        source_dir = FIGURES_DIR / source["source_id"]
        source_dir.mkdir(parents=True, exist_ok=True)
        try:
            if local_path.name in {"zenodo_record.json", "figshare_article.json"}:
                new_images.extend(extract_from_json_record(source, local_path, source_dir, max_per_source))
                continue
            if local_path.suffix.lower() in IMAGE_SUFFIXES:
                new_images.append(image_row(source, local_path, source.get("url", ""), "Direct source image.", local_path.name))
                continue
            html = local_path.read_text(encoding="utf-8", errors="ignore")
            metadata = parse_html_metadata(html, source["url"])
            kept = 0
            for image in metadata.get("images", []):
                if kept >= max_per_source:
                    break
                caption = image.get("alt", "") or image.get("title", "")
                if not should_keep_image(image["src"], caption):
                    continue
                data, _, final_url = fetch_url(image["src"])
                original_name = Path(urlparse(final_url).path).name or stable_id(final_url, "img") + ".jpg"
                output = source_dir / safe_name(f"{stable_id(final_url, 'img')}_{original_name}", original_name)
                output.write_bytes(data)
                new_images.append(image_row(source, output, final_url, caption, original_name))
                kept += 1
        except Exception as exc:
            errors.append({"source_id": source["source_id"], "error": str(exc)})
    if new_images:
        upsert_rows(IMAGES_CSV, IMAGE_FIELDS, new_images, "image_id")
    generate_scraper_audit()
    return new_images, errors


def generate_scraper_audit():
    ensure_dirs()
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    accepted = [row for row in sources if row.get("decision") == "accepted"]
    rejected = [row for row in sources if row.get("decision") == "rejected"]
    errors = [row for row in sources if row.get("status") in {"error", "download_error"}]
    lines = [
        "# Scraper Audit Report",
        "",
        f"- Sources total: {len(sources)}",
        f"- Sources accepted: {len(accepted)}",
        f"- Sources rejected: {len(rejected)}",
        f"- Source errors: {len(errors)}",
        f"- Extracted image candidates: {len(images)}",
        "",
        "## Accepted Sources",
    ]
    lines.extend(f"- {row['source_id']} | {row.get('source_type', '')} | {row.get('license_status', '')} | {row.get('url', '')}" for row in accepted)
    lines.extend(["", "## Rejected Sources"])
    lines.extend(f"- {row['source_id']} | {row.get('source_type', '')} | {row.get('reason', '')} | {row.get('url', '')}" for row in rejected)
    if errors:
        lines.extend(["", "## Errors"])
        lines.extend(f"- {row['source_id']} | {row.get('status', '')} | {row.get('reason', '')}" for row in errors)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / "scraper_audit.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description="Curated public-corpus scraper.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--sources", default="")
    subparsers.add_parser("download")
    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--max-per-source", type=int, default=20)
    subparsers.add_parser("audit")
    args = parser.parse_args()

    if args.command == "validate":
        rows = validate_sources(args.sources)
        print_json(
            {
                "ok": True,
                "message": f"Validated {len(rows)} source(s).",
                "rows": rows,
                "accepted": sum(1 for row in rows if row.get("decision") == "accepted"),
                "rejected": sum(1 for row in rows if row.get("decision") == "rejected"),
            }
        )
    elif args.command == "download":
        downloaded, errors = download_accepted()
        print_json({"ok": not errors, "message": f"Downloaded {len(downloaded)} accepted source(s); {len(errors)} error(s).", "downloaded": downloaded, "errors": errors})
    elif args.command == "extract":
        images, errors = extract_figures(args.max_per_source)
        print_json({"ok": not errors, "message": f"Extracted {len(images)} figure image(s); {len(errors)} error(s).", "images": images, "errors": errors})
    elif args.command == "audit":
        path = generate_scraper_audit()
        print_json({"ok": True, "message": "Scraper audit generated.", "path": str(path)})


if __name__ == "__main__":
    main()
