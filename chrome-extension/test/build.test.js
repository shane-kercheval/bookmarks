// Packaging assertions for the generated build artifacts (the plan's targeted
// checks — exact host sets and injected values, not blanket string scans that
// would false-positive on vendor SDK internals in the bundled worker).
//
// Hermetic in BOTH directions (review rounds 2026-07-24): every build passes
// an explicit fixture env file or --no-env-file (a developer's .env.*.local
// can never change what these tests assert — the committed fixtures under
// test/fixtures/ carry fake, syntactically valid Clerk values), and every
// build writes into one temporary workspace via --build-root (the tests can
// never overwrite the repo's build/<mode>/ — the artifact a developer may
// have loaded unpacked in Chrome).
import { execSync, spawnSync } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');

const FIXTURES = {
  development: path.join(ROOT, 'test', 'fixtures', 'development.env'),
};
// The production key must decode to the pinned canonical FAPI domain, so a
// passing test key IS the (public, derivable) production key. It is derived
// here at runtime from the committed domain rather than committed as a
// literal — preserving the "production key is env-supplied, not committed"
// convention in the tracked tree.
const PROD_KEY = 'pk_live_' + Buffer.from('clerk.tiddly.me$').toString('base64');
const PROD_REQUIRED = `CLERK_PUBLISHABLE_KEY=${PROD_KEY}\n`;
// Prepended to inline validation fixtures so the failure under test is the
// one being asserted, not a missing-required-value failure.
const DEV_REQUIRED =
  'CLERK_PUBLISHABLE_KEY=pk_test_ZmFrZS1pbnN0YW5jZS5jbGVyay5hY2NvdW50cy5kZXYk\n' +
  'CLERK_FRONTEND_API=https://fake-instance.clerk.accounts.dev\n';

let WORKSPACE;

const EXPECTED_FILES = [
  'background.js',
  'cache-ownership.js',
  'icons',
  'manifest.json',
  'options.css',
  'options.html',
  'options.js',
  'popup-core.js',
  'popup.css',
  'popup.html',
  'popup.js',
].sort();

function buildMode(mode, extraArgs) {
  return spawnSync('node', ['build.mjs', mode, '--build-root', WORKSPACE, ...extraArgs], {
    cwd: ROOT,
    encoding: 'utf-8',
  });
}

function buildWithEnv(mode, envContent) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tiddly-ext-env-'));
  const envPath = path.join(dir, 'build.env');
  fs.writeFileSync(envPath, envContent);
  const result = buildMode(mode, ['--env-file', envPath]);
  fs.rmSync(dir, { recursive: true, force: true });
  return result;
}

function readManifest(mode) {
  return JSON.parse(
    fs.readFileSync(path.join(WORKSPACE, mode, 'manifest.json'), 'utf-8'),
  );
}

function readWorker(mode) {
  return fs.readFileSync(path.join(WORKSPACE, mode, 'background.js'), 'utf-8');
}

// Recursive file inventory (files only, POSIX-relative paths) — the shape the
// zip's entry list is compared against.
function listFilesRecursive(dir, base = dir) {
  const entries = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      entries.push(...listFilesRecursive(full, base));
    } else {
      entries.push(path.relative(base, full).split(path.sep).join('/'));
    }
  }
  return entries.sort();
}

beforeAll(() => {
  WORKSPACE = fs.mkdtempSync(path.join(os.tmpdir(), 'tiddly-ext-build-'));
  const dev = buildMode('development', ['--env-file', FIXTURES.development]);
  if (dev.status !== 0) throw new Error(`workspace build failed for development:\n${dev.stderr}`);
  const prod = buildWithEnv('production', PROD_REQUIRED);
  if (prod.status !== 0) throw new Error(`workspace build failed for production:\n${prod.stderr}`);
}, 60_000);

afterAll(() => {
  // Runs even after failed assertions — the workspace never outlives the suite.
  fs.rmSync(WORKSPACE, { recursive: true, force: true });
});

describe('build artifact contents', () => {
  it.each(['development', 'production'])(
    '%s contains exactly the loadable file set (no source-only or env files)',
    (mode) => {
      const files = fs.readdirSync(path.join(WORKSPACE, mode)).sort();
      expect(files).toEqual(EXPECTED_FILES);
    },
  );

  it.each(['development', 'production'])('%s bundles the service worker (no relative imports left)', (mode) => {
    const worker = readWorker(mode);
    expect(worker).not.toContain('./background-core.js');
    expect(worker).not.toContain('./auth.js');
    expect(worker).not.toContain('__TIDDLY_API_URL__');
    expect(worker).not.toContain('__TIDDLY_CLERK_PUBLISHABLE_KEY__');
    expect(worker).not.toContain('__TIDDLY_CLERK_SYNC_HOST__');
    // Bundled handlers are actually present, not an empty shell.
    expect(worker).toContain('CREATE_BOOKMARK');
  });
});

