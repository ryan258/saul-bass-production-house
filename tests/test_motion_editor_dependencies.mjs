import assert from 'node:assert/strict';
import {after, before, test} from 'node:test';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {createServer, optimizeDeps, resolveConfig} from 'vite';

const framework = fileURLToPath(new URL('../', import.meta.url));
const saved = {project: process.env.SBPH_MOTION_PROJECT, output: process.env.SBPH_MOTION_OUTPUT};
let temporary, server, metadata;

before(async () => {
  temporary = await fs.mkdtemp(path.join(os.tmpdir(), 'sbph-editor-dependencies-'));
  const project = path.join(temporary, 'project.ts');
  await fs.writeFile(project, "import {makeProject} from '@motion-canvas/core';\nexport default makeProject({scenes: []});\n");
  process.env.SBPH_MOTION_PROJECT = project;
  process.env.SBPH_MOTION_OUTPUT = path.join(temporary, 'output');
  const options = {configFile: path.join(framework, 'motion-canvas/vite.config.ts'),
    envFile: false, cacheDir: path.join(temporary, 'cache'), optimizeDeps: {entries: []},
    server: {host: '127.0.0.1', port: 0, strictPort: true, watch: null}};
  // Initialize real optimizer metadata without crawling any film or opening a browser.
  metadata = await optimizeDeps(await resolveConfig(options, 'serve'), true, true);
  server = await createServer(options);
  await server.listen();
});

after(async () => {
  try {await server?.close();} finally {
    for (const [key, value] of [['SBPH_MOTION_PROJECT', saved.project], ['SBPH_MOTION_OUTPUT', saved.output]]) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    if (temporary) await fs.rm(temporary, {recursive: true, force: true});
  }
});

test('versioned 2D editor imports resolve to an existing JavaScript module', async () => {
  for (const query of ['?v=sbph-regression', '?import&v=sbph-regression']) {
    const resolved = await server.pluginContainer.resolveId('@motion-canvas/2d/editor' + query);
    assert.ok(resolved, 'The editor extension must resolve');
    const file = resolved.id.split('?')[0];
    assert.ok((await fs.stat(file).catch(() => null))?.isFile(), `Missing versioned editor module: ${resolved.id}`);
  }
});

test('unbundled 2D components retain working CommonJS dependency exports', async () => {
  const load = async id => {
    const optimized = metadata.optimized[id];
    assert.ok(optimized, `Missing CommonJS interop bundle: ${id}`);
    return import(pathToFileURL(optimized.file).href);
  };
  const parser = await load('parse-svg-path');
  assert.deepEqual(parser.default('M0 0L1 1'), [['M', 0, 0], ['L', 1, 1]]);
  for (const [id, name, kind] of [
    ['mathjax-full/js/adaptors/liteAdaptor', 'liteAdaptor', 'function'],
    ['mathjax-full/js/handlers/html', 'RegisterHTMLHandler', 'function'],
    ['mathjax-full/js/input/tex', 'TeX', 'function'],
    ['mathjax-full/js/input/tex/AllPackages', 'AllPackages', 'object'],
    ['mathjax-full/js/mathjax', 'mathjax', 'object'],
    ['mathjax-full/js/output/svg', 'SVG', 'function'],
  ]) {
    const bundled = await load(id);
    assert.equal(typeof (bundled[name] ?? bundled.default?.[name]), kind, `Missing export ${name} from ${id}`);
  }
});
