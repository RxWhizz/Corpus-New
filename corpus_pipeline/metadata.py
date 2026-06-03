import argparse
import json
import re

from common import (
    IMAGE_FIELDS,
    IMAGES_CSV,
    REPORTS_DIR,
    SOURCE_FIELDS,
    SOURCES_CSV,
    fetch_json,
    fetch_url,
    infer_modality,
    license_status_for,
    now_iso,
    parse_html_metadata,
    print_json,
    read_csv,
    resolve_path,
    sha256_file,
    write_csv,
    zenodo_record_id,
)


def enrich_sources(source_id=""):
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    changed = []
    errors = []
    for row in sources:
        if source_id and row["source_id"] != source_id:
            continue
        try:
            zenodo_id = zenodo_record_id(row.get("url", ""))
            if zenodo_id:
                record, _ = fetch_json(f"https://zenodo.org/api/records/{zenodo_id}")
                metadata = record.get("metadata", {})
                license_data = metadata.get("license") or {}
                license_text = " ".join(
                    str(value)
                    for value in [license_data.get("id"), license_data.get("title"), license_data.get("url")]
                    if value
                )
                row["title"] = metadata.get("title", row.get("title", ""))
                row["authors"] = "; ".join(
                    creator.get("name", "") for creator in metadata.get("creators", []) if creator.get("name")
                )
                row["doi"] = record.get("doi", row.get("doi", ""))
                row["year"] = str(metadata.get("publication_date", ""))[:4]
                row["publisher"] = "Zenodo"
                row["license"] = license_text or row.get("license", "")
                row["license_url"] = license_data.get("url", row.get("license_url", ""))
                row["abstract"] = metadata.get("description", row.get("abstract", ""))
                row["keywords"] = "; ".join(metadata.get("keywords", [])) or row.get("keywords", "")
                row["source_type"] = "zenodo_record"
            elif row.get("url"):
                data, content_type, final_url = fetch_url(row["url"])
                if "html" in content_type.lower() or data[:200].lower().find(b"<html") >= 0:
                    metadata = parse_html_metadata(data.decode("utf-8", errors="ignore"), final_url)
                    for field in [
                        "title",
                        "doi",
                        "authors",
                        "journal",
                        "year",
                        "publisher",
                        "license",
                        "license_url",
                        "modality",
                        "abstract",
                        "keywords",
                        "source_type",
                    ]:
                        if metadata.get(field):
                            row[field] = metadata[field]
                    row["url"] = final_url
            row["license_status"] = license_status_for(" ".join([row.get("license", ""), row.get("license_url", "")]))
            row["modality"] = row.get("modality") or infer_modality(" ".join([row.get("title", ""), row.get("abstract", "")]))
            row["decision"] = "accepted" if row["license_status"] == "accepted" else "rejected"
            row["status"] = "metadata_enriched"
            row["accessed_at"] = now_iso()
            changed.append(row["source_id"])
        except Exception as exc:
            row["status"] = "metadata_error"
            row["reason"] = str(exc)
            errors.append({"source_id": row.get("source_id", ""), "error": str(exc)})
    write_csv(SOURCES_CSV, SOURCE_FIELDS, sources)
    return {"changed": changed, "errors": errors}


def hash_images():
    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    hashed = []
    errors = []
    for image in images:
        path = resolve_path(image.get("file_path", ""))
        if not path or not path.exists():
            errors.append({"image_id": image.get("image_id", ""), "error": "File not found."})
            continue
        try:
            image["file_sha256"] = sha256_file(path)
            if not image.get("original_file_name"):
                image["original_file_name"] = path.name
            image["updated_at"] = now_iso()
            hashed.append(image["image_id"])
        except Exception as exc:
            errors.append({"image_id": image.get("image_id", ""), "error": str(exc)})
    write_csv(IMAGES_CSV, IMAGE_FIELDS, images)
    return {"hashed": hashed, "errors": errors}