describe('generated manifests', () => {
  it('production carries exactly the production host set (sync host and FAPI dedupe)', () => {
    expect(readManifest('production').host_permissions).toEqual([
      'https://api.tiddly.me/*',
      'https://clerk.tiddly.me/*',
    ]);
  });

  it('development carries exactly the development host set (portless localhost dedupes API + sync host)', () => {
    // Chrome's documented localhost pattern is portless and matches any port;
    // match patterns never carry ports (the port lives in the runtime URL).
    expect(readManifest('development').host_permissions).toEqual([
      'http://localhost/*',
      'https://fake-instance.clerk.accounts.dev/*',
    ]);
  });

  it.each(['development', 'production'])('%s keeps the module worker pairing (esm bundle <-> type module)', (mode) => {
    const manifest = readManifest(mode);
    expect(manifest.background).toEqual({
      service_worker: 'background.js',
      type: 'module',
    });
  });

  it.each(['development', 'production'])('%s preserves the static base fields (incl. the cookies permission)', (mode) => {
    const base = JSON.parse(
      fs.readFileSync(path.join(ROOT, 'manifest.base.json'), 'utf-8'),
    );
    const manifest = readManifest(mode);
    expect(manifest.version).toBe(base.version);
    expect(manifest.permissions).toEqual(base.permissions);
    expect(manifest.permissions).toContain('cookies');
    expect(manifest.commands).toEqual(base.commands);
    expect(manifest.key).toBe(base.key);
  });

  // Key-pinning tripwire (plan M7 step 3 preflight, made permanent): the
  // committed public key must derive the published Web Store extension ID —
  // Clerk allowlists, the azp allowlist, and the Sync Host flow are all bound
  // to this exact identity. A wrong key silently mints a third ID and
  // invalidates all of it. Chrome's ID = first 128 bits of SHA-256 over the
  // DER key, hex mapped 0-9a-f -> a-p.
  it('the committed manifest key derives the published Web Store extension ID', () => {
    const base = JSON.parse(
      fs.readFileSync(path.join(ROOT, 'manifest.base.json'), 'utf-8'),
    );
    const der = Buffer.from(base.key, 'base64');
    const derived = crypto.createHash('sha256').update(der).digest('hex').slice(0, 32)
      .replace(/[0-9a-f]/g, (c) => 'abcdefghijklmnop'['0123456789abcdef'.indexOf(c)]);
    expect(derived).toBe('npjlfgkihebhandkknldnjlcdmcpomkc');
  });
});

describe('injected configuration', () => {
  it('production worker carries the production values and none of the dev fixture values', () => {
    const worker = readWorker('production');
    expect(worker).toContain('"https://api.tiddly.me"');
    expect(worker).toContain('"https://clerk.tiddly.me"');
    expect(worker).toContain(`"${PROD_KEY}"`);
    // Targeted absences: this project's specific development values — not a
    // blanket scan (the bundled Clerk SDK may legitimately contain generic
    // dev-domain strings of its own).
    expect(worker).not.toContain('http://localhost:8000');
    expect(worker).not.toContain('fake-instance.clerk.accounts.dev');
    expect(worker).not.toContain('pk_test_ZmFrZS1pbnN0YW5jZS5jbGVyay5hY2NvdW50cy5kZXYk');
  });

  it('development worker carries the development API URL, sync host, and publishable key', () => {
    const worker = readWorker('development');
    expect(worker).toContain('"http://localhost:8000"');
    expect(worker).toContain('"http://localhost"');
    expect(worker).toContain('"pk_test_ZmFrZS1pbnN0YW5jZS5jbGVyay5hY2NvdW50cy5kZXYk"');
  });
});

describe('store packaging (package.mjs)', () => {
  it('replaces a stale archive completely — entry list equals the build inventory', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'tiddly-ext-zip-'));
    const output = path.join(dir, 'chrome-extension.zip');
    try {
      // Seed a stale archive with top-level AND nested junk — the exact
      // leftover-entries failure `zip -r` update semantics would produce.
      const junkDir = path.join(dir, 'junk');
      fs.mkdirSync(path.join(junkDir, 'nested'), { recursive: true });
      fs.writeFileSync(path.join(junkDir, 'stale-top-level.js'), 'junk');
      fs.writeFileSync(path.join(junkDir, 'nested', 'stale-deep.js'), 'junk');
      execSync(`zip -r ${JSON.stringify(output)} .`, { cwd: junkDir, stdio: 'pipe' });

      // --build-root keeps the packager's own production build (and the
      // inventory compared below) inside the workspace too — package.mjs
      // rebuilds production internally, so omitting it would clobber the
      // repo's build/production despite --output pointing elsewhere.
      const envPath = path.join(dir, 'production.env');
      fs.writeFileSync(envPath, PROD_REQUIRED);
      const result = spawnSync(
        'node',
        [
          'package.mjs',
          '--env-file', envPath,
          '--build-root', WORKSPACE,
          '--output', output,
        ],
        { cwd: ROOT, encoding: 'utf-8' },
      );
      expect(result.status).toBe(0);

      const zipEntries = execSync(`unzip -Z1 ${JSON.stringify(output)}`, { encoding: 'utf-8' })
        .split('\n')
        .filter((entry) => entry && !entry.endsWith('/'))
        .sort();
      expect(zipEntries).toEqual(listFilesRecursive(path.join(WORKSPACE, 'production')));
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }, 60_000);
});

