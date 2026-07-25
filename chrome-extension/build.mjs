// Builds the loadable extension artifact for one environment: build/<mode>/.
//
// The build output — not the source tree — is what Chrome loads and what the
// store zip ships. The manifest is generated per mode because host_permissions
// differ between environments, and development values (later: the Clerk dev
// instance's domain/key) must never live in a committed file.
//
// Usage: node build.mjs <development|production> [--env-file <path> | --no-env-file] [--build-root <path>]
//   (default env source: .env.<mode>.local if present — see .env.template;
//    default build root: ./build — tests pass a temp root so they never
//    overwrite an artifact a developer has loaded unpacked in Chrome)
//
// Config rules (review round 2026-07-24): env parsing is strict and fails fast
// (unknown/duplicate/empty keys, malformed lines, quoted values), and values
// that are canonical-and-public in production are PINNED, not overridable — a
// stale or typo'd .env.production.local must fail the build, never ship an
// artifact pointing at the wrong server. Env injection exists for values that
// genuinely differ per environment (later: the Clerk dev instance's key).
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));

const DEFAULTS = {
  development: { TIDDLY_API_URL: 'http://localhost:8000' },
  production: { TIDDLY_API_URL: 'https://api.tiddly.me' },
};

const KNOWN_KEYS = new Set(['TIDDLY_API_URL']);
// URL-parsed IPv6 hostnames keep their brackets, so only the bracketed form
// can ever match here.
const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

// Files copied verbatim: popup/options run unbundled (relative ESM imports,
// which Chrome resolves natively — only the background needs bundling because
// of bare npm imports).
const STATIC_FILES = [
  'popup.html', 'popup.js', 'popup-core.js', 'popup.css',
  'options.html', 'options.js', 'options.css',
];

function fail(message) {
  console.error(`build.mjs: ${message}`);
  process.exit(1);
}

function parseEnvFile(envPath) {
  const values = {};
  const lines = fs.readFileSync(envPath, 'utf-8').split('\n');
  for (const [index, line] of lines.entries()) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq === -1) fail(`${envPath}:${index + 1}: not KEY=VALUE: "${trimmed}"`);
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1).trim();
    if (!key) fail(`${envPath}:${index + 1}: empty key`);
    if (!KNOWN_KEYS.has(key)) fail(`${envPath}:${index + 1}: unknown key "${key}" (known: ${[...KNOWN_KEYS].join(', ')})`);
    if (key in values) fail(`${envPath}:${index + 1}: duplicate key "${key}"`);
    if (!value) fail(`${envPath}:${index + 1}: empty value for "${key}"`);
    if (/^["']|["']$/.test(value)) fail(`${envPath}:${index + 1}: quotes are not supported — use a bare value`);
    values[key] = value;
  }
  return values;
}

// Validates TIDDLY_API_URL as a bare origin and returns the normalized form
// (a lone trailing slash is normalized away; anything more is rejected).
function normalizeApiUrl(value, mode) {
  let url;
  try {
    url = new URL(value);
  } catch {
    fail(`TIDDLY_API_URL is not a valid URL: "${value}"`);
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    fail(`TIDDLY_API_URL must be http(s), got "${url.protocol}"`);
  }
  if (url.username || url.password) fail('TIDDLY_API_URL must not contain credentials');
  if (url.search || url.hash) fail('TIDDLY_API_URL must not contain a query or fragment');
  if (url.pathname !== '/') fail(`TIDDLY_API_URL must be a bare origin, got path "${url.pathname}"`);
  if (mode === 'production' && url.origin !== DEFAULTS.production.TIDDLY_API_URL) {
    fail(`production TIDDLY_API_URL is pinned to ${DEFAULTS.production.TIDDLY_API_URL} (got "${url.origin}") — add a distinct build mode instead of overriding production`);
  }
  if (mode === 'development' && url.protocol === 'http:' && !LOOPBACK_HOSTS.has(url.hostname)) {
    fail(`http is allowed only for loopback hosts in development, got "${url.hostname}" — use https for remote origins`);
  }
  return url.origin;
}

function resolveConfig(mode, { envFile, noEnvFile }) {
  let overrides = {};
  if (envFile) {
    if (!fs.existsSync(envFile)) fail(`--env-file not found: ${envFile}`);
    overrides = parseEnvFile(envFile);
  } else if (!noEnvFile) {
    const defaultPath = path.join(ROOT, `.env.${mode}.local`);
    if (fs.existsSync(defaultPath)) overrides = parseEnvFile(defaultPath);
  }
  const config = { ...DEFAULTS[mode], ...overrides };
  config.TIDDLY_API_URL = normalizeApiUrl(config.TIDDLY_API_URL, mode);
  return config;
}

function generateManifest(config) {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.base.json'), 'utf-8'));
  manifest.host_permissions = [`${config.TIDDLY_API_URL}/*`];
  return manifest;
}

export async function buildExtension(mode, options = {}) {
  if (!DEFAULTS[mode]) fail(`unknown mode "${mode}" (expected development or production)`);
  const config = resolveConfig(mode, options);
  const buildRoot = path.resolve(options.buildRoot ?? path.join(ROOT, 'build'));
  const outDir = path.join(buildRoot, mode);

  fs.rmSync(outDir, { recursive: true, force: true });
  fs.mkdirSync(outDir, { recursive: true });

  // format: 'esm' is paired with the manifest's "type": "module" — change both
  // or neither (an ESM worker declaration must load a module-valid file).
  await build({
    entryPoints: [path.join(ROOT, 'background.js')],
    bundle: true,
    format: 'esm',
    outfile: path.join(outDir, 'background.js'),
    define: {
      __TIDDLY_API_URL__: JSON.stringify(config.TIDDLY_API_URL),
    },
  });

  for (const file of STATIC_FILES) {
    fs.copyFileSync(path.join(ROOT, file), path.join(outDir, file));
  }
  fs.cpSync(path.join(ROOT, 'icons'), path.join(outDir, 'icons'), { recursive: true });

  fs.writeFileSync(
    path.join(outDir, 'manifest.json'),
    JSON.stringify(generateManifest(config), null, 2) + '\n',
  );

  console.log(`Built ${mode} → build/${mode}/ (API: ${config.TIDDLY_API_URL})`);
  return config;
}

function parseArgs(argv) {
  const [mode, ...rest] = argv;
  const options = { envFile: undefined, noEnvFile: false, buildRoot: undefined };
  for (let i = 0; i < rest.length; i++) {
    if (rest[i] === '--env-file') {
      options.envFile = rest[++i];
      if (!options.envFile) fail('--env-file requires a path');
    } else if (rest[i] === '--no-env-file') {
      options.noEnvFile = true;
    } else if (rest[i] === '--build-root') {
      options.buildRoot = rest[++i];
      if (!options.buildRoot) fail('--build-root requires a path');
    } else {
      fail(`unknown argument: ${rest[i]}`);
    }
  }
  if (options.envFile && options.noEnvFile) fail('--env-file and --no-env-file are mutually exclusive');
  return { mode, options };
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const { mode, options } = parseArgs(process.argv.slice(2));
  if (!mode) fail('Usage: node build.mjs <development|production> [--env-file <path> | --no-env-file] [--build-root <path>]');
  await buildExtension(mode, options);
}