def validate_metadata(write_report=True):
    sources = read_csv(SOURCES_CSV, SOURCE_FIELDS)
    images = read_csv(IMAGES_CSV, IMAGE_FIELDS)
    sources_by_id = {source["source_id"]: source for source in sources if source.get("source_id")}
    source_warnings = []
    image_warnings = []

    for source in sources:
        source["license_status"] = license_status_for(" ".join([source.get("license", ""), source.get("license_url", "")]))
        missing = [field for field in ["url", "license", "license_status"] if not source.get(field)]
        if source["license_status"] != "accepted":
            missing.append("accepted_license")
        if missing:
            source_warnings.append({"source_id": source["source_id"], "missing": missing})

    for image in images:
        source = sources_by_id.get(image.get("source_id", ""), {})
        missing = [
            field
            for field in ["source_id", "file_path", "source_url", "license", "file_sha256", "width", "height", "modality", "quality_status"]
            if not image.get(field)
        ]
        if not (image.get("caption") or image.get("notes")):
            missing.append("caption_or_notes")
        if source.get("license_status") != "accepted":
            missing.append("accepted_source_license")
        if image.get("curation_status") == "accepted" and image.get("nm_per_px") and image.get("scale_status") == "confirmed" and not missing:
            image["metadata_status"] = "ready"
        elif source.get("license_status") not in ("", "accepted"):
            image["metadata_status"] = "blocked"
        else:
            image["metadata_status"] = "needs_manual_review"
        if image.get("curation_status") == "accepted" and missing:
            image_warnings.append({"image_id": image["image_id"], "missing": missing})

    write_csv(SOURCES_CSV, SOURCE_FIELDS, sources)
    write_csv(IMAGES_CSV, IMAGE_FIELDS, images)

    report = {
        "sources": len(sources),
        "publication_ready_sources": sum(1 for row in sources if row.get("license_status") == "accepted"),
        "license_blocked_sources": sum(1 for row in sources if row.get("license_status") == "rejected_for_public_corpus"),
        "images": len(images),
        "images_missing_caption": sum(1 for row in images if not (row.get("caption") or row.get("notes"))),
        "images_missing_scale": sum(1 for row in images if not row.get("nm_per_px")),
        "images_missing_checksum": sum(1 for row in images if not row.get("file_sha256")),
        "metadata_ready_images": sum(1 for row in images if row.get("metadata_status") == "ready"),
        "source_warnings": source_warnings,
        "image_warnings": image_warnings,
    }
    if write_report:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Metadata Audit Report",
            "",
            f"- Sources: {report['sources']}",
            f"- Publication-ready sources: {report['publication_ready_sources']}",
            f"- License-blocked sources: {report['license_blocked_sources']}",
            f"- Images: {report['images']}",
            f"- Images missing caption/notes: {report['images_missing_caption']}",
            f"- Images missing scale: {report['images_missing_scale']}",
            f"- Images missing checksum: {report['images_missing_checksum']}",
            f"- Metadata-ready images: {report['metadata_ready_images']}",
            "",
            "## Source Warnings",
        ]
        lines.extend(f"- {item['source_id']}: {', '.join(item['missing'])}" for item in source_warnings)
        lines.extend(["", "## Image Warnings"])
        lines.extend(f"- {item['image_id']}: {', '.join(item['missing'])}" for item in image_warnings)
        (REPORTS_DIR / "metadata_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def parse_metadata_json(raw):
    try:
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        pairs = {}
        for piece in re.split(r"[;\n]+", raw or ""):
            if "=" in piece:
                key, value = piece.split("=", 1)
                pairs[key.strip()] = value.strip()
        return pairs


def update_row(path, fields, key_name, key_value, metadata):
    rows = read_csv(path, fields)
    updated = None
    allowed = set(fields) - {key_name}
    for row in rows:
        if row[key_name] == key_value:
            for key, value in metadata.items():
                if key in allowed:
                    row[key] = str(value)
            if "license" in fields:
                row["license_status"] = license_status_for(" ".join([row.get("license", ""), row.get("license_url", "")]))
            if "updated_at" in fields:
                row["updated_at"] = now_iso()
            updated = row
            break
    write_csv(path, fields, rows)
    return updated


def main():
    parser = argparse.ArgumentParser(description="Manage public corpus metadata.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    enrich_parser = subparsers.add_parser("enrich-source")
    enrich_parser.add_argument("--source-id", default="")
    subparsers.add_parser("hash-images")
    subparsers.add_parser("validate-metadata")
    source_parser = subparsers.add_parser("update-source")
    source_parser.add_argument("--source-id", required=True)
    source_parser.add_argument("--metadata-json", required=True)
    image_parser = subparsers.add_parser("update-image")
    image_parser.add_argument("--image-id", required=True)
    image_parser.add_argument("--metadata-json", required=True)
    args = parser.parse_args()

    if args.command == "enrich-source":
        result = enrich_sources(args.source_id)
        print_json({"ok": not result["errors"], "message": f"Enriched {len(result['changed'])} source(s).", **result})
    elif args.command == "hash-images":
        result = hash_images()
        print_json({"ok": not result["errors"], "message": f"Hashed {len(result['hashed'])} image(s).", **result})
    elif args.command == "validate-metadata":
        print_json({"ok": True, "message": "Metadata validation complete.", "report": validate_metadata()})
    elif args.command == "update-source":
        updated = update_row(SOURCES_CSV, SOURCE_FIELDS, "source_id", args.source_id, parse_metadata_json(args.metadata_json))
        print_json({"ok": updated is not None, "message": "Source metadata saved." if updated else "Source not found.", "source": updated})
    elif args.command == "update-image":
        updated = update_row(IMAGES_CSV, IMAGE_FIELDS, "image_id", args.image_id, parse_metadata_json(args.metadata_json))
        print_json({"ok": updated is not None, "message": "Image metadata saved." if updated else "Image not found.", "image": updated})


if __name__ == "__main__":
    main()
