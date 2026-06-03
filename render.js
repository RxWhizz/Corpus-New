const fs = require('fs');
const path = require('path');
const electron = require('electron');
const echarts = require('echarts');
const { ipcRenderer } = electron;
const { dialog } = require('@electron/remote');

const BROWSER_IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg']);

function needsPreviewConversion(filePath) {
  return !BROWSER_IMAGE_EXTS.has(path.extname(filePath).toLowerCase());
}

async function resolvePreviewSrc(filePath) {
  if (!needsPreviewConversion(filePath)) {
    return fileUrl(filePath);
  }
  try {
    const result = await ipcRenderer.invoke('image-to-preview', { imagePath: filePath });
    if (result && result.ok) return result.dataUrl;
  } catch (_) {}
  return null;
}

let Scale = document.getElementById('scale');
let Count = document.getElementById('Count');
let CountCarrier = document.getElementById('CountCarrier');
const manualMeasureBar     = document.getElementById('manualMeasureBar');
const manualMeasureBtn     = document.getElementById('manualMeasureBtn');
const manualMeasureStatus  = document.getElementById('manualMeasureStatus');
const manualMeasureResult  = document.getElementById('manualMeasureResult');
const manualMeasureAddArea = document.getElementById('manualMeasureAddArea');
const manualMeasureClass   = document.getElementById('manualMeasureClass');
const manualMeasureAdd     = document.getElementById('manualMeasureAdd');
const manualMeasureClear   = document.getElementById('manualMeasureClear');
const imageInput = document.getElementById('imageInput');
const measurementMode = document.getElementById('measurementMode');
const shapePreset = document.getElementById('shapePreset');
const auMinRadiusInput = document.getElementById('auMinRadius');
const auMaxRadiusInput = document.getElementById('auMaxRadius');
const sio2MinRadiusInput = document.getElementById('sio2MinRadius');
const sio2MaxRadiusInput = document.getElementById('sio2MaxRadius');
const manualScalePx = document.getElementById('manualScalePx');
const excludeEdges = document.getElementById('excludeEdges');
const watershed = document.getElementById('watershed');
const processButton = document.getElementById('processButton');
const recommendedSettingsButton = document.getElementById('recommendedSettingsButton');
const measurementHint = document.getElementById('measurementHint');
const scaleTool = document.getElementById('scaleTool');
const scaleCanvas = document.getElementById('scaleCanvas');
const scaleLineStatus = document.getElementById('scaleLineStatus');
const markScaleLineButton = document.getElementById('markScaleLineButton');
const clearScaleLineButton = document.getElementById('clearScaleLineButton');
let resultDiv = document.getElementById('result');
const measurementSummary = document.getElementById('measurementSummary');
const measurementDetails = document.getElementById('measurementDetails');

let image = null;
let img = document.createElement('img');
let charts = [];
let scalePreviewImage = null;
let currentPayload = null;
let editingObjectId = null;
let tableSortCol = null;
let tableSortAsc = true;

// Particle overlay
const overlayCanvas = document.createElement('canvas');
overlayCanvas.id = 'particleOverlay';
const particleMenu = document.getElementById('particleMenu');
const particleMenuLabel = document.getElementById('particleMenuLabel');
const pmEditBtn = document.getElementById('pmEditBtn');
const pmRejectBtn = document.getElementById('pmRejectBtn');
const pmCloseBtn = document.getElementById('pmCloseBtn');
let activeParticleId  = null;
let manualMeasureMode = false;
let manualCenter      = null;   // {x, y} in image coords
let manualLastMeasure = null;   // {center, edge, rPx, diamNm} after second click
const rejectedObjects = new Map(); // objectId → {center_x, center_y, radius_px}

function particleDisplayScale() {
    if (!img.naturalWidth) return { sx: 1, sy: 1 };
    return {
        sx: img.offsetWidth  / img.naturalWidth,
        sy: img.offsetHeight / img.naturalHeight
    };
}

function drawParticleOverlay(highlightId) {
    if (!currentPayload || !currentPayload.measurements) return;
    const { sx, sy } = particleDisplayScale();
    overlayCanvas.width  = img.offsetWidth;
    overlayCanvas.height = img.offsetHeight;
    const ctx = overlayCanvas.getContext('2d');
    ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    // Cover rejected particles by painting over with the sampled background color
    if (rejectedObjects.size > 0 && img.complete && img.naturalWidth) {
        let coverCtx = overlayCanvas._coverCtx;
        if (!coverCtx || overlayCanvas._coverSrc !== img.src) {
            const tmp = document.createElement('canvas');
            tmp.width  = img.naturalWidth;
            tmp.height = img.naturalHeight;
            coverCtx = tmp.getContext('2d');
            coverCtx.drawImage(img, 0, 0);
            overlayCanvas._coverCtx = coverCtx;
            overlayCanvas._coverSrc = img.src;
        }
        rejectedObjects.forEach(obj => {
            const cx = obj.center_x * sx;
            const cy = obj.center_y * sy;
            const r  = Math.max(10, (obj.radius_px || 20) * sx) + 3;
            // Sample background color from just outside the circle (8 points)
            const imgCx = obj.center_x;
            const imgCy = obj.center_y;
            const imgR  = (obj.radius_px || 20) + 6;
            let rSum = 0, gSum = 0, bSum = 0, n = 0;
            for (let i = 0; i < 8; i++) {
                const a  = i * Math.PI / 4;
                const px = Math.round(imgCx + Math.cos(a) * imgR);
                const py = Math.round(imgCy + Math.sin(a) * imgR);
                if (px >= 0 && py >= 0 && px < img.naturalWidth && py < img.naturalHeight) {
                    const d = coverCtx.getImageData(px, py, 1, 1).data;
                    rSum += d[0]; gSum += d[1]; bSum += d[2]; n++;
                }
            }
            const col = n > 0
                ? `rgb(${Math.round(rSum/n)},${Math.round(gSum/n)},${Math.round(bSum/n)})`
                : 'rgb(128,128,128)';
            ctx.save();
            ctx.fillStyle   = col;
            ctx.strokeStyle = col;
            ctx.lineWidth   = 5;
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, Math.PI * 2);
            ctx.fill();
            ctx.stroke();
            ctx.restore();
        });
    }

    // Draw active measurements
    currentPayload.measurements.forEach(obj => {
        const cx = obj.center_x * sx;
        const cy = obj.center_y * sy;
        const r  = Math.max(10, (obj.inner ? obj.inner.radius_px : 20) * sx);
        const isHl = obj.object_id === highlightId;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        if (isHl) {
            ctx.fillStyle   = 'rgba(255, 255, 255, 0.25)';
            ctx.fill();
            ctx.strokeStyle = '#facc15';
            ctx.lineWidth   = 3;
        } else {
            ctx.strokeStyle = obj.review_status === 'needs_review'
                ? 'rgba(220, 80, 80, 0.55)'
                : 'rgba(80, 200, 80, 0.55)';
            ctx.lineWidth = 2;
        }
        ctx.stroke();
    });
}

function particleAtPoint(clientX, clientY) {
    if (!currentPayload || !currentPayload.measurements) return null;
    const rect = img.getBoundingClientRect();
    const mx = clientX - rect.left;
    const my = clientY - rect.top;
    const { sx, sy } = particleDisplayScale();
    let best = null, bestDist = Infinity;
    currentPayload.measurements.forEach(obj => {
        const cx = obj.center_x * sx;
        const cy = obj.center_y * sy;
        const r  = Math.max(10, (obj.inner ? obj.inner.radius_px : 20) * sx);
        const d  = Math.hypot(cx - mx, cy - my);
        if (d <= r + 8 && d < bestDist) { best = obj; bestDist = d; }
    });
    return best;
}

