'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const child_process = require('child_process');

const WORKSPACE_ROOT = path.resolve(__dirname, '..', '..');

const STARTING_HASHES = {
  'src/engine/marketIntelligence/forecastEngine.ts': '738E787ABDF701C1658FE4F3234511F7B489D22FC46EDB652E3CD46035034E87',
  'src/engine/marketIntelligence/types.ts': '2203AC9A0527025282183A5D82C8355786BCA5125049122739918289748514C0',
  'src/engine/marketIntelligence/providers/MarketDataProvider.ts': 'FBA02EE957EE3FB1DB2B14BB54025AE72DC6FF93AF634EE18DC5B4ED5D338A02'
};

const CANONICAL_COMPILER_FILES = [
  'node_modules/typescript/bin/tsc',
  'node_modules/typescript/lib/_tsc.js',
  'node_modules/typescript/lib/tsc.js',
  'node_modules/typescript/package.json'
];

const ALLOWED_ROOT_KEYS = new Set([
  'schema_version',
  'mode',
  'calculation_id',
  'source_files',
  'support_files',
  'toolchain',
  'emitted_files',
  'package_boundary',
  'compiler_exit'
]);

const ALLOWED_TOOLCHAIN_KEYS = new Set([
  'node_version',
  'node_executable',
  'typescript_version',
  'compiler_files'
]);

const ALLOWED_RECORD_KEYS = new Set([
  'path',
  'bytes',
  'sha256'
]);

const ALLOWED_NODE_EXEC_KEYS = new Set([
  'bytes',
  'sha256'
]);

function assertExactKeys(obj, allowedSet, label) {
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) {
    throw new Error(`${label} must be a non-null object`);
  }
  const keys = Object.keys(obj);
  for (const k of keys) {
    if (!allowedSet.has(k)) {
      throw new Error(`Unexpected unknown key "${k}" in ${label}`);
    }
  }
  for (const k of allowedSet) {
    if (!(k in obj)) {
      throw new Error(`Missing required key "${k}" in ${label}`);
    }
  }
}

function assertSafeRelativePath(relPath) {
  if (typeof relPath !== 'string' || relPath.length === 0) {
    throw new Error(`Invalid path: ${relPath}`);
  }
  if (path.isAbsolute(relPath) || /^[A-Za-z]:/.test(relPath)) {
    throw new Error(`Absolute paths forbidden in manifest: ${relPath}`);
  }
  const parts = relPath.split(/[/\\]/);
  if (parts.includes('..') || parts.includes('.')) {
    throw new Error(`Directory traversal forbidden in manifest path: ${relPath}`);
  }
}

function validateFileRecord(rec, label) {
  assertExactKeys(rec, ALLOWED_RECORD_KEYS, label);
  assertSafeRelativePath(rec.path);
  if (!Number.isSafeInteger(rec.bytes) || rec.bytes < 0) {
    throw new Error(`${label}.bytes must be a non-negative integer`);
  }
  if (typeof rec.sha256 !== 'string' || !/^[0-9A-Fa-f]{64}$/.test(rec.sha256)) {
    throw new Error(`${label}.sha256 must be a 64-character hex string`);
  }
}

function sha256Buffer(buf) {
  return crypto.createHash('sha256').update(buf).digest('hex').toUpperCase();
}

function sha256File(filePath) {
  const content = fs.readFileSync(filePath);
  return sha256Buffer(content);
}

function getFileRecord(repoRelativePath, rootDir = WORKSPACE_ROOT) {
  const fullPath = path.resolve(rootDir, repoRelativePath);
  const stat = fs.statSync(fullPath);
  const hash = sha256File(fullPath);
  const posixPath = repoRelativePath.split(path.sep).join('/');
  return {
    path: posixPath,
    bytes: stat.size,
    sha256: hash
  };
}