// Declared last on purpose: the success cases below rewrite the workspace's
// development/production artifacts with inline fixture values and do not
// restore them. Nothing runs after this block, and the workspace is deleted
// in afterAll — if you add tests after this describe, don't read WORKSPACE.
describe('build configuration validation', () => {
  // Every failure case asserts on stderr so a wrong-reason failure can't pass.
  it('rejects a build missing required values, naming them', async () => {
    const result = buildMode('development', ['--no-env-file']);
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('missing required value(s) for development');
    expect(result.stderr).toContain('CLERK_PUBLISHABLE_KEY');
    expect(result.stderr).toContain('CLERK_FRONTEND_API');
  });

  it('rejects an unknown key, naming it', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_APIURL=https://typo.example\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('unknown key "TIDDLY_APIURL"');
  });

  it('rejects a non-comment line without =', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_API_URL https://example.com\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('not KEY=VALUE');
  });

  it('rejects a duplicate key', async () => {
    const result = buildWithEnv(
      'development',
      DEV_REQUIRED + 'TIDDLY_API_URL=https://a.example\nTIDDLY_API_URL=https://b.example\n',
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('duplicate key');
  });

  it('rejects an empty value', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_API_URL=\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('empty value');
  });

  it('rejects a quoted value', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_API_URL="https://a.example"\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('quotes are not supported');
  });

  it('rejects a URL with a path', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_API_URL=https://a.example/api\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('bare origin');
  });

  it('rejects a production API override that differs from the canonical origin', async () => {
    const result = buildWithEnv('production', PROD_REQUIRED + 'TIDDLY_API_URL=https://api.wrong-server.example\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('pinned to https://api.tiddly.me');
  });

  it('rejects a production sync-host override (pinned like the API origin)', async () => {
    const result = buildWithEnv('production', PROD_REQUIRED + 'CLERK_SYNC_HOST=https://evil.example\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('pinned to https://clerk.tiddly.me');
  });

  it('accepts a production override equal to the canonical origin', async () => {
    const result = buildWithEnv('production', PROD_REQUIRED + 'TIDDLY_API_URL=https://api.tiddly.me\n');
    expect(result.status).toBe(0);
  });

  it('rejects a publishable key with the wrong prefix for the mode', async () => {
    const result = buildWithEnv(
      'development',
      'CLERK_PUBLISHABLE_KEY=pk_live_ZmFrZQ==\nCLERK_FRONTEND_API=https://fake-instance.clerk.accounts.dev\n',
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('must start with "pk_test_"');
  });

  it('rejects http for a non-loopback host in development', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_API_URL=http://dev-box.example:8000\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('loopback');
  });

  it('applies a development override end-to-end: trailing slash normalized, manifest pattern portless, port kept in the runtime URL', async () => {
    const result = buildWithEnv('development', DEV_REQUIRED + 'TIDDLY_API_URL=https://fixture.example:8443/\n');
    expect(result.status).toBe(0);
    expect(readManifest('development').host_permissions).toEqual([
      'https://fixture.example/*',
      'http://localhost/*',
      'https://fake-instance.clerk.accounts.dev/*',
    ]);
    expect(readWorker('development')).toContain('"https://fixture.example:8443"');
  });

  it('rejects a publishable key whose payload is not valid base64', async () => {
    const result = buildWithEnv(
      'development',
      'CLERK_PUBLISHABLE_KEY=pk_test_!!!not-base64!!!\nCLERK_FRONTEND_API=https://fake-instance.clerk.accounts.dev\n',
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('not valid base64');
  });

  it('rejects a publishable key without the terminal $ marker', async () => {
    const noDollar = Buffer.from('fake-instance.clerk.accounts.dev').toString('base64');
    const result = buildWithEnv(
      'development',
      `CLERK_PUBLISHABLE_KEY=pk_test_${noDollar}\nCLERK_FRONTEND_API=https://fake-instance.clerk.accounts.dev\n`,
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('exactly one terminal $');
  });

  it('rejects a key/instance mismatch (key encodes a different Frontend API)', async () => {
    const otherInstance = Buffer.from('other-instance.clerk.accounts.dev$').toString('base64');
    const result = buildWithEnv(
      'development',
      `CLERK_PUBLISHABLE_KEY=pk_test_${otherInstance}\nCLERK_FRONTEND_API=https://fake-instance.clerk.accounts.dev\n`,
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('key/instance mismatch');
  });
});