function showParticleMenu(obj, clientX, clientY) {
    activeParticleId = obj.object_id;
    particleMenuLabel.textContent = `${obj.object_id} · ${obj.review_status}`;
    const menuW = 170, menuH = 130;
    const left = Math.min(clientX + 10, window.innerWidth  - menuW - 10);
    const top  = Math.min(clientY + 10, window.innerHeight - menuH - 10);
    particleMenu.style.left    = left + 'px';
    particleMenu.style.top     = top  + 'px';
    particleMenu.style.display = 'block';
    drawParticleOverlay(obj.object_id);
}

function hideParticleMenu() {
    particleMenu.style.display = 'none';
    activeParticleId = null;
    drawParticleOverlay(null);
}

function clientToImageCoords(clientX, clientY) {
    const rect = img.getBoundingClientRect();
    const sx   = img.naturalWidth  / img.offsetWidth;
    const sy   = img.naturalHeight / img.offsetHeight;
    return {
        x: (clientX - rect.left) * sx,
        y: (clientY - rect.top)  * sy
    };
}

function drawManualMeasure(centerImg, edgeImg) {
    const { sx, sy } = particleDisplayScale();
    const ctx = overlayCanvas.getContext('2d');

    if (centerImg) {
        const cx = centerImg.x / sx * sx;   // already in image coords, convert to canvas
        const cy = centerImg.y / sy * sy;
        const cx2 = centerImg.x * (img.offsetWidth  / img.naturalWidth);
        const cy2 = centerImg.y * (img.offsetHeight / img.naturalHeight);

        ctx.save();
        ctx.strokeStyle = '#facc15';
        ctx.fillStyle   = '#facc15';
        ctx.lineWidth   = 2;
        // crosshair at center
        ctx.beginPath(); ctx.moveTo(cx2 - 10, cy2); ctx.lineTo(cx2 + 10, cy2); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(cx2, cy2 - 10); ctx.lineTo(cx2, cy2 + 10); ctx.stroke();

        if (edgeImg) {
            const ex2 = edgeImg.x * (img.offsetWidth  / img.naturalWidth);
            const ey2 = edgeImg.y * (img.offsetHeight / img.naturalHeight);
            const rPx = Math.hypot(ex2 - cx2, ey2 - cy2);
            // radius line
            ctx.beginPath(); ctx.moveTo(cx2, cy2); ctx.lineTo(ex2, ey2); ctx.stroke();
            // circle
            ctx.beginPath(); ctx.arc(cx2, cy2, rPx, 0, Math.PI * 2);
            ctx.strokeStyle = 'rgba(250,204,21,0.7)'; ctx.stroke();
            // dot at edge
            ctx.beginPath(); ctx.arc(ex2, ey2, 4, 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore();
    }
}

function startManualMeasure() {
    manualMeasureMode = true;
    manualCenter      = null;
    manualMeasureBtn.textContent  = 'Cancelar';
    manualMeasureBtn.classList.remove('secondary');
    manualMeasureResult.textContent = '';
    manualMeasureStatus.textContent = '1. Click en el centro de la partícula';
    drawParticleOverlay(null);
}

function stopManualMeasure() {
    manualMeasureMode = false;
    manualCenter      = null;
    manualMeasureBtn.textContent = 'Manual Measure';
    manualMeasureBtn.classList.add('secondary');
    manualMeasureStatus.textContent = '';
    drawParticleOverlay(null);
}

manualMeasureBtn.onclick   = () => manualMeasureMode ? stopManualMeasure() : startManualMeasure();
manualMeasureClear.onclick = () => {
    stopManualMeasure();
    manualMeasureResult.textContent    = '';
    manualMeasureAddArea.style.display = 'none';
    manualLastMeasure = null;
};

manualMeasureAdd.onclick = () => {
    if (!manualLastMeasure || !currentPayload) return;
    const { center, rPx, diamNm } = manualLastMeasure;
    const cls = manualMeasureClass.value;
    const id  = `manual_${Date.now()}`;
    const innerObj = {
        class:              cls,
        diameter:           diamNm,
        major_axis:         diamNm,
        minor_axis:         diamNm,
        equivalent_diameter: diamNm,
        radius_px:          rPx,
        center_x:           center.x,
        center_y:           center.y,
        area_px:            Math.PI * rPx * rPx,
        aspect_ratio:       1.0,
        shape:              'manual',
        angle:              0,
        separation_method:  'manual',
        flags:              ['manual']
    };
    currentPayload.measurements.push({
        object_id:               id,
        review_status:           'ready',
        pair_status:             'manual',
        confidence_score:        1.0,
        center_x:                center.x,
        center_y:                center.y,
        inner_major_axis:        diamNm,
        inner_minor_axis:        diamNm,
        outer_major_axis:        0,
        outer_minor_axis:        0,
        equivalent_diameter:     diamNm,
        shell_thickness_estimate: 0,
        inner_outer_ratio:       0,
        flags:                   ['manual'],
        inner:                   innerObj,
        outer:                   null
    });
    manualMeasureAddArea.style.display = 'none';
    manualMeasureResult.textContent    = `Añadido: ${diamNm.toFixed(2)} nm`;
    manualMeasureStatus.textContent    = 'Click "Manual Measure" para medir otra.';
    manualLastMeasure = null;
    refreshResults();
};

function mountOverlay() {
    if (!img.naturalWidth) return;

    // Wrap img so overlay canvas can be positioned on top of it
    let wrap = img.parentNode;
    if (!wrap || !wrap.classList.contains('img-wrap')) {
        wrap = document.createElement('div');
        wrap.className = 'img-wrap';
        resultDiv.replaceChild(wrap, img);
        wrap.appendChild(img);
    }

    overlayCanvas.width  = img.offsetWidth;
    overlayCanvas.height = img.offsetHeight;
    overlayCanvas.style.width  = img.offsetWidth  + 'px';
    overlayCanvas.style.height = img.offsetHeight + 'px';

    if (!wrap.contains(overlayCanvas)) wrap.appendChild(overlayCanvas);
    drawParticleOverlay(null);

    overlayCanvas.onmousemove = (e) => {
        const obj = particleAtPoint(e.clientX, e.clientY);
        overlayCanvas.style.cursor = obj ? 'pointer' : 'default';
        if (particleMenu.style.display === 'none' || !particleMenu.style.display) {
            drawParticleOverlay(obj ? obj.object_id : null);
        }
    };
    overlayCanvas.onmouseleave = () => {
        if (!activeParticleId) drawParticleOverlay(null);
        overlayCanvas.style.cursor = 'default';
    };
    overlayCanvas.onclick = (e) => {
        if (manualMeasureMode) {
            const pt = clientToImageCoords(e.clientX, e.clientY);
            if (!manualCenter) {
                manualCenter = pt;
                manualMeasureStatus.textContent = '2. Click en el borde de la partícula';
                drawParticleOverlay(null);
                drawManualMeasure(manualCenter, null);
            } else {
                const nmPerPx = currentPayload && currentPayload.nm_per_px;
                if (nmPerPx) {
                    const rPx  = Math.hypot(pt.x - manualCenter.x, pt.y - manualCenter.y);
                    const diam = 2 * rPx * nmPerPx;
                    manualLastMeasure = { center: manualCenter, edge: pt, rPx, diamNm: diam };
                    manualMeasureResult.textContent = `Diámetro estimado: ${diam.toFixed(2)} nm`;
                    manualMeasureStatus.textContent = 'Listo. Agrega al histograma o mide de nuevo.';
                    manualMeasureAddArea.style.display = 'flex';
                } else {
                    manualMeasureResult.textContent = 'Sin escala disponible — procesa la imagen primero.';
                    manualLastMeasure = null;
                }
                drawParticleOverlay(null);
                drawManualMeasure(manualCenter, pt);
                manualMeasureMode = false;
                manualMeasureBtn.textContent = 'Manual Measure';
                manualMeasureBtn.classList.add('secondary');
            }
            return;
        }
        const obj = particleAtPoint(e.clientX, e.clientY);
        if (obj) showParticleMenu(obj, e.clientX, e.clientY);
        else     hideParticleMenu();
    };
}

pmEditBtn.onclick   = () => { hideParticleMenu(); startEdit(activeParticleId); document.getElementById('measurementDetails').scrollIntoView({ behavior: 'smooth' }); };
pmRejectBtn.onclick = () => { const id = activeParticleId; hideParticleMenu(); rejectMeasurement(id); };
pmCloseBtn.onclick  = () => hideParticleMenu();
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideParticleMenu(); });
let scaleCanvasScale = 1;
let scaleLineMode = false;
let scaleLineDraft = [];
let manualScaleLine = null;

