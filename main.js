const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const corpusScripts = {
  status: 'status.py',
  searchSources: 'search_sources.py',
  downloadSources: 'download_sources.py',
  extractFigures: 'extract_figures.py',
  curateImage: 'curate_images.py',
  calibrateImage: 'calibrate_images.py',
  exportDataset: 'export_dataset.py',
  metadata: 'metadata.py'
};

function pythonCandidates() {
  return [
    process.env.PYTHON ? { command: process.env.PYTHON, args: [] } : null,
    { command: 'python3', args: [] },
    { command: 'python', args: [] },
    { command: 'py', args: ['-3'] }
  ].filter(Boolean);
}

function runPythonRaw(script, args = []) {
  return new Promise((resolve) => {
    const scriptPath = path.isAbsolute(script) ? script : path.join(__dirname, script);
    const candidates = pythonCandidates();
    let index = 0;

    function tryNext(lastError = '') {
      if (index >= candidates.length) {
        resolve({ code: -1, stdout: '', stderr: lastError || 'No Python executable could be started.' });
        return;
      }

      const candidate = candidates[index];
      index += 1;
      const pythonProcess = spawn(candidate.command, [...candidate.args, scriptPath, ...args], { cwd: __dirname });
      let stdout = '';
      let stderr = '';
      let failedToStart = false;

      pythonProcess.stdout.on('data', (data) => {
        stdout += data.toString();
      });

      pythonProcess.stderr.on('data', (data) => {
        stderr += data.toString();
      });

      pythonProcess.on('error', (error) => {
        failedToStart = true;
        tryNext(error.message);
      });

      pythonProcess.on('close', (code) => {
        if (failedToStart) {
          return;
        }
        resolve({ code, stdout, stderr });
      });
    }

    tryNext();
  });
}

async function runPython(script, args = []) {
  const result = await runPythonRaw(script, args);
  let payload = null;
  try {
    payload = JSON.parse(result.stdout.trim() || '{}');
  } catch (error) {
    payload = {
      ok: false,
      message: 'Python script returned invalid JSON.',
      stdout: result.stdout,
      stderr: result.stderr || error.message
    };
  }

  if (result.code !== 0) {
    payload.ok = false;
    payload.message = payload.message || `Python process exited with code ${result.code}`;
    payload.stderr = result.stderr;
  }

  return payload;
}
//Initialize the window
function createWindow() {
  const win = new BrowserWindow({
    width: 1500,
    height: 1200,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: true
    },
  });
  require('@electron/remote/main').initialize()  
  require('@electron/remote/main').enable(win.webContents)  
  win.loadFile('index.html');
  win.webContents.openDevTools({ mode: 'bottom' });
}
app.whenReady().then(createWindow);
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// Process the image
ipcMain.on('process-image', async (event, {
  image,
  mode,
  shapePreset,
  scale,
  manualScalePx,
  manualScaleLine,
  excludeEdges,
  watershed,
  auMinRadius,
  auMaxRadius,
  sio2MinRadius,
  sio2MaxRadius,
  histogramBinWidth,
  minRadius,
  maxRadius
}) => {
  const effectiveMode = mode || 'au';
  const effectiveAuMin = auMinRadius || minRadius || 1;
  const effectiveAuMax = auMaxRadius || maxRadius || 50;
  const effectiveSio2Min = sio2MinRadius || minRadius || 20;
  const effectiveSio2Max = sio2MaxRadius || maxRadius || 500;
  const args = [
    '--image', image,
    '--mode', effectiveMode,
    '--shape-preset', shapePreset || 'generic',
    '--scale', scale,
    '--manual-scale-px', manualScalePx || 0,
    '--exclude-edges', excludeEdges === false ? 'false' : 'true',
    '--watershed', watershed === false ? 'false' : 'true',
    '--au-min-radius', effectiveAuMin,
    '--au-max-radius', effectiveAuMax,
    '--sio2-min-radius', effectiveSio2Min,
    '--sio2-max-radius', effectiveSio2Max,
    '--histogram-bin-width', histogramBinWidth || 5
  ];
  if (manualScaleLine) {
    args.push(
      '--manual-scale-line',
      [
        manualScaleLine.x1,
        manualScaleLine.y1,
        manualScaleLine.x2,
        manualScaleLine.y2
      ].join(',')
    );
  }
  const result = await runPython('measurement_modes.py', args);

  if (result.ok) {
    event.sender.send('image-processed', {
      imagePath: result.processed_image_path,
      ...result
    });
  } else {
    event.sender.send('image-process-error', result);
    console.error(`Python Error: ${result.stderr || result.message}`);
  }
});

ipcMain.on('corpus-command', async (event, { command, args }) => {
  const script = corpusScripts[command];
  if (!script) {
    event.sender.send('corpus-result', {
      command,
      ok: false,
      message: `Unknown corpus command: ${command}`
    });
    return;
  }

  const result = await runPython(path.join('corpus_pipeline', script), args || []);
  event.sender.send('corpus-result', { command, ...result });
});

ipcMain.handle('image-to-preview', async (_event, { imagePath }) => {
  return await runPython('preview_image.py', [imagePath]);
});
