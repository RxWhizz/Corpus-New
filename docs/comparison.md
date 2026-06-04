# Comparison Notes

Corpus is a TEM-focused curation and lightweight metrology tool. It intentionally overlaps with familiar microscopy operations such as thresholding, watershed, particle filtering, overlays, and measurement summaries, but it does not copy the interface, text, or menu structure of other tools.

## ImageJ/Fiji

ImageJ/Fiji is broader and more mature for general image analysis. Corpus is narrower: it prioritizes TEM nanoparticle workflows, manual scale-line calibration, publicable metadata, class-aware Au/SiO2 measurements, and simple review/export from one GUI.

## CVAT and Label Studio

CVAT and Label Studio are better choices for detailed manual mask annotation. Corpus prepares curated images and metadata for annotation but does not try to replace those tools for segmentation labeling.

## Ultralytics and AI Segmentation

Ultralytics YOLO-seg and related AI tools are useful after enough real annotated data exists. Corpus currently focuses on curation and non-AI pre-metrology, with exports designed to support later training workflows.

## Particle Sizing Tools

General particle sizing tools can be faster for single-population images. Corpus is aimed at TEM cases where the user needs traceable scale calibration, separate Au/SiO2 populations, decorated nanoparticle summaries, and manual review of ambiguous detections.