const measurementPresets = {
    spheres: {
        mode: 'both',
        scale: 50,
        binWidth: '',
        auMin: 8,
        auMax: 18,
        sio2Min: 18,
        sio2Max: 35,
        watershed: true,
        hint: 'Para esferas núcleo-corteza. Empareja los núcleos Au (rojo) con los portadores SiO2 (cian) y reporta diámetro interno, externo y espesor de corteza.'
    },
    pellets: {
        mode: 'both',
        scale: 50,
        binWidth: '',
        auMin: 20,
        auMax: 35,
        sio2Min: 30,
        sio2Max: 45,
        watershed: false,
        hint: 'Para varillas o pellets. Mide el eje largo del núcleo Au oscuro y el eje largo del portador SiO2 circundante.'
    },
    generic: {
        mode: 'both',
        scale: 50,
        binWidth: '',
        auMin: 1,
        auMax: 50,
        sio2Min: 20,
        sio2Max: 500,
        watershed: true,
        hint: 'Fallback contour detector for mixed particles. Use it when the sample is not clearly spherical or rod-like.'
    }
};

function parsePositiveNumber(input, label) {
    const value = parseFloat(input.value);
    if (!Number.isFinite(value) || value <= 0) {
        throw new Error(`${label} must be greater than 0.`);
    }
    return value;
}

function clearMeasurementResults() {
    if (img.parentNode === resultDiv) {
        resultDiv.removeChild(img);
    }
    measurementSummary.innerHTML = '';
    measurementDetails.innerHTML = '';
    charts.forEach(c => c.dispose());
    charts = [];
}

function scaleLineLength(line) {
    if (!line) {
        return 0;
    }
    const dx = line.x2 - line.x1;
    const dy = line.y2 - line.y1;
    return Math.sqrt(dx * dx + dy * dy);
}

function updateScaleLineStatus(message) {
    if (!scaleLineStatus) {
        return;
    }
    if (message) {
        scaleLineStatus.textContent = message;
        return;
    }
    if (manualScaleLine) {
        scaleLineStatus.textContent = `Escala manual: ${scaleLineLength(manualScaleLine).toFixed(2)} px`;
    } else if (scaleLineDraft.length === 1) {
        scaleLineStatus.textContent = 'Primer punto marcado. Click en el otro extremo de la barra.';
    } else {
        scaleLineStatus.textContent = 'No manual scale line marked.';
    }
}

function drawScaleCanvas() {
    if (!scaleCanvas || !scalePreviewImage) {
        return;
    }
    const context = scaleCanvas.getContext('2d');
    context.clearRect(0, 0, scaleCanvas.width, scaleCanvas.height);
    context.drawImage(scalePreviewImage, 0, 0, scaleCanvas.width, scaleCanvas.height);

    const points = manualScaleLine
        ? [{ x: manualScaleLine.x1, y: manualScaleLine.y1 }, { x: manualScaleLine.x2, y: manualScaleLine.y2 }]
        : scaleLineDraft;

    if (!points.length) {
        return;
    }

    context.save();
    context.lineWidth = 3;
    context.strokeStyle = '#facc15';
    context.fillStyle = '#facc15';
    context.shadowColor = '#111827';
    context.shadowBlur = 3;
    points.forEach((point) => {
        context.beginPath();
        context.arc(point.x * scaleCanvasScale, point.y * scaleCanvasScale, 4, 0, Math.PI * 2);
        context.fill();
    });
    if (points.length === 2) {
        context.beginPath();
        context.moveTo(points[0].x * scaleCanvasScale, points[0].y * scaleCanvasScale);
        context.lineTo(points[1].x * scaleCanvasScale, points[1].y * scaleCanvasScale);
        context.stroke();
    }
    context.restore();
}

function resetManualScaleLine(clearInput = true) {
    scaleLineMode = false;
    scaleLineDraft = [];
    manualScaleLine = null;
    if (clearInput) {
        manualScalePx.value = '';
    }
    updateScaleLineStatus();
    drawScaleCanvas();
}

function loadScalePreview(filePath) {
    if (!scaleTool || !scaleCanvas) {
        return;
    }
    if (!filePath) {
        scaleTool.classList.remove('active');
        scalePreviewImage = null;
        resetManualScaleLine(true);
        return;
    }

    scaleTool.classList.add('active');
    scalePreviewImage = new Image();
    scalePreviewImage.onload = () => {
        const maxW = 900;
        const maxH = window.innerHeight - 300;
        scaleCanvasScale = Math.min(
            1,
            maxW / scalePreviewImage.naturalWidth,
            maxH / scalePreviewImage.naturalHeight
        );
        scaleCanvas.width = Math.max(1, Math.round(scalePreviewImage.naturalWidth * scaleCanvasScale));
        scaleCanvas.height = Math.max(1, Math.round(scalePreviewImage.naturalHeight * scaleCanvasScale));
        resetManualScaleLine(true);
        drawScaleCanvas();
    };
    scalePreviewImage.onerror = () => {
        scaleTool.classList.remove('active');
        updateScaleLineStatus('No se pudo cargar la vista previa de escala.');
    };
    resolvePreviewSrc(filePath).then(src => {
        if (src) {
            scalePreviewImage.src = src;
        } else {
            scaleTool.classList.remove('active');
            updateScaleLineStatus('No se pudo cargar la vista previa de escala.');
        }
    });
}

function canvasEventToImagePoint(event) {
    const rect = scaleCanvas.getBoundingClientRect();
    // Use offsetX/offsetY which are already relative to the canvas element,
    // unaffected by the parent wrap's scroll position.
    const canvasX = event.offsetX;
    const canvasY = event.offsetY;
    return {
        x: Math.max(0, Math.min(scalePreviewImage.naturalWidth, canvasX / scaleCanvasScale)),
        y: Math.max(0, Math.min(scalePreviewImage.naturalHeight, canvasY / scaleCanvasScale))
    };
}

function updateModeInputState() {
    const mode = measurementMode.value;
    const auDisabled = mode === 'sio2';
    const sio2Disabled = mode === 'au';
    auMinRadiusInput.disabled = auDisabled;
    auMaxRadiusInput.disabled = auDisabled;
    sio2MinRadiusInput.disabled = sio2Disabled;
    sio2MaxRadiusInput.disabled = sio2Disabled;
}

function applyRecommendedSettings(forceMode = true) {
    const preset = measurementPresets[shapePreset.value] || measurementPresets.spheres;
    if (forceMode) {
        measurementMode.value = preset.mode;
    }
    Scale.value = preset.scale;
    Count.value = preset.binWidth;
    CountCarrier.value = preset.binWidth;
    auMinRadiusInput.value = preset.auMin;
    auMaxRadiusInput.value = preset.auMax;
    sio2MinRadiusInput.value = preset.sio2Min;
    sio2MaxRadiusInput.value = preset.sio2Max;
    manualScalePx.value = '';
    resetManualScaleLine(true);
    excludeEdges.checked = true;
    watershed.checked = preset.watershed;
    measurementHint.textContent = preset.hint;
    updateModeInputState();
}

function setProcessing(isProcessing) {
    processButton.disabled = isProcessing;
    processButton.textContent = isProcessing ? 'Processing...' : 'Process Image';
}

function classesForMode(mode) {
    if (mode === 'au') {
        return ['Au_decorations'];
    }
    if (mode === 'sio2') {
        return ['SiO2_carrier'];
    }
    return ['Au_decorations', 'SiO2_carrier'];
}

