# Local TEM PDF Sources

Local PDFs live in `Examples/pdfs TEM/` and are intentionally ignored by Git. This document records how they should be used without committing the PDFs themselves.

## Core-Shell v0 Candidates

Use these first for the `Au_core` / `SiO2_outer` dataset after license and figure quality review:

- `materials-17-02213-v2.pdf` | DOI `10.3390/ma17102213` | strong Au@SiO2 core-shell candidate.
- `comparative-analysis-of-au-and-au-sio2-nanoparticle-protein-interactions-for-evaluation-as-platforms-in-theranostic.pdf` | DOI `10.1021/acsomega.9b03716` | useful Au vs Au@SiO2 comparison.
- `gold silica.pdf` | DOI `10.1039/c9nr07129f` | gold-silica core-shell PLAL route.
- `nanomaterials-16-00269-v2.pdf` | DOI `10.3390/nano16040269` | review manually; may be core-shell or decorated depending on figure.

## Decorated / Future Model Candidates

These are better for a future `Au_decoration` / `SiO2_carrier` model than for core-shell v0:

- `Highly_sensitive_near-infrared_SERS_nanoprobes_for.pdf` | DOI `10.1186/s12951-022-01327-7`.
- `Gol decoration.pdf` | DOI `10.1039/c8ra01032c`.
- `Photothermal conversion of SiO2@Au nanoparticles mediated by surface morphology of gold cluster layer.pdf` | DOI `10.1039/d0ra06278b`.
- `s42452-021-04456-0.pdf` | DOI `10.1007/s42452-021-04456-0`.
- `materials-15-07470-v2.pdf` | DOI `10.3390/ma15217470`.
- `nanomaterials-13-02156.pdf` | DOI `10.3390/nano13152156`.
- `nanomaterials-10-01996.pdf` | DOI `10.3390/nano10101996`.

## Related / Negative Morphologies

These may help as near-domain negatives or future transfer material, but should not be mixed into core-shell v0 as positive labels:

- `s41598-021-82242-z.pdf` | DOI `10.1038/s41598-021-82242-z`.
- `gases.pdf` | DOI `10.1039/d3lc00136a`.
- `gold.pdf` | DOI `10.1039/c9na00508k`.
- `01NanosphericalSurface-SupportedSeededGrowthofAu.pdf` | DOI `10.1002/ppsc.201400200`.

## Rules

- Do not include the PDFs in Git.
- Do not include extracted figures in a public bundle until license is verified.
- Use local PDFs as `private_training` or manual review candidates by default.
- Extract candidate figures into `data/interim/figures/` or another ignored folder, then curate in Corpus Builder.
- Keep `training/seed_sources.json` as the machine-readable source inventory.

## Useful Commands

```powershell
python training\fetch_training_assets.py local-pdfs
python training\fetch_training_assets.py seed-sources
```

Optional embedded image extraction, if PyMuPDF is installed:

```powershell
python training\extract_paper_figures.py --pdf "Examples\pdfs TEM\materials-17-02213-v2.pdf" --out data\interim\figures\materials-17-02213
```
