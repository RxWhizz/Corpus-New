# Corpus
Corpus is a desktop GUI for building curated TEM nanoparticle datasets and measuring particle size distributions. It combines a public-corpus workflow for Au@SiO2 metadata/scraping with the original particle measurement tools for microscopy images.

## Description
Corpus uses Electron as the frontend frame and Python as the backend language. Its measurement mechanism is based on OpenCV, including image processing algorithms and statistical modeling techniques. The main code can be divided by 4 steps: 
1. Extract a plotting scale from the scaled image, or use the GUI to draw the scale line manually.
2. Balance the image's lightness for more accurate recognition.
3. Apply algorithms for the image adjustment.
4. Draw the coutours of the nanoparticles and collect the diameters

It is important to note that the accuracy of the results depends on the quality of the input graph. Therefore, it is recommended to ensure high-resolution and well-defined images for optimal analysis. Additionally, users have the option to customize various parameters.

Furthermore, when the object is very large (just one in the image), we can accurately measure its diameter (the scale should be black though). This code is Diameter-Measurement.py, simple but useful. And you can just enter the folder's name, this program will automatically process every image and export the data to output.xlsx

## Installation
- Install npm [Download npm](https://nodejs.org)

- Open cmd in the root dir:

    npm install electron

    npm install echart

    npm run start

    Relevant Doc: [Building your First App](https://www.electronjs.org/docs/latest/tutorial/tutorial-first-app)

- Packages for Python:

    pip install opencv-python numpy

    The measurement backend uses `cv2` and `numpy`.

## Ubuntu install and build
The repository includes a portable Ubuntu/Linux x64 build at `dist/Corpus-1.0.0-linux-x64.tar.gz`. The archive is stored with Git LFS because it is larger than GitHub's regular file limit.

### Use the prebuilt Ubuntu package
Install runtime dependencies:

```bash
sudo apt update
sudo apt install -y git git-lfs python3 python3-pip libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 xdg-utils libatspi2.0-0 libuuid1 libsecret-1-0
python3 -m pip install --user opencv-python numpy pillow requests
```

Clone with Git LFS and run the app:

```bash
git lfs install
git clone https://github.com/RxWhizz/Corpus.git
cd Corpus
tar -xzf dist/Corpus-1.0.0-linux-x64.tar.gz
cd linux-unpacked
PYTHON=python3 ./corpus
```

If Ubuntu blocks the executable bit after copying the archive, run:

```bash
chmod +x corpus
PYTHON=python3 ./corpus
```

### Build como AppImage (recomendado)

Un AppImage es un ejecutable único y portable: no requiere instalación y funciona en cualquier Ubuntu moderno.

```bash
git clone https://github.com/RxWhizz/Corpus.git
cd Corpus
bash build-ubuntu.sh
```

El script instala automáticamente todas las dependencias del sistema y Python, compila el proyecto y deja el binario listo:

```text
dist/Corpus-1.0.0-linux-x64.AppImage
```

Ejecutar con:

```bash
env -u ELECTRON_RUN_AS_NODE PYTHON=python3 ./dist/Corpus-1.0.0.AppImage
```

> **Nota:** Si lanzas desde un terminal de VSCode, es necesario `env -u ELECTRON_RUN_AS_NODE` porque VSCode establece esa variable para sus propios procesos internos. Desde un terminal externo no hace falta.

### Build del paquete portable (tarball)

Instalar dependencias de compilación:

```bash
sudo apt update
sudo apt install -y nodejs npm python3 python3-pip git git-lfs
python3 -m pip install --user opencv-python numpy pillow requests
```

Compilar el paquete Linux portable:

```bash
git clone https://github.com/RxWhizz/Corpus.git
cd Corpus
npm install
npm run package:ubuntu
```

El artefacto generado es:

```text
dist/Corpus-1.0.0-linux-x64.tar.gz
```

Extraer y ejecutar:

```bash
tar -xzf dist/Corpus-1.0.0-linux-x64.tar.gz -C dist
PYTHON=python3 ./dist/linux-unpacked/corpus
```

Para un paquete Debian, `npm run dist:linux:deb` está disponible, pero requiere `fpm` en la máquina de compilación.

## Usage
1. Generate a TEM graph with a white plotting scale 
<div align=center>
<img src = "https://static.igem.wiki/teams/4702/wiki/software/particle-size-distribution-counter/example.jpg" alt = "example image" style = "padding-left:25%; width:50%;"/>
</div>

2. After entering the app, choose the file path, measurement mode, shape preset, class-specific radius ranges, scale and width of the distribution bars in the scale's unit. Use `Core-shell spheres` for round Au/SiO2 objects, `Core-shell pellets / rods` for elongated particles, and `Generic particles` for the fallback contour detector. For best calibration, click `Mark Scale Line` and mark the two ends of the printed scale bar; the app fills `Manual Bar Length px` automatically and uses that line to calculate nm/px. `Separate touching particles (watershed)` splits touching round particles like ImageJ; it is on for spheres/generic and off for pellets by default. Then click to process image.
<div align=center>
<img src = "https://static.igem.wiki/teams/4702/wiki/software/particle-size-distribution-counter/main-display.png" alt = "example image" style = "padding-left:25%; width:75%;"/>
</div>

3. Then the app will generate an image with measured particles overlaid by class. `Measure Au decorations` marks small dark Au features in red, `Measure SiO2 carriers` marks the visible outer carrier boundary in cyan, and detections that need review are marked in yellow. The app also writes `measurements.json` with paired inner/outer object measurements, confidence scores and review flags.

    <div align=center>
    <img src = "https://static.igem.wiki/teams/4702/wiki/software/particle-size-distribution-counter/image.jpg" alt = "example image" style = "padding-left:12.5%; width:75%;"/>
    </div>
    And it will generate a bar graph, providing users with a clear and intuitive visualization of the particle size distribution.
        <div align=center>
    <img src = "https://static.igem.wiki/teams/4702/wiki/software/particle-size-distribution-counter/bar.png" alt = "example image" style = "padding-left:10%; width:80%;"/>
    </div>

## Contributing
This code is open to contributions.
## Authors and acknowledgment
The inspiration of this script came from Shouyi Hu, and Haotian Shen brought it into codes.