function classColor(className) {
    return className === 'Au_decorations'
        ? 'rgba(220, 38, 38, 0.72)'
        : 'rgba(14, 165, 233, 0.72)';
}

function classLabel(className) {
    return className === 'Au_decorations' ? 'Decoraciones Au' : 'Portadores SiO2';
}

function summarizeMeasurements(payload) {
    const objectSummary = payload.object_summary || {};
    const classSummary = payload.summary || {};
    const entries = Object.entries(classSummary);
    if (!entries.length && !objectSummary.objects) {
        measurementSummary.innerHTML = '<div class="metric"><strong>0</strong>Sin mediciones encontradas</div>';
        return;
    }

    const scaleCandidates = payload.scale_candidates || [];
    const selectedScale = payload.selected_scale || {};
    const classMetrics = entries.map(([className, stats]) => `
        <div class="metric">
            <strong>${stats.count || 0}</strong>
            ${classLabel(className)}<br>
            Mean: ${Number(stats.mean_diameter || 0).toFixed(2)}
        </div>
    `).join('');

    measurementSummary.innerHTML = `
        <div class="metric">
            <strong>${objectSummary.paired || 0}/${objectSummary.objects || 0}</strong>
            objetos emparejados
        </div>
        <div class="metric">
            <strong>${Number(objectSummary.mean_inner_major_axis || 0).toFixed(2)}</strong>
            eje mayor interno medio
        </div>
        <div class="metric">
            <strong>${Number(objectSummary.mean_outer_major_axis || 0).toFixed(2)}</strong>
            eje mayor externo medio
        </div>
        <div class="metric">
            <strong>${objectSummary.watershed_splits || 0}</strong>
            separaciones watershed<br>
            ${escapeHtml(payload.separation_method || 'contour/hough')}
        </div>
        ${classMetrics}
        <div class="metric">
            <strong>${Number(payload.nm_per_px || 0).toPrecision(5)}</strong>
            unidad de escala / px
        </div>
        <div class="metric">
            <strong>${Number(selectedScale.width_px || payload.scale_bar_px || 0).toFixed(1)}</strong>
            barra de escala (px)<br>
            ${scaleCandidates.length} candidatos
        </div>
    `;
}

function autoBinWidth(values) {
    const n = values.length;
    if (n < 2) return 1;
    const sorted = [...values].sort((a, b) => a - b);
    const range  = sorted[sorted.length - 1] - sorted[0];
    if (range === 0) return 1;
    const mean = values.reduce((a, b) => a + b, 0) / n;
    const std  = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / n);

    // Scott's rule, clamped to 6–25 bins
    const scott  = std > 0 ? 3.49 * std * Math.pow(n, -1 / 3) : range / 10;
    const bwMin  = range / 25;
    const bwMax  = range / 6;
    let bw       = Math.max(bwMin, Math.min(bwMax, scott));

    // Round to nearest "nice" number
    const mag        = Math.pow(10, Math.floor(Math.log10(bw)));
    const candidates = [0.5, 1, 1.5, 2, 2.5, 5, 10].map(f => f * mag);
    bw = candidates
        .filter(c => c >= bwMin * 0.9)
        .reduce((best, c) => Math.abs(c - bw) < Math.abs(best - bw) ? c : best);

    return Math.max(0.1, bw);
}

// Returns 100-point [x, y] pairs for a smooth Gaussian on a value axis
function smoothGaussian(values, minVal, maxVal, binWidth) {
    const n = values.length;
    if (n < 2) return null;
    const mean = values.reduce((a, b) => a + b, 0) / n;
    const std  = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / n);
    if (std < 1e-9) return null;
    const PTS  = 120;
    const step = (maxVal - minVal) / PTS;
    return Array.from({ length: PTS + 1 }, (_, i) => {
        const x = minVal + i * step;
        const y = (n * binWidth) / (std * Math.sqrt(2 * Math.PI)) *
                  Math.exp(-0.5 * ((x - mean) / std) ** 2);
        return [parseFloat(x.toFixed(4)), parseFloat(y.toFixed(4))];
    });
}

function measurementSeries(payload) {
    const objects = payload.measurements || [];
    if (payload.shape_preset === 'spheres') {
        return [
            {
                name: 'Diámetro interno',
                color: 'rgba(220, 38, 38, 0.72)',
                values: objects.map((row) => Number(row.inner_major_axis)).filter((value) => value > 0)
            },
            {
                name: 'Diámetro externo',
                color: 'rgba(14, 165, 233, 0.72)',
                values: objects.map((row) => Number(row.outer_major_axis)).filter((value) => value > 0)
            },
            {
                name: 'Espesor de corteza',
                color: 'rgba(245, 158, 11, 0.72)',
                values: objects.map((row) => Number(row.shell_thickness_estimate)).filter((value) => value > 0)
            }
        ];
    }
    if (payload.shape_preset === 'pellets') {
        return [
            {
                name: 'Eje mayor interno',
                color: 'rgba(220, 38, 38, 0.72)',
                values: objects.map((row) => Number(row.inner_major_axis)).filter((value) => value > 0)
            },
            {
                name: 'Eje mayor externo',
                color: 'rgba(14, 165, 233, 0.72)',
                values: objects.map((row) => Number(row.outer_major_axis)).filter((value) => value > 0)
            },
            {
                name: 'Eje menor externo',
                color: 'rgba(16, 185, 129, 0.72)',
                values: objects.map((row) => Number(row.outer_minor_axis)).filter((value) => value > 0)
            }
        ];
    }

    const flat = payload.class_measurements || [];
    return classesForMode(payload.mode)
        .filter((className) => flat.some((row) => row.class === className))
        .map((className) => ({
            name: classLabel(className),
            color: classColor(className),
            values: flat.filter((row) => row.class === className).map((row) => Number(row.diameter))
        }));
}

function exportChartPng(chartInstance, seriesName) {
    const url = chartInstance.getDataURL({ type: 'png', pixelRatio: 2, backgroundColor: '#fff' });
    const base64 = url.replace(/^data:image\/png;base64,/, '');
    const safeName = seriesName.replace(/[^a-z0-9]/gi, '_');
    const defaultPath = currentPayload && currentPayload.measurements_path
        ? currentPayload.measurements_path.replace(/\.json$/, `_${safeName}.png`)
        : `${safeName}.png`;
    const savePath = dialog.showSaveDialogSync({
        title: 'Exportar gráfica como PNG',
        defaultPath,
        filters: [{ name: 'PNG Image', extensions: ['png'] }]
    });
    if (!savePath) return;
    fs.writeFileSync(savePath, Buffer.from(base64, 'base64'));
    alert(`Gráfica guardada en:\n${savePath}`);
}

