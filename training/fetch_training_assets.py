import argparse
import json
from pathlib import Path

from common_training import ROOT


SEED_PATH = ROOT / "training" / "seed_sources.json"
DEFAULT_OUT = ROOT / "data" / "training" / "asset_queries"

SEARCH_QUERIES = [
    '"Au@SiO2" TEM core shell nanoparticle PMCID',
    '"gold silica core-shell" TEM "shell thickness" open access',
    '"Au@SiO2" "transmission electron microscopy" DOI',
    '"gold nanoparticle" TEM segmentation dataset',
    '"nanoparticle TEM" masks Zenodo',
    '"electron microscopy" nanoparticle segmentation GitHub',
    '"core shell nanoparticle" synthetic TEM generator',
]


def load_seed_sources():
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def seed_sources(output_dir=None):
    payload = load_seed_sources()
    lines = ["# Corpus Training Seed Sources", ""]
    lines.append("## Seed Papers")
    for row in payload.get("seed_papers", []):
        lines.append(f"- DOI {row['doi']} | priority {row.get('priority', '')} | {row.get('reason', '')}")
    lines.extend(["", "## Search Queries"])
    for query in SEARCH_QUERIES:
        lines.append(f"- {query}")
    lines.extend(["", "## Related Datasets"])
    for row in payload.get("related_datasets", []):
        caution = "license-check-required" if row.get("redistribution_caution") else "metadata-check-required"
        lines.append(f"- {row['name']} | {caution} | {row.get('use', '')}")
    lines.extend(["", "## Local PDF Sources"])
    for row in payload.get("local_pdf_sources", []):
        lines.append(
            f"- {row.get('doi', '')} | priority {row.get('priority', '')} | "
            f"{row.get('training_use', '')} | {row.get('file', '')}"
        )

    text = "\n".join(lines)
    print(text)
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "seed_sources.md").write_text(text, encoding="utf-8")
        (output_dir / "seed_sources.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def related_datasets(output_dir=None):
    payload = load_seed_sources()
    rows = []
    for row in payload.get("related_datasets", []):
        rows.append(
            {
                "name": row.get("name", ""),
                "use": row.get("use", ""),
                "redistribution_caution": bool(row.get("redistribution_caution")),
                "download_status": "manual_review_required",
                "reason": "No automatic download until URL and license are explicitly verified.",
            }
        )
    print(json.dumps({"ok": True, "related_datasets": rows}, indent=2))
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "related_datasets_review.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def local_pdfs(output_dir=None):
    payload = load_seed_sources()
    rows = payload.get("local_pdf_sources", [])
    existing = []
    for row in rows:
        item = dict(row)
        item["exists"] = (ROOT / item.get("file", "")).exists()
        item["download_status"] = "local_pdf_manual_review"
        item["public_bundle_status"] = "excluded_until_license_verified"
        existing.append(item)
    print(json.dumps({"ok": True, "local_pdf_sources": existing}, indent=2))
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "local_pdf_sources_review.json").write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return existing


def main():
    parser = argparse.ArgumentParser(description="Fetch or export safe training asset references.")
    parser.add_argument("command", choices=["seed-sources", "related-datasets", "local-pdfs"])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    if args.command == "seed-sources":
        seed_sources(args.out)
    elif args.command == "related-datasets":
        related_datasets(args.out)
    elif args.command == "local-pdfs":
        local_pdfs(args.out)


if __name__ == "__main__":
    main()