function verifyPathWithinWorkspace(targetPath) {
  const resolved = path.resolve(targetPath);
  const rel = path.relative(WORKSPACE_ROOT, resolved);
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    throw new Error(`Path ${targetPath} resolves outside workspace: ${resolved}`);
  }

  const realRoot = fs.realpathSync(WORKSPACE_ROOT);

  // Validate every existing or link entry ancestor of resolved path. Links are refused
  // at any depth; realpath containment applies only to the workspace root and its
  // descendants, because parents of a nested checkout legitimately lie outside it.
  let cur = resolved;
  while (cur && cur !== path.dirname(cur)) {
    const lstat = fs.lstatSync(cur, { throwIfNoEntry: false });
    if (lstat) {
      if (lstat.isSymbolicLink()) {
        throw new Error(`Path ${targetPath} or its ancestor is a symbolic link: ${cur}`);
      }
      const curRel = path.relative(WORKSPACE_ROOT, cur);
      if (curRel.startsWith('..') || path.isAbsolute(curRel)) {
        cur = path.dirname(cur);
        continue;
      }
      const realCur = fs.realpathSync(cur);
      const realRel = path.relative(realRoot, realCur);
      if (realRel.startsWith('..') || path.isAbsolute(realRel)) {
        throw new Error(`Path ${targetPath} ancestor realpath resolves outside workspace: ${realCur}`);
      }
    }
    cur = path.dirname(cur);
  }

  return resolved;
}

function safeWriteFile(filePath, content, encoding = 'utf8') {
  verifyPathWithinWorkspace(filePath);
  const lstat = fs.lstatSync(filePath, { throwIfNoEntry: false });
  if (lstat && lstat.isSymbolicLink()) {
    throw new Error(`Refusing write: target is a symbolic link: ${filePath}`);
  }
  fs.writeFileSync(filePath, content, encoding);
}

function getExpectedSets(mode) {
  const source_files = [
    'src/engine/marketIntelligence/forecastEngine.ts',
    'src/engine/marketIntelligence/providers/MarketDataProvider.ts',
    'src/engine/marketIntelligence/types.ts'
  ];
  if (mode === 'candidate') {
    source_files.push('src/engine/marketIntelligence/forecastCore.ts');
  }
  source_files.sort();

  const support_files = [
    'package.json',
    'package-lock.json',
    'research/prediction_eval/compile_replay.cjs',
    'research/prediction_eval/tsconfig.replay.json'
  ];
  if (mode === 'candidate') {
    support_files.push('research/prediction_eval/replay.cjs');
    // tsconfig.replay.json extends the root config, so its inherited options are a
    // compiler input. Candidate-only: the sealed baseline manifest predates this
    // binding and must stay valid for the supplemental differential comparison.
    support_files.push('tsconfig.json');
  }
  support_files.sort();

  const emitted_files = [
    'src/engine/marketIntelligence/forecastEngine.js',
    'src/engine/marketIntelligence/providers/MarketDataProvider.js',
    'src/engine/marketIntelligence/types.js'
  ];
  if (mode === 'candidate') {
    emitted_files.push('src/engine/marketIntelligence/forecastCore.js');
  }
  emitted_files.sort();

  return { source_files, support_files, emitted_files };
}

function getFilesRecursive(dir, baseDir = dir) {
  let results = [];
  const lstatDir = fs.lstatSync(dir, { throwIfNoEntry: false });
  if (!lstatDir) return results;
  if (lstatDir.isSymbolicLink()) {
    throw new Error(`Directory cannot be a symbolic link: ${dir}`);
  }
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    const lstat = fs.lstatSync(full, { throwIfNoEntry: false });
    if (!lstat) continue;
    if (lstat.isSymbolicLink() || entry.isSymbolicLink()) {
      throw new Error(`Symbolic link encountered during directory enumeration: ${full}`);
    }
    if (lstat.isDirectory()) {
      results = results.concat(getFilesRecursive(full, baseDir));
    } else if (lstat.isFile()) {
      const rel = path.relative(baseDir, full).split(path.sep).join('/');
      results.push(rel);
    } else {
      throw new Error(`Non-regular file encountered during directory enumeration: ${full}`);
    }
  }
  return results;
}

