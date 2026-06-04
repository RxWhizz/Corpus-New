# Corpus Training

Training starts after real Au@SiO2 TEM images are curated and annotated. Corpus is the local curation, metadata, scale, COCO, and YOLO-seg conversion tool; CVAT or Label Studio is used for manual instance masks.

## Ontology v0

- `0: Au_core`: visible Au core mask.
- `1: SiO2_outer`: full visible outer boundary of the Au@SiO2 particle.

`SiO2_outer` is not only the silica ring; it is the total outside contour used to calculate `D_total`.

## Dataset Layers

- `real_exact`: real Au@SiO2 core-shell TEM images; main training truth.
- `real_near`: related nanoparticle TEM/SEM datasets; transfer/pretraining only.
- `synthetic_core_shell`: generated TEM-like images for curriculum and augmentation.
- `public_demo`: redistributable subset with clear CC BY/CC0/public license.
- `private_training`: internal-only images that must not be redistributed.

## Local PDF Sources

Local paper PDFs can be placed in `Examples/pdfs TEM/`. They are ignored by Git and should be treated as manual-review/private-training material until license and figure reuse rights are confirmed.

```powershell
python training\fetch_training_assets.py local-pdfs
python training\fetch_training_assets.py seed-sources
```

After extracting embedded PDF images, triage them before CVAT curation:

```powershell
python training\extract_paper_figures.py --pdf "Examples\pdfs TEM\materials-17-02213-v2.pdf" --out data\interim\figures\pdf_extracted\materials-17-02213
python training\triage_pdf_figures.py --input data\interim\figures\pdf_extracted --out data\interim\figures\triaged --clean
```

The triage step separates TEM candidates, graphs, abstracts/schemes, mixed figures, and dense TEM tiles. Review `data/interim/figures/triaged/figure_triage_manifest.csv` before exporting anything to CVAT.

The machine-readable inventory is `training/seed_sources.json`; the human guide is `docs/local_pdf_sources.md`.

## Local Flow

1. Curate images in Corpus Builder and confirm metadata, license, scale, and checksum.

2. Export accepted images for CVAT:

   ```powershell
   python training\export_cvat_package.py --out data\training\cvat_package
   ```

   Public-only package:

   ```powershell
   python training\export_cvat_package.py --layer public_demo --out data\training\cvat_public_demo
   ```

3. Annotate in CVAT using polygon instance segmentation labels:

   - `Au_core`
   - `SiO2_outer`

   Exclude scale bars, panel letters, severe blur, edge-cut particles, and ambiguous overlaps. If an object must remain in the master COCO but should not train, mark it with `review_status=needs_review`.

4. Export from CVAT as COCO instance segmentation, then import it:

   ```powershell
   python training\import_cvat_coco.py --coco path\to\instances_default.json
   ```

5. Prepare YOLO-seg and audit it:

   ```powershell
   python training\prepare_yolo_seg.py
   python training\audit_training_dataset.py --min-images 5 --min-au-core 5 --min-sio2-outer 5
   ```

6. Upload `data\training\yolo_seg` to Colab/Drive and run `training\colab_train_yolo_seg.ipynb`.

## One-ZIP Colab Bundle

Generate a Colab-ready ZIP from real CVAT COCO:

```powershell
python training\package_colab_bundle.py --coco data\annotations\cvat_coco_imported.json --clean
```

Or generate a synthetic smoke bundle before real annotation exists:

```powershell
python training\package_colab_bundle.py --synthetic-smoke --clean
```

Convenience npm commands use a Python launcher that works around Windows Python aliases:

```powershell
npm.cmd run training:synthetic-bundle
npm.cmd run training:package
npm.cmd run training:audit
```

The output is:

```text
data\training\colab_bundle\corpus_colab_training_bundle.zip
```

Upload that ZIP in `training\colab_train_yolo_seg.ipynb` and run all cells. The ZIP contains:

- `dataset/data.yaml`
- `dataset/images/{train,val,test}`
- `dataset/labels/{train,val,test}`
- `dataset/manifest.csv`
- `reports/training_dataset_audit.md`
- `docs/dataset_sources.md`
- `training/seed_sources.json`
- `training/colab_run_training.py`

You can also run the Colab runner directly:

```bash
python colab_run_training.py --bundle /content/corpus_colab_training_bundle.zip --smoke-only
python colab_run_training.py --dataset /content/corpus_yolo_seg --full --epochs 75 --imgsz 1024 --batch 4
```

## Synthetic Smoke Dataset

Generate a small synthetic COCO dataset:

```powershell
python training\generate_synthetic_core_shell.py --count 25
python training\prepare_yolo_seg.py --coco data\training\synthetic_core_shell\synthetic_core_shell_coco.json --out data\training\synthetic_yolo_seg
python training\audit_training_dataset.py --dataset data\training\synthetic_yolo_seg --min-images 5 --min-au-core 5 --min-sio2-outer 5
```

Synthetic data is for smoke tests, curriculum, and robustness checks. It does not replace real annotated Au@SiO2 TEM images.

## EMPS Pretraining Dataset

For a general EM/TEM particle detector, use EMPS as `real_near_emps`. It has one YOLO-seg class:

- `0: particle`

This pretraining layer teaches particle boundaries, overlap, and EM texture. It is not Au@SiO2 truth and should not be used to report core/shell metrology.

```powershell
git clone --depth 1 https://github.com/by256/emps.git data\external\emps
npm.cmd run training:prepare-emps
npm.cmd run training:package-emps
```

The prepared dataset is `data\training\emps_yolo_seg`; the Colab ZIP is `data\training\colab_bundle\corpus_colab_training_bundle.zip`. Train this first as a single-class `particle` model, then fine-tune on Corpus Au@SiO2 annotations with `Au_core` and `SiO2_outer`.

## Metrology Export

After importing CVAT COCO, calculate per-object metrology rows:

```powershell
python training\metrology_from_coco.py --coco data\annotations\cvat_coco_imported.json --out data\training\metrology_from_coco.csv
```

The CSV includes `D_core_nm`, `D_total_nm`, and `t_shell_nm` for paired core-shell instances. Use it for comparison against Fiji/ImageJ manual measurements.

## Dataset Targets

- Smoke dataset: 5-10 annotated images.
- Pilot: 150-250 images/tiles.
- Useful v0: 300-600 images/tiles.
- Publication target: 600-1200 images/tiles, 3-5 sources, multiple magnifications and shell thickness ranges.

## Rules

- COCO is the master annotation format.
- YOLO-seg is generated only for training.
- Only images with at least one valid polygon label are exported to YOLO-seg.
- Splits are assigned by source group when no explicit split exists.
- Do not split tiles from the same source/micrograph across train/val/test.
- Local machine is for curation/conversion/audit; Colab/cloud GPU is for training.
