# Dataset Source Priorities for Au@SiO2 Core-Shell

This guide summarizes the source strategy from `C:\Users\LUIS\Downloads\deep-research-report(1).md`.

## Primary Target

Build a curated Au@SiO2 core-shell TEM dataset with instance masks for:

- `Au_core`
- `SiO2_outer`

No public dataset found in the report already provides a large, ready-to-train, dual-mask Au@SiO2 core-shell corpus. Corpus should therefore curate real images and combine them with related datasets and synthetic core-shell images.

## Search Priority

1. PMC / PubMed Central open-access articles.
2. Zenodo, Figshare, and Dryad datasets with clear licenses.
3. MDPI, PMC-hosted RSC Advances, Discover Nano, and other open-access article pages.
4. GitHub repositories for tooling, masks, and synthetic workflows.
5. Kaggle only for exploration, not publishable ground truth.

## Seed Papers

Start with these DOI queries in the Corpus source validator:

- `10.1039/C6TB01659F`
- `10.1039/C9RA02543J`
- `10.3390/ma17102213`
- `10.1186/s11671-024-04141-2`
- `10.1021/acsomega.9b03716`

Preferred images are TEM or BF-TEM with visible Au/SiO2 contrast, readable scale bars, and separable core-shell particles.

## Related Datasets for Transfer or Smoke Tests

- TEMExtraction: useful for literature-mined TEM, scale/figure workflows, and some segmentation annotations; check image reuse rights before redistribution.
- BAM Automatic SEM Image Segmentation: useful for aggregation/overlap and synthetic generation ideas; data license is not ideal for public redistribution.
- EMcopilot: useful for synthetic EM and self-supervised workflows.
- Nanowire TEM morphology dataset: useful for TEM segmentation transfer, not morphology-specific to Au@SiO2.
- Illinois Patchy Nanoparticles: useful as related raw nanoparticle imagery and metadata, not direct segmentation truth.

## Inclusion Rules

- Prefer native TIFF/DM3/DM4/EMD when available; otherwise use figure crops with manual scale-line calibration.
- Record DOI, source URL, license, license URL, authors, journal, year, figure, panel, caption, modality, magnification when known, and `nm_per_px`.
- Split by source, article, figure, or original micrograph. Never split random tiles from the same original image across train/val/test.
- Separate `public_demo` from `private_training`; do not publish figures from unclear or restricted licenses.

## Annotation Rules

- `Au_core`: closed mask of the visible Au core.
- `SiO2_outer`: closed mask of the full visible outer particle boundary.
- Exclude edge-truncated, heavily overlapped, low-focus, or ambiguous particles from the training export.
- Preserve questionable objects only in the master COCO with `review_status=needs_review`.
