const { spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

function bundledPythonCandidates() {
  const home = os.homedir();
  const paths = [
    path.join(home, '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe'),
    path.join(home, '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'bin', 'python3'),
    path.join(home, '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'bin', 'python'),
  ];
  return paths
    .filter((candidatePath) => fs.existsSync(candidatePath))
    .map((candidatePath) => ({ command: candidatePath, args: [] }));
}

function candidates() {
  return [
    process.env.PYTHON ? { command: process.env.PYTHON, args: [] } : null,
    ...bundledPythonCandidates(),
    { command: 'python', args: [] },
    { command: 'python3', args: [] },
    { command: 'py', args: ['-3'] },
  ].filter(Boolean);
}

function recoverableAlias(stdout, stderr) {
  const text = `${stdout || ''}\n${stderr || ''}`.toLowerCase();
  return text.includes('python was not found') ||
    text.includes('microsoft store') ||
    text.includes('app execution aliases');
}

const scriptArgs = process.argv.slice(2);
if (!scriptArgs.length) {
  console.error('Usage: node training/run_python.js <script.py> [args...]');
  process.exit(2);
}

let last = null;
for (const candidate of candidates()) {
  const result = spawnSync(candidate.command, [...candidate.args, ...scriptArgs], {
    stdio: ['inherit', 'pipe', 'pipe'],
    shell: false,
  });
  last = result;
  const stdout = result.stdout ? result.stdout.toString() : '';
  const stderr = result.stderr ? result.stderr.toString() : '';
  if (result.error) {
    continue;
  }
  process.stdout.write(stdout);
  process.stderr.write(stderr);
  if (result.status === 0) {
    process.exit(0);
  }
  if (recoverableAlias(stdout, stderr)) {
    continue;
  }
  process.exit(result.status || 1);
}

if (last && last.error) {
  console.error(last.error.message);
}
console.error('No working Python executable found. Set PYTHON to your Python executable path.');
process.exit(1);