function preflightOutputDirectory(modeOutDir, ownedEmittedFiles) {
  // 1. Verify output directory path resolves within workspace
  verifyPathWithinWorkspace(modeOutDir);

  const dirLstat = fs.lstatSync(modeOutDir, { throwIfNoEntry: false });
  if (dirLstat) {
    if (dirLstat.isSymbolicLink()) {
      throw new Error(`Output directory cannot be a symbolic link: ${modeOutDir}`);
    }
    if (!dirLstat.isDirectory()) {
      throw new Error(`Output directory is not a directory: ${modeOutDir}`);
    }
  }

  // 2. Preflight ALL fixed output targets and their entire ancestor chains (including absent leaves)
  for (const rel of ownedEmittedFiles) {
    const target = path.join(modeOutDir, rel);
    verifyPathWithinWorkspace(target);
    const targetLstat = fs.lstatSync(target, { throwIfNoEntry: false });
    if (targetLstat) {
      if (targetLstat.isSymbolicLink()) {
        throw new Error(`Refusing write: existing output target is a symbolic link: ${target}`);
      }
      if (!targetLstat.isFile()) {
        throw new Error(`Refusing write: existing output target is not a regular file: ${target}`);
      }
    }
  }

  // 3. If output directory exists on disk, inspect all existing entries recursively
  if (dirLstat && dirLstat.isDirectory()) {
    const allowedFilesSet = new Set(ownedEmittedFiles);
    const allowedDirsSet = new Set();
    for (const rel of ownedEmittedFiles) {
      let curRelDir = path.dirname(rel);
      while (curRelDir && curRelDir !== '.' && curRelDir !== '') {
        allowedDirsSet.add(curRelDir.split(path.sep).join('/'));
        curRelDir = path.dirname(curRelDir);
      }
    }

    function inspectExistingTree(currentDir) {
      const entries = fs.readdirSync(currentDir, { withFileTypes: true });
      for (const entry of entries) {
        const full = path.join(currentDir, entry.name);
        const relToMode = path.relative(modeOutDir, full).split(path.sep).join('/');

        const entryLstat = fs.lstatSync(full, { throwIfNoEntry: false });
        if (!entryLstat || entryLstat.isSymbolicLink() || entry.isSymbolicLink()) {
          throw new Error(`Output directory contains a symbolic link entry: ${full}`);
        }

        if (entryLstat.isDirectory()) {
          if (!allowedDirsSet.has(relToMode)) {
            throw new Error(`Output directory contains an unexpected directory: ${relToMode}`);
          }
          inspectExistingTree(full);
        } else if (entryLstat.isFile()) {
          if (!allowedFilesSet.has(relToMode)) {
            throw new Error(`Output directory contains an unexpected file: ${relToMode}`);
          }
        } else {
          throw new Error(`Output directory contains a non-regular entry: ${full}`);
        }
      }
    }

    inspectExistingTree(modeOutDir);
  }
}

// Explicit opt-in evidence capture for the compiler child. The slot must be a fresh,
// workspace-confined directory disjoint from the build output, so one invocation can
// never overwrite another invocation's record or pollute the emitted-file set.
function prepareChildCapture(childLogDir, modeOutDir) {
  if (typeof childLogDir !== 'string' || childLogDir.length === 0) {
    throw new Error('childLogDir must be a non-empty path string');
  }
  const captureDir = verifyPathWithinWorkspace(childLogDir);
  const isWithin = (parent, child) => {
    const rel = path.relative(parent, child);
    return rel === '' || (!rel.startsWith('..') && !path.isAbsolute(rel));
  };
  if (isWithin(modeOutDir, captureDir) || isWithin(captureDir, modeOutDir)) {
    throw new Error(`childLogDir must be disjoint from the build output directory: ${captureDir}`);
  }
  if (fs.lstatSync(captureDir, { throwIfNoEntry: false })) {
    throw new Error(`childLogDir already exists; capture requires a fresh directory: ${captureDir}`);
  }
  return captureDir;
}

