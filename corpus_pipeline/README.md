# Corpus Pipeline

This pipeline is driven from the Electron `Corpus Builder` tab. It keeps a public-corpus bias: sources without a clear reusable license are rejected by default.

## Phase 2 Scraper

The scraper is centralized in `scraper.py`. The older entrypoints remain as GUI-compatible wrappers:

- `search_sources.py` -> `scraper.py validate`
- `download_sources.py` -> `scraper.py download`
- `extract_figures.py` -> `scraper.py extract`

Supported adapters:

- DOI resolver
- Zenodo API
- Figshare API
- PMC / NCBI HTML
- MDPI HTML
- generic HTML with detectable public license
- direct images only when already attached to an accepted source

## GUI Flow

1. Add DOI or URL candidates in `Sources`.
2. Click `Search / Validate Sources`.
3. Click `Download Accepted`.
4. Click `Extract Figures`.
5. Review each image in `Curate` and mark it `Accept`, `Reject`, or `Needs Review`.
6. Enter manual scale data in `Calibrate`.
7. Enrich, edit, validate, and hash records in `Metadata`.
8. Export `COCO`, `YOLO-seg`, and the audit report.

## Files

- `data/sources.csv`: source URL, DOI, license, decision, and download status.
- `data/images.csv`: extracted figure metadata, hashes, captions, and curation state.
- `data/calibration.csv`: manual `nm_per_px` calibration and metrology context.
- `data/annotations/coco_master.json`: master annotation scaffold.
- `data/exports/yolo-seg/`: training export.
- `reports/audit.md`: public-corpus audit summary.
- `reports/scraper_audit.md`: source acceptance/rejection and extraction summary.
- `reports/metadata_audit.md`: metadata completeness and publication-readiness summary.

## License Policy

Accepted by default: CC BY, CC0, public domain, and equivalent open attribution licenses.

Rejected by default: missing license, closed publisher pages, CC BY-NC, CC BY-ND, and CC BY-NC-ND.

The scraper never downloads rejected sources into `data/raw/public/`.

## CLI Smoke Test

```powershell
python corpus_pipeline\scraper.py validate --sources "https://zenodo.org/records/4563942"
python corpus_pipeline\scraper.py download
python corpus_pipeline\scraper.py extract
python corpus_pipeline\scraper.py audit
```

## Metadata Commands

- `metadata.py enrich-source`: enriches source metadata from Zenodo API or HTML meta tags.
- `metadata.py hash-images`: calculates SHA256 hashes for extracted images.
- `metadata.py validate-metadata`: updates metadata status and writes `reports/metadata_audit.md`.
- `metadata.py update-source` / `update-image`: used by the GUI to save manual edits.
