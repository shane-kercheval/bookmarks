// Builds the loadable extension artifact for one environment: build/<mode>/.
//
// The build output — not the source tree — is what Chrome loads and what the
// store zip ships. The manifest is generated per mode because host_permissions
// differ between environments, and development values (the Clerk dev
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
// genuinely differ per environment (the Clerk dev instance's key/domain, and
// the production publishable key — public, but env-supplied by decision).
import { build } from 'esbuild';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));

// Canonical production origins — public facts, committed and pinned.
const CANONICAL = {
  TIDDLY_API_URL: 'https://api.tiddly.me',
  CLERK_SYNC_HOST: 'https://clerk.tiddly.me',
  CLERK_FRONTEND_API: 'https://clerk.tiddly.me',
};

const DEFAULTS = {
  development: {
    TIDDLY_API_URL: 'http://localhost:8000',
    // Clerk's documented Sync Host special case for development — do NOT
    // "correct" it to the dev instance's .accounts.dev domain (plan M7 step 1).
    CLERK_SYNC_HOST: 'http://localhost',
    // CLERK_PUBLISHABLE_KEY / CLERK_FRONTEND_API: dev-instance values, required
    // from the env file — never committed (no-env-identifiers rule).
  },
  production: { ...CANONICAL },
  // CLERK_PUBLISHABLE_KEY (production): public by design but env-supplied —
  // required from .env.production.local.
};

const REQUIRED_FROM_ENV = {
  development: ['CLERK_PUBLISHABLE_KEY', 'CLERK_FRONTEND_API'],
  production: ['CLERK_PUBLISHABLE_KEY'],
};

const ORIGIN_KEYS = ['TIDDLY_API_URL', 'CLERK_SYNC_HOST', 'CLERK_FRONTEND_API'];
const KNOWN_KEYS = new Set([...ORIGIN_KEYS, 'CLERK_PUBLISHABLE_KEY']);
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

// Validates an origin-valued variable and returns the normalized form
// (a lone trailing slash is normalized away; anything more is rejected).
function normalizeOrigin(name, value, mode) {
  let url;
  try {
    url = new URL(value);
  } catch {
    fail(`${name} is not a valid URL: "${value}"`);
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    fail(`${name} must be http(s), got "${url.protocol}"`);
  }
  if (url.username || url.password) fail(`${name} must not contain credentials`);
  if (url.search || url.hash) fail(`${name} must not contain a query or fragment`);
  if (url.pathname !== '/') fail(`${name} must be a bare origin, got path "${url.pathname}"`);
  if (mode === 'production' && url.origin !== CANONICAL[name]) {
    fail(`production ${name} is pinned to ${CANONICAL[name]} (got "${url.origin}") — add a distinct build mode instead of overriding production`);
  }
  if (mode === 'development' && url.protocol === 'http:' && !LOOPBACK_HOSTS.has(url.hostname)) {
    fail(`http is allowed only for loopback hosts in development, got "${url.hostname}" — use https for remote origins`);
  }
  return url.origin;
}

// Clerk publishable keys are documented as base64("<frontend-api>$") behind a
// pk_test_/pk_live_ prefix. Validating structure AND that the encoded domain
// matches CLERK_FRONTEND_API catches truncated keys and keys copied from the
// wrong instance at build time — otherwise the artifact builds green and
// session sync silently fails at runtime (masked for PAT users). Strict on
// purpose: Node's base64 decoder is lenient, so round-trip to verify.
function validatePublishableKey(value, mode, frontendApi) {
  const prefix = mode === 'production' ? 'pk_live_' : 'pk_test_';
  if (!value.startsWith(prefix)) {
    fail(`CLERK_PUBLISHABLE_KEY for ${mode} must start with "${prefix}"`);
  }
  const encoded = value.slice(prefix.length);
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(encoded)) {
    fail('CLERK_PUBLISHABLE_KEY payload is not valid base64');
  }
  const decoded = Buffer.from(encoded, 'base64').toString('utf-8');
  const reencoded = Buffer.from(decoded, 'utf-8').toString('base64').replace(/=+$/, '');
  if (reencoded !== encoded.replace(/=+$/, '')) {
    fail('CLERK_PUBLISHABLE_KEY payload is not valid base64 (round-trip mismatch)');
  }
  if (!decoded.endsWith('$') || decoded.indexOf('$') !== decoded.length - 1) {
    fail('CLERK_PUBLISHABLE_KEY must decode to "<frontend-api>$" (exactly one terminal $)');
  }
  const host = decoded.slice(0, -1);
  if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/i.test(host)) {
    fail(`CLERK_PUBLISHABLE_KEY does not decode to a hostname (got "${host}")`);
  }
  const expected = new URL(frontendApi).hostname;
  if (host !== expected) {
    fail(`CLERK_PUBLISHABLE_KEY decodes to "${host}" but CLERK_FRONTEND_API is "${expected}" — key/instance mismatch`);
  }
  return value;
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

  const missing = REQUIRED_FROM_ENV[mode].filter((key) => !(key in config));
  if (missing.length) {
    fail(`missing required value(s) for ${mode}: ${missing.join(', ')} — supply via .env.${mode}.local or --env-file (see .env.template)`);
  }
  for (const key of ORIGIN_KEYS) {
    config[key] = normalizeOrigin(key, config[key], mode);
  }
  config.CLERK_PUBLISHABLE_KEY = validatePublishableKey(
    config.CLERK_PUBLISHABLE_KEY, mode, config.CLERK_FRONTEND_API,
  );
  return config;
}

function generateManifest(config) {
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'manifest.base.json'), 'utf-8'));
  // API + sync host + Clerk Frontend API; deduped (in production the sync host
  // and the FAPI are the same origin; in development the portless API and sync
  // host both become http://localhost/*). Match patterns are scheme+hostname
  // only — Chrome's documented localhost pattern is portless ("matches any
  // localhost port"); the port stays in the injected runtime URL.
  manifest.host_permissions = [...new Set(
    [config.TIDDLY_API_URL, config.CLERK_SYNC_HOST, config.CLERK_FRONTEND_API]
      .map((origin) => {
        const url = new URL(origin);
        return `${url.protocol}//${url.hostname}/*`;
      }),
  )];
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
    // The bundled Clerk SDK is ~6 MB unminified; ship production minified
    // (string literals — the packaging test's assertions — are unaffected).
    minify: mode === 'production',
    outfile: path.join(outDir, 'background.js'),
    define: {
      __TIDDLY_API_URL__: JSON.stringify(config.TIDDLY_API_URL),
      __TIDDLY_CLERK_PUBLISHABLE_KEY__: JSON.stringify(config.CLERK_PUBLISHABLE_KEY),
      __TIDDLY_CLERK_SYNC_HOST__: JSON.stringify(config.CLERK_SYNC_HOST),
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

  console.log(`Built ${mode} → build/${mode}/ (API: ${config.TIDDLY_API_URL}, syncHost: ${config.CLERK_SYNC_HOST})`);
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