// Required capture: any failure is surfaced to the caller instead of being swallowed.
function writeChildCapture(captureDir, label, record, stdoutText, stderrText) {
  try {
    fs.mkdirSync(captureDir, { recursive: true });
    verifyPathWithinWorkspace(captureDir);
    if (!fs.lstatSync(captureDir).isDirectory()) {
      throw new Error('capture path is not a directory');
    }
    const stdoutBuf = Buffer.from(stdoutText || '', 'utf8');
    const stderrBuf = Buffer.from(stderrText || '', 'utf8');
    const stdoutPath = path.join(captureDir, `${label}.stdout.log`);
    const stderrPath = path.join(captureDir, `${label}.stderr.log`);
    // flag 'wx' refuses to replace any existing entry, including a planted link
    fs.writeFileSync(stdoutPath, stdoutBuf, { flag: 'wx' });
    fs.writeFileSync(stderrPath, stderrBuf, { flag: 'wx' });
    const fullRecord = {
      ...record,
      stdout_path: stdoutPath,
      stdout_bytes: stdoutBuf.length,
      stdout_sha256: sha256Buffer(stdoutBuf),
      stderr_path: stderrPath,
      stderr_bytes: stderrBuf.length,
      stderr_sha256: sha256Buffer(stderrBuf)
    };
    fs.writeFileSync(path.join(captureDir, `${label}.json`), JSON.stringify(fullRecord, null, 2) + '\n', { encoding: 'utf8', flag: 'wx' });
  } catch (err) {
    throw new Error(`Compiler child capture failed in ${captureDir}: ${err.message}`);
  }
}