function renderMeasurementChart(payload) {
    const userBwDecoration = parseFloat(Count.value);
    const userBwCarrier    = parseFloat(CountCarrier.value);
    const seriesDefs = measurementSeries(payload);
    const container  = document.getElementById('chartsContainer');

    charts.forEach(c => c.dispose());
    charts = [];
    container.innerHTML = '';

    seriesDefs.forEach(def => {
        const values = def.values.filter(v => Number.isFinite(v) && v > 0);
        if (!values.length) return;

        // Pick the right bin input: decoration (Au) vs carrier (SiO2)
        const isCarrier = def.name.toLowerCase().includes('sio2') ||
                          def.name.toLowerCase().includes('carrier') ||
                          def.name.toLowerCase().includes('outer') ||
                          def.name.toLowerCase().includes('shell');
        const userBw = isCarrier ? userBwCarrier : userBwDecoration;
        const binInput = isCarrier ? CountCarrier : Count;

        // Auto bin width unless user specified one
        const binWidth = (userBw > 0) ? userBw : autoBinWidth(values);
        if (!(userBw > 0) && binInput) binInput.placeholder = `auto: ${binWidth}`;

        const rawMin  = Math.min(...values);
        const rawMax  = Math.max(...values);
        const minVal  = Math.floor(rawMin / binWidth) * binWidth;
        const maxVal  = Math.ceil(rawMax  / binWidth) * binWidth;
        const nBins   = Math.max(1, Math.ceil((maxVal - minVal) / binWidth));

        const labels = Array.from({ length: nBins }, (_, i) =>
            (minVal + i * binWidth).toFixed(binWidth < 1 ? 2 : 1)
        );
        const counts = new Array(nBins).fill(0);
        values.forEach(v => {
            const idx = Math.min(nBins - 1, Math.max(0, Math.floor((v - minVal) / binWidth)));
            counts[idx]++;
        });

        const n    = values.length;
        const mean = values.reduce((a, b) => a + b, 0) / n;
        const std  = Math.sqrt(values.reduce((a, b) => a + (b - mean) ** 2, 0) / n);

        // Extend Gaussian range slightly beyond data for full bell shape
        const gaussMin = minVal - binWidth;
        const gaussMax = maxVal + binWidth;
        const gaussData = smoothGaussian(values, gaussMin, gaussMax, binWidth);

        const wrap = document.createElement('div');
        wrap.style.cssText = 'position:relative; margin-bottom:20px;';

        const exportBtn = document.createElement('button');
        exportBtn.textContent = 'Exportar PNG';
        exportBtn.className = 'secondary';
        exportBtn.style.cssText = 'position:absolute;top:10px;right:10px;z-index:10;padding:5px 12px;font-size:12px';

        const chartDiv = document.createElement('div');
        chartDiv.style.cssText = 'width:100%;height:400px';

        wrap.appendChild(exportBtn);
        wrap.appendChild(chartDiv);
        container.appendChild(wrap);

        const c = echarts.init(chartDiv);

        const series = [
            {
                name: def.name,
                type: 'bar',
                xAxisIndex: 0,
                data: counts,
                barWidth: '85%',
                barGap: '0%',
                itemStyle: {
                    color: 'rgba(143,170,143,0.88)',
                    borderColor: 'rgba(90,120,90,0.4)',
                    borderWidth: 0.5
                },
                z: 1
            }
        ];

        if (gaussData) {
            series.push({
                name: 'Ajuste gaussiano',
                type: 'line',
                xAxisIndex: 1,   // value axis — 120 fine points
                data: gaussData,
                smooth: false,
                symbol: 'none',
                lineStyle: { color: '#c0392b', width: 2.5 },
                itemStyle: { color: '#c0392b' },
                z: 2
            });
        }

        c.setOption({
            title: {
                text: `${def.name} — Distribución de tamaños`,
                subtext: `n = ${n}    μ = ${mean.toFixed(2)} nm    σ = ${std.toFixed(2)} nm    bin = ${binWidth} nm`,
                left: 'center',
                top: 8,
                subtextStyle: { fontSize: 12, color: '#555' }
            },
            tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
            legend: { bottom: 0, data: [def.name, 'Gaussian fit'] },
            grid: { top: 72, bottom: 48, left: 20, right: 20, containLabel: true },
            xAxis: [
                {
                    type: 'category',
                    data: labels,
                    name: 'Diámetro (nm)',
                    nameLocation: 'middle',
                    nameGap: 30
                },
                {
                    type: 'value',
                    min: gaussMin,
                    max: gaussMax,
                    show: false    // hidden — only used for Gaussian alignment
                }
            ],
            yAxis: {
                type: 'value',
                name: 'Frecuencia',
                nameLocation: 'middle',
                nameGap: 40
            },
            series
        });

        charts.push(c);
        exportBtn.onclick = () => exportChartPng(c, def.name);
    });
}

function formatMeasurement(value) {
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number.toFixed(2) : '';
}

function recalculatePayload() {
    const measurements = currentPayload.measurements;
    const flat = [];
    measurements.forEach(obj => {
        if (obj.inner) flat.push(Object.assign({}, obj.inner));
        if (obj.outer) flat.push(Object.assign({}, obj.outer));
    });
    currentPayload.class_measurements = flat;

    const byClass = {};
    flat.forEach(item => {
        if (!byClass[item.class]) byClass[item.class] = [];
        byClass[item.class].push(item.diameter || 0);
    });
    const newSummary = {};
    Object.entries(byClass).forEach(([cls, vals]) => {
        const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
        newSummary[cls] = {
            count: vals.length,
            mean_diameter: mean,
            min_diameter: Math.min(...vals),
            max_diameter: Math.max(...vals)
        };
    });
    currentPayload.summary = newSummary;

    const paired = measurements.filter(m => m.pair_status === 'paired').length;
    const ready  = measurements.filter(m => m.review_status === 'ready').length;
    const innerAxes = measurements.map(m => m.inner_major_axis).filter(v => v > 0);
    const outerAxes = measurements.map(m => m.outer_major_axis).filter(v => v > 0);
    const avg = arr => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
    currentPayload.object_summary = Object.assign(
        {}, currentPayload.object_summary,
        {
            objects: measurements.length,
            paired,
            ready,
            needs_review: measurements.length - ready,
            mean_inner_major_axis: avg(innerAxes),
            mean_outer_major_axis: avg(outerAxes)
        }
    );
}

function saveMeasurementsJson() {
    if (!currentPayload || !currentPayload.measurements_path) return;
    try {
        fs.writeFileSync(
            currentPayload.measurements_path,
            JSON.stringify(currentPayload.measurements, null, 2)
        );
    } catch (e) {
        console.error('Could not save measurements.json:', e);
    }
}

function exportCsv() {
    if (!currentPayload || !currentPayload.measurements || !currentPayload.measurements.length) {
        alert('No hay mediciones para exportar.');
        return;
    }
    const defaultPath = currentPayload.measurements_path
        ? currentPayload.measurements_path.replace(/\.json$/, '.csv')
        : 'measurements.csv';

    const savePath = dialog.showSaveDialogSync({
        title: 'Export measurements as CSV',
        defaultPath,
        filters: [{ name: 'CSV', extensions: ['csv'] }]
    });
    if (!savePath) return;

    const cols = [
        'object_id', 'review_status', 'pair_status', 'confidence_score',
        'inner_major_axis', 'inner_minor_axis', 'outer_major_axis', 'outer_minor_axis',
        'equivalent_diameter', 'shell_thickness_estimate', 'inner_outer_ratio',
        'center_x', 'center_y', 'flags'
    ];

    const escape = v => {
        if (v === null || v === undefined) return '';
        const s = Array.isArray(v) ? v.join('|') : String(v);
        return s.includes(',') || s.includes('"') || s.includes('\n')
            ? `"${s.replace(/"/g, '""')}"` : s;
    };

    const rows = [cols.join(',')];
    currentPayload.measurements.forEach(m => {
        rows.push(cols.map(c => escape(m[c])).join(','));
    });

    fs.writeFileSync(savePath, rows.join('\n'), 'utf8');
    alert(`Exportadas ${currentPayload.measurements.length} mediciones a:\n${savePath}`);
}

function refreshResults() {
    recalculatePayload();
    saveMeasurementsJson();
    summarizeMeasurements(currentPayload);
    renderMeasurementChart(currentPayload);
    renderMeasurementDetails(currentPayload);
    drawParticleOverlay(null);
}

function setTableSort(col) {
    if (tableSortCol === col) {
        tableSortAsc = !tableSortAsc;
    } else {
        tableSortCol = col;
        tableSortAsc = false; // first click: mayor a menor
    }
    renderMeasurementDetails(currentPayload);
}

function rejectMeasurement(objectId) {
    const obj = currentPayload.measurements.find(m => m.object_id === objectId);
    if (obj) {
        rejectedObjects.set(objectId, {
            center_x:  obj.center_x,
            center_y:  obj.center_y,
            radius_px: obj.inner ? obj.inner.radius_px : 20
        });
    }
    currentPayload.measurements = currentPayload.measurements.filter(m => m.object_id !== objectId);
    editingObjectId = null;
    refreshResults();
}

