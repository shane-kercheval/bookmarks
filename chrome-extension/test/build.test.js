// Packaging assertions for the generated build artifacts (the plan's targeted
// checks — exact host sets and injected values, not blanket string scans that
// would false-positive on vendor SDK internals once Clerk is bundled).
//
// Hermetic in BOTH directions (review rounds 2026-07-24): every build passes
// --no-env-file or an explicit temp fixture (a developer's .env.*.local can
// never change what these tests assert), and every build writes into one
// temporary workspace via --build-root (the tests can never overwrite the
// repo's build/<mode>/ — the artifact a developer may have loaded unpacked
// in Chrome).
import { execSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');

let WORKSPACE;

const EXPECTED_FILES = [
  'background.js',
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

function buildMode(mode, extraArgs = ['--no-env-file']) {
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
  for (const mode of ['development', 'production']) {
    const result = buildMode(mode);
    if (result.status !== 0) throw new Error(`workspace build failed for ${mode}:\n${result.stderr}`);
  }
}, 30_000);

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
    expect(worker).not.toContain('__TIDDLY_API_URL__');
    // Bundled handlers are actually present, not an empty shell.
    expect(worker).toContain('CREATE_BOOKMARK');
  });
});

describe('generated manifests', () => {
  it('production carries exactly the production host set', () => {
    expect(readManifest('production').host_permissions).toEqual([
      'https://api.tiddly.me/*',
    ]);
  });

  it('development carries exactly the development host set', () => {
    expect(readManifest('development').host_permissions).toEqual([
      'http://localhost:8000/*',
    ]);
  });

  it.each(['development', 'production'])('%s keeps the module worker pairing (esm bundle <-> type module)', (mode) => {
    const manifest = readManifest(mode);
    expect(manifest.background).toEqual({
      service_worker: 'background.js',
      type: 'module',
    });
  });

  it.each(['development', 'production'])('%s preserves the static base fields', (mode) => {
    const base = JSON.parse(
      fs.readFileSync(path.join(ROOT, 'manifest.base.json'), 'utf-8'),
    );
    const manifest = readManifest(mode);
    expect(manifest.version).toBe(base.version);
    expect(manifest.permissions).toEqual(base.permissions);
    expect(manifest.commands).toEqual(base.commands);
  });
});

describe('injected configuration', () => {
  it('production worker carries the production API URL and no development URL', () => {
    const worker = readWorker('production');
    expect(worker).toContain('"https://api.tiddly.me"');
    expect(worker).not.toContain('http://localhost:8000');
  });

  it('development worker carries the development API URL', () => {
    expect(readWorker('development')).toContain('"http://localhost:8000"');
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
      const result = spawnSync(
        'node',
        ['package.mjs', '--no-env-file', '--build-root', WORKSPACE, '--output', output],
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
  }, 30_000);
});

// Declared last on purpose: the success cases below rewrite the workspace's
// development artifact with fixture values and do not restore it. Nothing
// runs after this block, and the workspace is deleted in afterAll — if you
// add tests below/after this describe, don't read WORKSPACE/development.
describe('build configuration validation', () => {
  // Every failure case asserts on stderr so a wrong-reason failure can't pass.
  it('rejects an unknown key, naming it', () => {
    const result = buildWithEnv('development', 'TIDDLY_APIURL=https://typo.example\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('unknown key "TIDDLY_APIURL"');
  });

  it('rejects a non-comment line without =', () => {
    const result = buildWithEnv('development', 'TIDDLY_API_URL https://example.com\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('not KEY=VALUE');
  });

  it('rejects a duplicate key', () => {
    const result = buildWithEnv(
      'development',
      'TIDDLY_API_URL=https://a.example\nTIDDLY_API_URL=https://b.example\n',
    );
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('duplicate key');
  });

  it('rejects an empty value', () => {
    const result = buildWithEnv('development', 'TIDDLY_API_URL=\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('empty value');
  });

  it('rejects a quoted value', () => {
    const result = buildWithEnv('development', 'TIDDLY_API_URL="https://a.example"\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('quotes are not supported');
  });

  it('rejects a URL with a path', () => {
    const result = buildWithEnv('development', 'TIDDLY_API_URL=https://a.example/api\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('bare origin');
  });

  it('rejects a production override that differs from the canonical origin', () => {
    const result = buildWithEnv('production', 'TIDDLY_API_URL=https://api.wrong-server.example\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('pinned to https://api.tiddly.me');
  });

  it('accepts a production override equal to the canonical origin', () => {
    const result = buildWithEnv('production', 'TIDDLY_API_URL=https://api.tiddly.me\n');
    expect(result.status).toBe(0);
  });

  it('rejects http for a non-loopback host in development', () => {
    const result = buildWithEnv('development', 'TIDDLY_API_URL=http://dev-box.example:8000\n');
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('loopback');
  });

  it('applies a development override end-to-end and normalizes a trailing slash', () => {
    const result = buildWithEnv('development', 'TIDDLY_API_URL=https://fixture.example/\n');
    expect(result.status).toBe(0);
    expect(readManifest('development').host_permissions).toEqual(['https://fixture.example/*']);
    expect(readWorker('development')).toContain('"https://fixture.example"');
  });
});
