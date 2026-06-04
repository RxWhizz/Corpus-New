# Corpus

Corpus is an open-source desktop GUI for curated TEM nanoparticle datasets and lightweight non-AI metrology. It is built with Electron for the interface and Python/OpenCV for image processing.

The project is focused on practical TEM curation: source metadata, image review, manual scale calibration, reproducible measurement settings, overlays, histograms, Gaussian reference curves, and export-friendly measurement metadata. It does not replace expert review, CVAT/Label Studio annotation, or AI segmentation in ambiguous images.

## Features

- Manual scale-line calibration from the printed scale bar.
- Shape presets for:
  - Core-shell spheres
  - Core-shell rods / pellets
  - Decorated nanoparticles
  - Generic TEM particles
- Class-aware non-AI measurement for Au decorations and SiO2 carriers.
- Watershed separation for touching round particles.
- Segmentation Assist for dark particles, bright shells, and manual gray ranges.
- Particle Filters for radius, circularity, elongation, edge exclusion, and hole handling.
- Measurement Basket for reviewing, editing, rejecting, and exporting detections.
- Summary reports with counts, means, standard deviations, histogram data, Gaussian reference curves, warnings, and settings in `measurements.json`.
- Corpus Builder tools for curated public metadata and dataset preparation.

## Install on Windows

Install Node.js LTS from [nodejs.org](https://nodejs.org/). Install Python 3.10+ from [python.org](https://www.python.org/downloads/windows/) and make sure it is available as `python` or set `PYTHON` explicitly.

```powershell
cd "C:\Users\LUIS\Documents\GitHub\Corpus-New"
npm.cmd install
python -m pip install opencv-python numpy pillow requests pandas matplotlib
npm.cmd run start
```

If PowerShell blocks `npm.ps1`, use `npm.cmd` as shown above.

If Python is installed in a custom path:

```powershell
$env:PYTHON="C:\Path\To\python.exe"
npm.cmd run start
```

## Install on Ubuntu

```bash
sudo apt update
sudo apt install -y nodejs npm python3 python3-pip git \
  libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 \
  xdg-utils libatspi2.0-0 libuuid1 libsecret-1-0

git clone https://github.com/RxWhizz/Corpus-New.git
cd Corpus-New
npm install
python3 -m pip install --user opencv-python numpy pillow requests pandas matplotlib
PYTHON=python3 npm run start
```

## Build on Ubuntu

The repository stays source-only. Build outputs are generated locally under `dist/` and should be attached to GitHub Releases, not committed to Git.

```bash
git clone https://github.com/RxWhizz/Corpus-New.git
cd Corpus-New
bash build-ubuntu.sh
```

Run the generated AppImage:

```bash
env -u ELECTRON_RUN_AS_NODE PYTHON=python3 ./dist/*.AppImage
```

`env -u ELECTRON_RUN_AS_NODE` is useful when launching from VSCode terminals, which may set that variable for internal Electron processes.

## Quick Tutorial

1. Open `Particle Measurement`.
2. Choose `Easy` for the guided workflow.
3. Load a TEM image.
4. Select the sample type:
   - `Core-shell spheres` for round Au/SiO2 objects.
   - `Core-shell rods / pellets` for elongated particles.
   - `Decorated nanoparticles` for SiO2 carriers decorated with small Au particles.
   - `Generic TEM particles` when the sample does not match the other presets.
5. Enter the printed scale length in nm.
6. Click `Mark Scale Line` and mark the two ends of the printed scale bar.
7. Click `Process Image`.
8. Review the overlay and Measurement Basket. Edit or reject questionable detections.
9. Export CSV or use `measurements.json` for traceable downstream reporting.

Switch to `Advanced` when the image needs manual gray thresholds, circularity/elongation filters, numbered overlays, or more control over watershed separation.

## Decorated Nanoparticles

The `Decorated nanoparticles` preset is intended for systems such as SiO2 particles decorated with Au nanoparticles. It measures:

- Au decoration diameter distribution.
- SiO2 carrier outer diameter distribution.
- Decorations per carrier.
- Approximate decoration density per 1000 nm2.

For synthesis-specific studies, record the source DOI, protocol notes, precursor concentration, Raman label, laser wavelength, and expected size range in the Corpus Builder metadata panel. The PDF or article itself should not be committed unless redistribution rights are clear.

## AI Dataset v0

The first AI training target is Au@SiO2 core-shell TEM instance segmentation, not decorated nanoparticles. The fixed v0 classes are:

- `0: Au_core`
- `1: SiO2_outer`

Corpus prepares curated images, scale metadata, COCO master annotations, YOLO-seg exports, and dataset audits. Fine masks are created in CVAT or Label Studio. See `training/README.md` and `docs/dataset_sources.md`.

To make a Colab-ready training bundle:

```powershell
python training\package_colab_bundle.py --synthetic-smoke --clean
python training\package_colab_bundle.py --coco data\annotations\cvat_coco_imported.json --clean
```

Upload `data\training\colab_bundle\corpus_colab_training_bundle.zip` to `training\colab_train_yolo_seg.ipynb` and run all cells.

Convenience commands:

```powershell
npm.cmd run training:synthetic-bundle
npm.cmd run training:package
```

Local paper PDFs for candidate TEM figures can be kept in `Examples/pdfs TEM/`; they are ignored by Git. Use `python training\fetch_training_assets.py local-pdfs` to audit the local inventory and `docs/local_pdf_sources.md` for the current classification.

## Outputs

The measurement backend writes:

- `processed_image.jpg`: overlay image.
- `measurements.json`: complete settings, scale calibration, measurements, review flags, warnings, normality hints, and decorated-particle metrics when applicable.
- `diameters.txt`: legacy compatibility output.

Generated outputs are ignored by Git by default.

## Relationship to Other Tools

Corpus is inspired by common microscopy workflows, including thresholding, watershed, filtering, object review, and measurement summaries. It uses its own TEM-focused naming, UI, implementation, and documentation.

- ImageJ/Fiji remains a broad, mature image-analysis environment.
- CVAT and Label Studio are better for manual mask annotation at dataset scale.
- Ultralytics and other deep-learning tools are better for trained segmentation once enough annotated data exists.
- Corpus aims to be easier for curated TEM workflows where scale, metadata, review status, and exportable measurements matter from the first screen.

## Limitations

- Non-AI measurement is a pre-metrology tool, not final truth for complex overlaps, low contrast, or ambiguous shells.
- Manual scale calibration is strongly recommended.
- Watershed can over-split elongated particles, so it is off by default for rods/pellets.
- Gaussian curves are visual/reference aids. For small sample sizes, `measurements.json` marks normality as insufficient rather than definitive.
- Publication-quality datasets still need license checks, metadata review, and manual annotation when segmentation masks are required.

## Development Checks

```bash
node --check main.js
node --check render.js
python3 -m py_compile measurement_modes.py python_script.py preview_image.py
bash -n build-ubuntu.sh corpus-launch.sh
```

## License

MIT. See `LICENSE`.