function startEdit(objectId) {
    editingObjectId = objectId;
    renderMeasurementDetails(currentPayload);
}

function cancelEdit() {
    editingObjectId = null;
    renderMeasurementDetails(currentPayload);
}

function saveEdit(objectId) {
    const obj = currentPayload.measurements.find(m => m.object_id === objectId);
    if (!obj) return;
    const innerVal = parseFloat(document.getElementById('edit-inner-' + objectId).value);
    const outerVal = parseFloat(document.getElementById('edit-outer-' + objectId).value);
    const statusVal = document.getElementById('edit-status-' + objectId).value;
    if (Number.isFinite(innerVal) && innerVal > 0) {
        obj.inner_major_axis = innerVal;
        if (obj.inner) obj.inner.diameter = innerVal;
    }
    if (Number.isFinite(outerVal) && outerVal > 0) {
        obj.outer_major_axis = outerVal;
        if (obj.outer) obj.outer.diameter = outerVal;
    }
    obj.review_status = statusVal;
    editingObjectId = null;
    refreshResults();
}

function renderMeasurementDetails(payload) {
    const objects = payload.measurements || [];
    if (!objects.length) {
        measurementDetails.innerHTML = '';
        return;
    }

    const scaleRows = (payload.scale_candidates || []).slice(0, 4).map((row) => `
        <tr>
            <td>${escapeHtml(row.method)}</td>
            <td>${formatMeasurement(row.width_px)}</td>
            <td>${Number(row.confidence || 0).toFixed(2)}</td>
            <td>${escapeHtml(row.x)}, ${escapeHtml(row.y)}</td>
        </tr>
    `).join('');

    // Sort objects if a column is selected
    const SORT_KEYS = {
        'object_id':              r => r.object_id,
        'review_status':          r => r.review_status,
        'inner_major_axis':       r => Number(r.inner_major_axis) || 0,
        'outer_major_axis':       r => Number(r.outer_major_axis) || 0,
        'shell_thickness_estimate': r => Number(r.shell_thickness_estimate) || 0,
        'confidence_score':       r => Number(r.confidence_score) || 0,
    };
    let sorted = [...objects];
    if (tableSortCol && SORT_KEYS[tableSortCol]) {
        const key = SORT_KEYS[tableSortCol];
        sorted.sort((a, b) => {
            const va = key(a), vb = key(b);
            if (va < vb) return tableSortAsc ? -1 : 1;
            if (va > vb) return tableSortAsc ? 1 : -1;
            return 0;
        });
    }

    const thStyle = 'cursor:pointer;user-select:none;white-space:nowrap';
    const arrow = col => tableSortCol === col ? (tableSortAsc ? ' ▲' : ' ▼') : ' ⇅';
    const thClick = col => `onclick="setTableSort('${col}')"`;

    measurementDetails.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
            <h3 style="margin:0">Revisión de mediciones</h3>
            <button onclick="exportCsv()" class="secondary" style="padding:6px 14px">Exportar CSV</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th style="${thStyle}" ${thClick('object_id')}>Objeto${arrow('object_id')}</th>
                    <th style="${thStyle}" ${thClick('review_status')}>Estado${arrow('review_status')}</th>
                    <th style="${thStyle}" ${thClick('inner_major_axis')}>Eje mayor interno (nm)${arrow('inner_major_axis')}</th>
                    <th style="${thStyle}" ${thClick('outer_major_axis')}>Eje mayor externo (nm)${arrow('outer_major_axis')}</th>
                    <th style="${thStyle}" ${thClick('shell_thickness_estimate')}>Corteza${arrow('shell_thickness_estimate')}</th>
                    <th style="${thStyle}" ${thClick('confidence_score')}>Confianza${arrow('confidence_score')}</th>
                    <th>Indicadores</th>
                    <th>Acciones</th>
                </tr>
            </thead>
            <tbody>
                ${sorted.map((row) => {
                    const isEditing = editingObjectId === row.object_id;
                    const id = escapeHtml(row.object_id);
                    const statusBadge = row.review_status === 'needs_review'
                        ? `<span style="color:#b42318;font-weight:700">revisar</span>`
                        : `<span style="color:#1a7f37;font-weight:700">${escapeHtml(row.review_status)}</span>`;
                    if (isEditing) {
                        return `<tr style="background:#fffbe6">
                            <td>${id}</td>
                            <td>
                                <select id="edit-status-${id}" style="width:130px">
                                    <option value="ready" ${row.review_status === 'ready' ? 'selected' : ''}>listo</option>
                                    <option value="needs_review" ${row.review_status === 'needs_review' ? 'selected' : ''}>revisar</option>
                                </select>
                            </td>
                            <td><input id="edit-inner-${id}" type="number" step="0.01" min="0"
                                value="${Number(row.inner_major_axis || 0).toFixed(3)}"
                                style="width:90px"></td>
                            <td><input id="edit-outer-${id}" type="number" step="0.01" min="0"
                                value="${Number(row.outer_major_axis || 0).toFixed(3)}"
                                style="width:90px"></td>
                            <td>${formatMeasurement(row.shell_thickness_estimate)}</td>
                            <td>${Number(row.confidence_score || 0).toFixed(2)}</td>
                            <td>${escapeHtml((row.flags || []).join(', '))}</td>
                            <td>
                                <button onclick="saveEdit('${id}')" style="margin-right:4px;padding:4px 8px">Guardar</button>
                                <button onclick="cancelEdit()" class="secondary" style="padding:4px 8px">Cancelar</button>
                            </td>
                        </tr>`;
                    }
                    return `<tr>
                        <td>${id}</td>
                        <td>${statusBadge} / ${escapeHtml(row.pair_status)}</td>
                        <td>${formatMeasurement(row.inner_major_axis)}</td>
                        <td>${formatMeasurement(row.outer_major_axis)}</td>
                        <td>${formatMeasurement(row.shell_thickness_estimate)}</td>
                        <td>${Number(row.confidence_score || 0).toFixed(2)}</td>
                        <td>${escapeHtml((row.flags || []).join(', '))}</td>
                        <td>
                            <button onclick="startEdit('${id}')" class="secondary" style="margin-right:4px;padding:4px 8px">Editar</button>
                            <button onclick="rejectMeasurement('${id}')" class="danger" style="padding:4px 8px">Rechazar</button>
                        </td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>
        <h3>Candidatos de escala</h3>
        <table>
            <thead>
                <tr>
                    <th>Método</th>
                    <th>Ancho (px)</th>
                    <th>Confianza</th>
                    <th>Posición</th>
                </tr>
            </thead>
            <tbody>
                ${scaleRows || '<tr><td colspan="4">Sin candidatos. Usa Longitud manual de barra (px).</td></tr>'}
            </tbody>
        </table>
    `;
}

//Clear the input when changing the image
imageInput.addEventListener('change', (event) => {
    if (!event.target.files.length) {
        image = null;
        clearMeasurementResults();
        loadScalePreview(null);
        return;
    }
    const filePath = event.target.files[0].path;
    console.log(filePath);
    image = filePath;
    console.log(`Selected image: ${image}`);
    clearMeasurementResults();
    applyRecommendedSettings(false);
    loadScalePreview(image);
    resolvePreviewSrc(image).then(src => { if (src) img.src = src; });
});

measurementMode.addEventListener('change', updateModeInputState);
shapePreset.addEventListener('change', () => applyRecommendedSettings(true));
recommendedSettingsButton.addEventListener('click', () => applyRecommendedSettings(true));
markScaleLineButton.addEventListener('click', () => {
    if (!scalePreviewImage) {
        alert('Selecciona una imagen primero.');
        return;
    }
    scaleLineMode = true;
    scaleLineDraft = [];
    manualScaleLine = null;
    manualScalePx.value = '';
    updateScaleLineStatus('Click the first end of the printed scale bar.');
    drawScaleCanvas();
});
clearScaleLineButton.addEventListener('click', () => resetManualScaleLine(true));
manualScalePx.addEventListener('input', () => {
    if (manualScaleLine) {
        scaleLineDraft = [];
        manualScaleLine = null;
        drawScaleCanvas();
        updateScaleLineStatus('Usando longitud de barra manual ingresada.');
    }
});
scaleCanvas.addEventListener('click', (event) => {
    if (!scaleLineMode || !scalePreviewImage) {
        return;
    }
    const point = canvasEventToImagePoint(event);
    scaleLineDraft.push(point);
    if (scaleLineDraft.length === 2) {
        manualScaleLine = {
            x1: scaleLineDraft[0].x,
            y1: scaleLineDraft[0].y,
            x2: scaleLineDraft[1].x,
            y2: scaleLineDraft[1].y
        };
        manualScalePx.value = scaleLineLength(manualScaleLine).toFixed(4);
        scaleLineMode = false;
        scaleLineDraft = [];
    }
    updateScaleLineStatus();
    drawScaleCanvas();
});
applyRecommendedSettings(true);
updateModeInputState();
//Sends image processing events to the main process
processButton.addEventListener('click', () => {
    if (!image) {
        alert('Selecciona una imagen primero.');
        return;
    }

    try {
        const mode = measurementMode.value;
        const preset = shapePreset.value;
        const scale = parsePositiveNumber(Scale, 'Scale');
        const histogramBinWidth = parseFloat(Count.value) > 0 ? parseFloat(Count.value) : 5;
        const manualScalePxValue = parseFloat(manualScalePx.value);
        const auMinRadius = mode !== 'sio2' ? parsePositiveNumber(auMinRadiusInput, 'Au min radius') : 1;
        const auMaxRadius = mode !== 'sio2' ? parsePositiveNumber(auMaxRadiusInput, 'Au max radius') : 50;
        const sio2MinRadius = mode !== 'au' ? parsePositiveNumber(sio2MinRadiusInput, 'SiO2 min radius') : 20;
        const sio2MaxRadius = mode !== 'au' ? parsePositiveNumber(sio2MaxRadiusInput, 'SiO2 max radius') : 500;

        if (auMinRadius >= auMaxRadius) {
            throw new Error('Au min radius must be smaller than Au max radius.');
        }
        if (sio2MinRadius >= sio2MaxRadius) {
            throw new Error('SiO2 min radius must be smaller than SiO2 max radius.');
        }

        setProcessing(true);
        measurementSummary.innerHTML = '<div class="metric"><strong>...</strong>Procesando imagen…</div>';
        measurementDetails.innerHTML = '';
        ipcRenderer.send('process-image', {
            image,
            mode,
            shapePreset: preset,
            scale,
            manualScalePx: Number.isFinite(manualScalePxValue) && manualScalePxValue > 0 ? manualScalePxValue : 0,
            manualScaleLine,
            excludeEdges: excludeEdges.checked,
            watershed: watershed.checked,
            auMinRadius,
            auMaxRadius,
            sio2MinRadius,
            sio2MaxRadius,
            histogramBinWidth
        });
    } catch (error) {
        alert(error.message);
    }
});

// Process the results returned by the main process
ipcRenderer.on('image-processed', (event, payload) => {
    const imagePath = payload.imagePath || payload.processed_image_path;
    currentPayload = payload;
    editingObjectId = null;
    rejectedObjects.clear();
    hideParticleMenu();

    // Restore img to a plain state before setting new src
    if (img.parentNode && img.parentNode !== resultDiv) {
        img.parentNode.replaceWith(img);
    }
    img.onload = () => { mountOverlay(); manualMeasureBar.style.display = 'flex'; };
    img.src = imagePath;

    resultDiv.innerHTML = '';
    resultDiv.appendChild(img);

    setProcessing(false);
    summarizeMeasurements(payload);
    renderMeasurementChart(payload);
    renderMeasurementDetails(payload);
});

ipcRenderer.on('image-process-error', (event, payload) => {
    setProcessing(false);
    alert(payload.message || 'Image processing failed.');
});

const tabButtons = document.querySelectorAll('.tab-button');
const panels = document.querySelectorAll('.panel');
const sourceInput = document.getElementById('sourceInput');
const corpusSummary = document.getElementById('corpusSummary');
const corpusLog = document.getElementById('corpusLog');
const corpusProgress = document.getElementById('corpusProgress');
const sourcesTable = document.getElementById('sourcesTable');
const imageList = document.getElementById('imageList');
const corpusPreview = document.getElementById('corpusPreview');
const curationModality = document.getElementById('curationModality');
const curationLicense = document.getElementById('curationLicense');
const curationNotes = document.getElementById('curationNotes');
const scaleNm = document.getElementById('scaleNm');
const scalePx = document.getElementById('scalePx');
const nmPerPx = document.getElementById('nmPerPx');
const metadataBadges = document.getElementById('metadataBadges');
const metaSourceLicenseStatus = document.getElementById('metaSourceLicenseStatus');
const metaQualityStatus = document.getElementById('metaQualityStatus');
const metaScaleStatus = document.getElementById('metaScaleStatus');
const metaFileSha = document.getElementById('metaFileSha');
const metaCaption = document.getElementById('metaCaption');

let corpusState = { sources: [], images: [], summary: {} };
let selectedImage = null;
let selectedSource = null;

function setLog(message, payload) {
    const detail = payload ? `\n${JSON.stringify(payload, null, 2)}` : '';
    corpusLog.textContent = `${new Date().toLocaleTimeString()} - ${message}${detail}`;
}

function sendCorpusCommand(command, args = []) {
    setLog(`Running ${command}...`);
    corpusProgress.style.display = 'block';
    corpusProgress.removeAttribute('value');
    ipcRenderer.send('corpus-command', { command, args });
}

function fileUrl(filePath) {
    if (!filePath) {
        return '';
    }
    const absolutePath = path.isAbsolute(filePath) ? filePath : path.join(__dirname, filePath);
    return `file:///${absolutePath.replace(/\\/g, '/')}`;
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function renderSummary() {
    const summary = corpusState.summary || {};
    const metrics = [
        ['Sources', summary.sources || 0],
        ['Accepted Sources', summary.acceptedSources || 0],
        ['Images', summary.images || 0],
        ['Accepted Images', summary.acceptedImages || 0],
        ['Needs Review', summary.needsReview || 0],
        ['Calibrated', summary.calibrated || 0],
        ['Metadata Ready', summary.metadataReadyImages || 0],
        ['Missing SHA', summary.imagesMissingChecksum || 0],
    ];
    corpusSummary.innerHTML = metrics.map(([label, value]) => (
        `<div class="metric"><strong>${value}</strong>${label}</div>`
    )).join('');
}

function renderSources() {
    if (!corpusState.sources.length) {
        sourcesTable.innerHTML = '<p>No sources validated yet.</p>';
        return;
    }

    sourcesTable.innerHTML = `
        <table>
            <thead>
                <tr>
                    <th>Decision</th>
                    <th>Domain</th>
                    <th>License</th>
                    <th>Modality</th>
                    <th>Reason</th>
                    <th>URL</th>
                </tr>
            </thead>
            <tbody>
                ${corpusState.sources.map((row) => `
                    <tr>
                        <td>${escapeHtml(row.decision)}</td>
                        <td>${escapeHtml(row.domain)}</td>
                        <td>${escapeHtml(row.license)}</td>
                        <td>${escapeHtml(row.modality)}</td>
                        <td>${escapeHtml(row.reason)}</td>
                        <td>${escapeHtml(row.url)}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function selectImage(imageId) {
    selectedImage = corpusState.images.find((imageRow) => imageRow.image_id === imageId) || null;
    selectedSource = selectedImage ? corpusState.sources.find((sourceRow) => sourceRow.source_id === selectedImage.source_id) || null : null;
    renderImages();
    if (!selectedImage) {
        corpusPreview.removeAttribute('src');
        renderMetadata();
        return;
    }
    corpusPreview.src = fileUrl(selectedImage.file_path);
    curationModality.value = selectedImage.modality || '';
    curationLicense.value = selectedImage.license || '';
    curationNotes.value = selectedImage.notes || '';
    scaleNm.value = selectedImage.scale_nm || '';
    scalePx.value = selectedImage.scale_px || '';
    nmPerPx.value = selectedImage.nm_per_px || '';
    renderMetadata();
}

function renderImages() {
    if (!corpusState.images.length) {
        imageList.innerHTML = '<p style="padding: 10px;">No extracted images yet.</p>';
        return;
    }

    imageList.innerHTML = corpusState.images.map((imageRow) => {
        const active = selectedImage && selectedImage.image_id === imageRow.image_id ? ' active' : '';
        return `
            <button class="image-item${active}" data-image-id="${escapeHtml(imageRow.image_id)}">
                <strong>${escapeHtml(imageRow.curation_status || 'needs_review')}</strong><br>
                ${escapeHtml(imageRow.image_id)}<br>
                ${escapeHtml(imageRow.modality)} | ${escapeHtml(imageRow.nm_per_px ? `${imageRow.nm_per_px} nm/px` : 'no scale')}
            </button>
        `;
    }).join('');

    imageList.querySelectorAll('.image-item').forEach((button) => {
        button.addEventListener('click', () => selectImage(button.dataset.imageId));
    });
}

function badge(label, type) {
    return `<span class="badge ${type || ''}">${escapeHtml(label)}</span>`;
}

function renderMetadata() {
    const imageRow = selectedImage || {};
    const source = selectedSource || {};
    metaSourceLicenseStatus.value = source.license_status || '';
    metaQualityStatus.value = imageRow.quality_status || '';
    metaScaleStatus.value = imageRow.scale_status || '';
    metaFileSha.value = imageRow.file_sha256 || '';
    metaCaption.value = imageRow.caption || '';

    const badges = [];
    if (!imageRow.image_id) {
        badges.push(badge('Select an image', 'warning'));
    }
    if (source.license_status === 'accepted') {
        badges.push(badge('Ready License', 'ready'));
    } else if (source.license_status === 'rejected_for_public_corpus') {
        badges.push(badge('License Blocked', 'blocked'));
    } else {
        badges.push(badge('License Missing', 'warning'));
    }
    if (imageRow.metadata_status === 'ready') {
        badges.push(badge('Ready', 'ready'));
    } else if (imageRow.metadata_status === 'blocked') {
        badges.push(badge('Blocked', 'blocked'));
    } else {
        badges.push(badge('Needs Review', 'warning'));
    }
    if (imageRow.image_id && !imageRow.nm_per_px) {
        badges.push(badge('Missing Scale', 'warning'));
    }
    if (imageRow.image_id && !imageRow.file_sha256) {
        badges.push(badge('Missing SHA256', 'warning'));
    }
    metadataBadges.innerHTML = badges.join('');
}

function renderCorpusState() {
    renderSummary();
    renderSources();
    renderImages();
    if (selectedImage) {
        selectedImage = corpusState.images.find((imageRow) => imageRow.image_id === selectedImage.image_id) || null;
        selectedSource = selectedImage ? corpusState.sources.find((sourceRow) => sourceRow.source_id === selectedImage.source_id) || null : selectedSource;
    }
    renderMetadata();
}

function updateCalibrationPreview() {
    const scaleNmValue = parseFloat(scaleNm.value);
    const scalePxValue = parseFloat(scalePx.value);
    if (scaleNmValue > 0 && scalePxValue > 0) {
        nmPerPx.value = (scaleNmValue / scalePxValue).toPrecision(8);
    } else {
        nmPerPx.value = '';
    }
}

tabButtons.forEach((button) => {
    button.addEventListener('click', () => {
        tabButtons.forEach((item) => item.classList.remove('active'));
        panels.forEach((panel) => panel.classList.remove('active'));
        button.classList.add('active');
        document.getElementById(button.dataset.tab).classList.add('active');
        if (button.dataset.tab === 'corpusPanel') {
            sendCorpusCommand('status');
        }
    });
});

document.getElementById('validateSourcesButton').addEventListener('click', () => {
    sendCorpusCommand('searchSources', ['--sources', sourceInput.value]);
});

document.getElementById('refreshCorpusButton').addEventListener('click', () => {
    sendCorpusCommand('status');
});

document.getElementById('downloadAcceptedButton').addEventListener('click', () => {
    sendCorpusCommand('downloadSources');
});

document.getElementById('extractFiguresButton').addEventListener('click', () => {
    sendCorpusCommand('extractFigures');
});

function updateCuration(status) {
    if (!selectedImage) {
        setLog('Select an image first.');
        return;
    }
    sendCorpusCommand('curateImage', [
        '--image-id', selectedImage.image_id,
        '--status', status,
        '--modality', curationModality.value,
        '--license', curationLicense.value,
        '--notes', curationNotes.value,
    ]);
}

document.getElementById('acceptImageButton').addEventListener('click', () => updateCuration('accepted'));
document.getElementById('reviewImageButton').addEventListener('click', () => updateCuration('needs_review'));
document.getElementById('rejectImageButton').addEventListener('click', () => updateCuration('rejected'));

scaleNm.addEventListener('input', updateCalibrationPreview);
scalePx.addEventListener('input', updateCalibrationPreview);

document.getElementById('saveCalibrationButton').addEventListener('click', () => {
    if (!selectedImage) {
        setLog('Select an image first.');
        return;
    }
    sendCorpusCommand('calibrateImage', [
        '--image-id', selectedImage.image_id,
        '--scale-nm', scaleNm.value,
        '--scale-px', scalePx.value,
        '--method', 'manual',
    ]);
});

document.getElementById('enrichMetadataButton').addEventListener('click', () => {
    const args = ['enrich-source'];
    if (selectedSource) {
        args.push('--source-id', selectedSource.source_id);
    }
    sendCorpusCommand('metadata', args);
});

document.getElementById('saveMetadataButton').addEventListener('click', () => {
    if (selectedSource) {
        sendCorpusCommand('metadata', [
            'update-source',
            '--source-id', selectedSource.source_id,
            '--metadata-json', JSON.stringify({ license_status: metaSourceLicenseStatus.value }),
        ]);
    }
    if (selectedImage) {
        sendCorpusCommand('metadata', [
            'update-image',
            '--image-id', selectedImage.image_id,
            '--metadata-json', JSON.stringify({
                caption: metaCaption.value,
                quality_status: metaQualityStatus.value,
                scale_status: metaScaleStatus.value,
            }),
        ]);
    }
    if (!selectedSource && !selectedImage) {
        setLog('Select an image first.');
    }
});

document.getElementById('validateMetadataButton').addEventListener('click', () => {
    sendCorpusCommand('metadata', ['validate-metadata']);
});

document.getElementById('hashImagesButton').addEventListener('click', () => {
    sendCorpusCommand('metadata', ['hash-images']);
});

document.getElementById('exportCocoButton').addEventListener('click', () => {
    sendCorpusCommand('exportDataset', ['--coco']);
});

document.getElementById('exportYoloButton').addEventListener('click', () => {
    sendCorpusCommand('exportDataset', ['--yolo']);
});

document.getElementById('auditButton').addEventListener('click', () => {
    sendCorpusCommand('exportDataset', ['--audit']);
});

ipcRenderer.on('corpus-result', (event, result) => {
    corpusProgress.style.display = 'none';
    corpusProgress.value = 0;
    setLog(result.message || 'Corpus command finished.', result.ok === false ? result : null);
    if (result.command === 'status' && result.ok) {
        corpusState = result;
        if (selectedImage) {
            const selectedId = selectedImage.image_id;
            selectedImage = corpusState.images.find((imageRow) => imageRow.image_id === selectedId) || null;
        }
        renderCorpusState();
        return;
    }

    if (result.ok !== false) {
        sendCorpusCommand('status');
    }
});

