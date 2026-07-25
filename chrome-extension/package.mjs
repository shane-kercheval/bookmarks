// Packages the production build for the Chrome Web Store.
//
// Always performs a clean production build first, zips ONLY build/production/,
// and replaces the destination atomically via a unique temp archive — plain
// `zip -r` into an existing archive updates entries but never removes stale
// ones, which is exactly the stale-package failure this pipeline exists to
// eliminate (caught in review, 2026-07-24).
//
// Usage: node package.mjs [--env-file <path> | --no-env-file] [--output <path>] [--build-root <path>]
//   default output: ../dist/chrome-extension.zip (repo-root dist/)
//   default build root: ./build (tests pass a temp root; the zip source is
//   always <build-root>/production, the tree this run just built)
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { buildExtension } from './build.mjs';

const ROOT = path.dirname(fileURLToPath(import.meta.url));

function fail(message) {
  console.error(`package.mjs: ${message}`);
  process.exit(1);
}

const options = { envFile: undefined, noEnvFile: false, buildRoot: undefined };
let output = path.join(ROOT, '..', 'dist', 'chrome-extension.zip');
const args = process.argv.slice(2);
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--env-file') {
    options.envFile = args[++i];
    if (!options.envFile) fail('--env-file requires a path');
  } else if (args[i] === '--no-env-file') {
    options.noEnvFile = true;
  } else if (args[i] === '--output') {
    output = args[++i];
    if (!output) fail('--output requires a path');
  } else if (args[i] === '--build-root') {
    options.buildRoot = args[++i];
    if (!options.buildRoot) fail('--build-root requires a path');
  } else {
    fail(`unknown argument: ${args[i]}`);
  }
}
if (options.envFile && options.noEnvFile) fail('--env-file and --no-env-file are mutually exclusive');

const buildRoot = path.resolve(options.buildRoot ?? path.join(ROOT, 'build'));
await buildExtension('production', options);

output = path.resolve(output);
fs.mkdirSync(path.dirname(output), { recursive: true });
const tmp = `${output}.${process.pid}.tmp`;
fs.rmSync(tmp, { force: true });
try {
  const result = spawnSync('zip', ['-r', tmp, '.', '-x', '*.DS_Store'], {
    cwd: path.join(buildRoot, 'production'),
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`zip exited with status ${result.status}`);
  fs.renameSync(tmp, output);
} catch (err) {
  fs.rmSync(tmp, { force: true });
  fail(err.message);
}
console.log(`Packaged → ${output}`);
