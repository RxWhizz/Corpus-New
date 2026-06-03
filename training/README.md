# Corpus Training

Training starts after real images are curated and annotated in CVAT.

## Local Flow

1. Export accepted images for CVAT:

   ```powershell
   python training\export_cvat_package.py --out data\training\cvat_package
   ```

2. Annotate in CVAT using instance segmentation labels:

   - `Au_core`
   - `SiO2_outer`

3. Export from CVAT as COCO instance segmentation, then import it:

   ```powershell
   python training\import_cvat_coco.py --coco path\to\instances_default.json
   ```

4. Prepare YOLO-seg:

   ```powershell
   python training\prepare_yolo_seg.py
   python training\audit_training_dataset.py
   ```

5. Upload `data\training\yolo_seg` to Colab/Drive and run `colab_train_yolo_seg.ipynb`.

## Rules

- Only images with at least one valid polygon label are exported to YOLO-seg.
- Class ids are fixed: `0=Au_core`, `1=SiO2_outer`.
- Splits are assigned by source group when no explicit split exists.
- Local machine is for curation/conversion/audit; Colab/cloud GPU is for training.