function compile(mode, options = {}) {
  if (mode !== 'baseline' && mode !== 'candidate') {
    throw new Error(`Invalid compile mode: "${mode}". Must be "baseline" or "candidate".`);
  }

  const modeOutDir = options.outDir
    ? verifyPathWithinWorkspace(options.outDir)
    : verifyPathWithinWorkspace(path.join(WORKSPACE_ROOT, 'build', 'prediction-eval', mode));
  const priorManifest = path.join(modeOutDir, 'build-manifest.json');

  const { source_files: expectedSourceFiles, support_files: expectedSupportFiles, emitted_files: expectedEmittedFiles } = getExpectedSets(mode);

  // Invalidate only the fixed owned emitted artifacts before compile to guarantee fresh emission
  const ownedEmittedFiles = [
    ...expectedEmittedFiles,
    'package.json',
    'build-manifest.json'
  ];

  // 1. Input preconditions BEFORE any mutation: a failed check must leave existing
  // outputs, including a sealed baseline build, untouched.
  if (mode === 'baseline') {
    for (const [relPath, expectedHash] of Object.entries(STARTING_HASHES)) {
      const fullPath = path.join(WORKSPACE_ROOT, relPath);
      if (!fs.existsSync(fullPath)) {
        throw new Error(`Baseline check failed: missing required file ${relPath}`);
      }
      const actualHash = sha256File(fullPath);
      if (actualHash !== expectedHash) {
        throw new Error(`Baseline check failed: hash mismatch for ${relPath}. Expected ${expectedHash}, got ${actualHash}`);
      }
    }
  }

  // Pre-compilation stability baseline; reading every declared input here also
  // fails on a missing source/support/compiler file before anything is deleted.
  const preSourceHashes = new Map();
  for (const rel of expectedSourceFiles) {
    preSourceHashes.set(rel, sha256File(path.join(WORKSPACE_ROOT, rel)));
  }
  const preSupportHashes = new Map();
  for (const rel of expectedSupportFiles) {
    preSupportHashes.set(rel, sha256File(path.join(WORKSPACE_ROOT, rel)));
  }
  const preCompilerHashes = new Map();
  for (const rel of CANONICAL_COMPILER_FILES) {
    preCompilerHashes.set(rel, sha256File(path.join(WORKSPACE_ROOT, rel)));
  }

  // Local locked TypeScript paths
  const tsconfigPath = path.join(WORKSPACE_ROOT, 'research', 'prediction_eval', 'tsconfig.replay.json');
  const tscBin = path.join(WORKSPACE_ROOT, 'node_modules', 'typescript', 'bin', 'tsc');

  if (!fs.existsSync(tscBin)) {
    throw new Error(`Local TypeScript binary not found at ${tscBin}`);
  }

  // Ordinary compilation writes only owned outputs; evidence capture is opt-in.
  const captureDir = options.childLogDir !== undefined
    ? prepareChildCapture(options.childLogDir, modeOutDir)
    : null;

  // 2. Output preflight BEFORE any mutation, deletion, or compiler launch
  preflightOutputDirectory(modeOutDir, ownedEmittedFiles);

  // 3. Safely invalidate ONLY the exact owned emitted artifacts
  if (fs.existsSync(modeOutDir)) {
    for (const rel of ownedEmittedFiles) {
      const target = path.join(modeOutDir, rel);
      const lstat = fs.lstatSync(target, { throwIfNoEntry: false });
      if (lstat) {
        fs.unlinkSync(target);
      }
    }
  }

  // Ensure output directory exists and emit package.json type=commonjs
  fs.mkdirSync(modeOutDir, { recursive: true });
  const modePackageJsonPath = path.join(modeOutDir, 'package.json');
  safeWriteFile(modePackageJsonPath, JSON.stringify({ type: 'commonjs' }, null, 2) + '\n', 'utf8');

  const tscArgs = [
    tscBin,
    '--project', tsconfigPath,
    '--outDir', modeOutDir,
    '--pretty', 'false'
  ];

  const startUtc = new Date().toISOString();
  const res = child_process.spawnSync(process.execPath, tscArgs, {
    cwd: WORKSPACE_ROOT,
    stdio: ['ignore', 'pipe', 'pipe'],
    encoding: 'utf8'
  });
  const endUtc = new Date().toISOString();

  if (res.stdout && res.stdout.length > 0) {
    process.stdout.write(res.stdout);
  }
  if (res.stderr && res.stderr.length > 0) {
    process.stderr.write(res.stderr);
  }

  // Requested compiler child evidence is recorded before the exit status is judged,
  // so a failed compile keeps its streams; a capture failure fails the compile.
  if (captureDir) {
    writeChildCapture(captureDir, 'compiler-tsc', {
      label: 'compiler-tsc',
      start_utc: startUtc,
      end_utc: endUtc,
      exe: process.execPath,
      argv: tscArgs,
      cwd: WORKSPACE_ROOT,
      immediate_status: res.status,
      immediate_native_exit: res.status,
      signal: res.signal,
      error: res.error ? res.error.message : null
    }, res.stdout, res.stderr);
  }

  if (res.status !== 0) {
    const errText = res.stderr || res.stdout || `Compiler exited with code ${res.status}`;
    throw new Error(`TypeScript compilation failed for mode "${mode}" (exit ${res.status}):\n${errText}`);
  }

  // Post-compilation input stability verification
  for (const [rel, preHash] of preSourceHashes.entries()) {
    const postHash = sha256File(path.join(WORKSPACE_ROOT, rel));
    if (postHash !== preHash) {
      throw new Error(`Source file instability during compilation: ${rel}`);
    }
  }
  for (const [rel, preHash] of preSupportHashes.entries()) {
    const postHash = sha256File(path.join(WORKSPACE_ROOT, rel));
    if (postHash !== preHash) {
      throw new Error(`Support file instability during compilation: ${rel}`);
    }
  }
  for (const [rel, preHash] of preCompilerHashes.entries()) {
    const postHash = sha256File(path.join(WORKSPACE_ROOT, rel));
    if (postHash !== preHash) {
      throw new Error(`Compiler file instability during compilation: ${rel}`);
    }
  }

  // Fresh emitted set verification: verify only expected files are emitted in modeOutDir
  const actualEmittedOnDisk = getFilesRecursive(modeOutDir);
  const allowedOutputs = new Set([
    ...expectedEmittedFiles,
    'package.json'
  ]);
  for (const actualRel of actualEmittedOnDisk) {
    if (!allowedOutputs.has(actualRel)) {
      throw new Error(`Unexpected emitted file in output directory: ${actualRel}`);
    }
  }

  // Measure source_files
  const source_files = expectedSourceFiles.map(rel => getFileRecord(rel, WORKSPACE_ROOT));

  // Measure support_files
  const support_files = expectedSupportFiles.map(rel => getFileRecord(rel, WORKSPACE_ROOT));

  // Measure emitted_files (paths relative to mode root)
  const emitted_files = expectedEmittedFiles.map(rel => {
    const full = path.join(modeOutDir, rel);
    if (!fs.existsSync(full)) {
      throw new Error(`Expected emitted file missing: ${rel} at ${full}`);
    }
    const lstat = fs.lstatSync(full);
    if (lstat.isSymbolicLink()) {
      throw new Error(`Emitted file cannot be a symbolic link: ${full}`);
    }
    if (!lstat.isFile()) {
      throw new Error(`Emitted file is not a regular file: ${full}`);
    }
    return getFileRecord(rel, modeOutDir);
  });

  // Measure package_boundary (relative to mode root)
  const package_boundary = getFileRecord('package.json', modeOutDir);

  // Measure toolchain
  const nodeStat = fs.statSync(process.execPath);
  const nodeHash = sha256Buffer(fs.readFileSync(process.execPath));

  const tsPkgJson = JSON.parse(fs.readFileSync(path.join(WORKSPACE_ROOT, 'node_modules', 'typescript', 'package.json'), 'utf8'));

  const compiler_files = CANONICAL_COMPILER_FILES.map(rel => getFileRecord(rel, WORKSPACE_ROOT));
  compiler_files.sort((a, b) => a.path.localeCompare(b.path));

  const toolchain = {
    node_version: process.version,
    node_executable: {
      bytes: nodeStat.size,
      sha256: nodeHash
    },
    typescript_version: tsPkgJson.version,
    compiler_files
  };

  const manifest = {
    schema_version: 'nivesh-replay-build-v1',
    mode,
    calculation_id: 'preserved-directional-core-v1',
    source_files,
    support_files,
    toolchain,
    emitted_files,
    package_boundary,
    compiler_exit: 0
  };

  safeWriteFile(priorManifest, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
  return manifest;
}

function validateBuildManifest(manifest, expectedMode, workspaceRoot = WORKSPACE_ROOT) {
  if (!manifest || typeof manifest !== 'object' || Array.isArray(manifest)) {
    throw new Error('Build manifest must be a non-null object');
  }

  // Schema key strictness on root
  assertExactKeys(manifest, ALLOWED_ROOT_KEYS, 'build manifest root');

  if (manifest.schema_version !== 'nivesh-replay-build-v1') {
    throw new Error(`Invalid manifest schema_version: ${manifest.schema_version}`);
  }
  if (manifest.calculation_id !== 'preserved-directional-core-v1') {
    throw new Error(`Invalid manifest calculation_id: ${manifest.calculation_id}`);
  }
  if (manifest.mode !== expectedMode) {
    throw new Error(`Manifest mode mismatch: expected "${expectedMode}", got "${manifest.mode}"`);
  }
  if (manifest.compiler_exit !== 0) {
    throw new Error(`Manifest compiler_exit is nonzero: ${manifest.compiler_exit}`);
  }

  const { source_files: expSrc, support_files: expSup, emitted_files: expEmit } = getExpectedSets(expectedMode);

  // Canonical set verification BEFORE file access
  if (!Array.isArray(manifest.source_files)) throw new Error('manifest.source_files must be an array');
  const actualSrcPaths = manifest.source_files.map(r => r.path);
  if (JSON.stringify(actualSrcPaths) !== JSON.stringify(expSrc)) {
    throw new Error(`manifest.source_files paths do not match canonical set: expected ${JSON.stringify(expSrc)}, got ${JSON.stringify(actualSrcPaths)}`);
  }
  manifest.source_files.forEach((rec, idx) => validateFileRecord(rec, `manifest.source_files[${idx}]`));

  if (!Array.isArray(manifest.support_files)) throw new Error('manifest.support_files must be an array');
  const actualSupPaths = manifest.support_files.map(r => r.path);
  if (JSON.stringify(actualSupPaths) !== JSON.stringify(expSup)) {
    throw new Error(`manifest.support_files paths do not match canonical set: expected ${JSON.stringify(expSup)}, got ${JSON.stringify(actualSupPaths)}`);
  }
  manifest.support_files.forEach((rec, idx) => validateFileRecord(rec, `manifest.support_files[${idx}]`));

  if (!Array.isArray(manifest.emitted_files)) throw new Error('manifest.emitted_files must be an array');
  const actualEmitPaths = manifest.emitted_files.map(r => r.path);
  if (JSON.stringify(actualEmitPaths) !== JSON.stringify(expEmit)) {
    throw new Error(`manifest.emitted_files paths do not match canonical set: expected ${JSON.stringify(expEmit)}, got ${JSON.stringify(actualEmitPaths)}`);
  }
  manifest.emitted_files.forEach((rec, idx) => validateFileRecord(rec, `manifest.emitted_files[${idx}]`));

  validateFileRecord(manifest.package_boundary, 'manifest.package_boundary');
  if (manifest.package_boundary.path !== 'package.json') {
    throw new Error('manifest.package_boundary must be record for "package.json"');
  }

  // Toolchain canonical set check and schema key strictness
  if (!manifest.toolchain || typeof manifest.toolchain !== 'object' || Array.isArray(manifest.toolchain)) {
    throw new Error('manifest.toolchain missing or invalid');
  }
  assertExactKeys(manifest.toolchain, ALLOWED_TOOLCHAIN_KEYS, 'manifest.toolchain');

  // Verify node_version type and runtime identity
  if (typeof manifest.toolchain.node_version !== 'string') {
    throw new Error('manifest.toolchain.node_version must be string');
  }
  if (manifest.toolchain.node_version !== process.version) {
    throw new Error(`Toolchain node_version mismatch: manifest has "${manifest.toolchain.node_version}", current runtime is "${process.version}"`);
  }

  // Verify node_executable schema and runtime identity
  assertExactKeys(manifest.toolchain.node_executable, ALLOWED_NODE_EXEC_KEYS, 'manifest.toolchain.node_executable');
  if (!Number.isSafeInteger(manifest.toolchain.node_executable.bytes) || manifest.toolchain.node_executable.bytes < 0) {
    throw new Error('manifest.toolchain.node_executable.bytes must be non-negative integer');
  }
  if (typeof manifest.toolchain.node_executable.sha256 !== 'string' || !/^[0-9A-Fa-f]{64}$/.test(manifest.toolchain.node_executable.sha256)) {
    throw new Error('manifest.toolchain.node_executable.sha256 must be 64-character hex string');
  }
  const currentExecStat = fs.statSync(process.execPath);
  if (manifest.toolchain.node_executable.bytes !== currentExecStat.size) {
    throw new Error(`Toolchain node_executable size mismatch: manifest has ${manifest.toolchain.node_executable.bytes}, current executable has ${currentExecStat.size}`);
  }
  const currentExecHash = sha256File(process.execPath);
  if (manifest.toolchain.node_executable.sha256 !== currentExecHash) {
    throw new Error(`Toolchain node_executable sha256 mismatch: manifest has ${manifest.toolchain.node_executable.sha256}, current executable has ${currentExecHash}`);
  }

  // Verify typescript_version type and local package identity
  if (typeof manifest.toolchain.typescript_version !== 'string') {
    throw new Error('manifest.toolchain.typescript_version must be string');
  }
  const localTsPkgPath = path.join(workspaceRoot, 'node_modules', 'typescript', 'package.json');
  if (!fs.existsSync(localTsPkgPath)) {
    throw new Error(`TypeScript package.json not found at ${localTsPkgPath}`);
  }
  const localTsPkg = JSON.parse(fs.readFileSync(localTsPkgPath, 'utf8'));
  if (manifest.toolchain.typescript_version !== localTsPkg.version) {
    throw new Error(`Toolchain typescript_version mismatch: manifest has "${manifest.toolchain.typescript_version}", local package is "${localTsPkg.version}"`);
  }

  // Compiler files check
  if (!Array.isArray(manifest.toolchain.compiler_files)) {
    throw new Error('manifest.toolchain.compiler_files must be an array');
  }
  const actualCompilerPaths = manifest.toolchain.compiler_files.map(r => r.path);
  if (JSON.stringify(actualCompilerPaths) !== JSON.stringify(CANONICAL_COMPILER_FILES)) {
    throw new Error('manifest.toolchain.compiler_files do not match canonical list');
  }
  manifest.toolchain.compiler_files.forEach((rec, idx) => validateFileRecord(rec, `manifest.toolchain.compiler_files[${idx}]`));

  const modeOutDir = path.join(workspaceRoot, 'build', 'prediction-eval', expectedMode);

  // Validate source_files and support_files on disk for candidate mode
  if (expectedMode === 'candidate') {
    for (const rec of manifest.source_files) {
      const full = path.join(workspaceRoot, rec.path);
      if (!fs.existsSync(full)) throw new Error(`Source file missing: ${rec.path}`);
      const stat = fs.statSync(full);
      if (stat.size !== rec.bytes) throw new Error(`Source file size mismatch for ${rec.path}`);
      const hash = sha256File(full);
      if (hash !== rec.sha256) throw new Error(`Source file hash mismatch for ${rec.path}`);
    }

    // Validate support_files on disk
    for (const rec of manifest.support_files) {
      const full = path.join(workspaceRoot, rec.path);
      if (!fs.existsSync(full)) throw new Error(`Support file missing: ${rec.path}`);
      const stat = fs.statSync(full);
      if (stat.size !== rec.bytes) throw new Error(`Support file size mismatch for ${rec.path}`);
      const hash = sha256File(full);
      if (hash !== rec.sha256) throw new Error(`Support file hash mismatch for ${rec.path}`);
    }
  }

  // Validate emitted_files on disk
  for (const rec of manifest.emitted_files) {
    const full = path.join(modeOutDir, rec.path);
    if (!fs.existsSync(full)) throw new Error(`Emitted file missing: ${rec.path}`);
    const stat = fs.statSync(full);
    if (stat.size !== rec.bytes) throw new Error(`Emitted file size mismatch for ${rec.path}`);
    const hash = sha256File(full);
    if (hash !== rec.sha256) throw new Error(`Emitted file hash mismatch for ${rec.path}`);
  }

  // Validate package_boundary on disk
  const pkgFull = path.join(modeOutDir, manifest.package_boundary.path);
  if (!fs.existsSync(pkgFull)) throw new Error('Mode package.json missing');
  const pkgStat = fs.statSync(pkgFull);
  if (pkgStat.size !== manifest.package_boundary.bytes) throw new Error('Mode package.json size mismatch');
  const pkgHash = sha256File(pkgFull);
  if (pkgHash !== manifest.package_boundary.sha256) throw new Error('Mode package.json hash mismatch');

  // Validate toolchain compiler files on disk
  for (const rec of manifest.toolchain.compiler_files) {
    const full = path.join(workspaceRoot, rec.path);
    if (!fs.existsSync(full)) throw new Error(`Compiler file missing: ${rec.path}`);
    const stat = fs.statSync(full);
    if (stat.size !== rec.bytes) throw new Error(`Compiler file size mismatch for ${rec.path}`);
    const hash = sha256File(full);
    if (hash !== rec.sha256) throw new Error(`Compiler file hash mismatch for ${rec.path}`);
  }

  return true;
}

if (require.main === module) {
  const mode = process.argv[2];
  try {
    const manifest = compile(mode);
    process.stdout.write(`Successfully compiled ${mode} replay mode.\n`);
    process.exit(0);
  } catch (err) {
    process.stderr.write(`Compilation error: ${err.message}\n`);
    process.exit(1);
  }
}

module.exports = {
  compile,
  preflightOutputDirectory,
  getExpectedSets,
  validateBuildManifest,
  assertSafeRelativePath,
  verifyPathWithinWorkspace,
  safeWriteFile,
  sha256File,
  sha256Buffer,
  getFileRecord,
  STARTING_HASHES,
  CANONICAL_COMPILER_FILES,
  ALLOWED_ROOT_KEYS,
  ALLOWED_TOOLCHAIN_KEYS,
  ALLOWED_RECORD_KEYS,
  ALLOWED_NODE_EXEC_KEYS,
  assertExactKeys,
  validateFileRecord
};
