import {defineConfig} from 'vite';
import motionCanvas from '@motion-canvas/vite-plugin';
import ffmpeg from '@motion-canvas/ffmpeg';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const framework = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const project = process.env.SBPH_MOTION_PROJECT;
if (!project) throw new Error('Set SBPH_MOTION_PROJECT to a Motion Canvas project.ts');

export default defineConfig({
  root: framework,
  logLevel: 'error',
  plugins: [
    motionCanvas({project, output: process.env.SBPH_MOTION_OUTPUT || path.join(framework, 'output/motion-canvas')}),
    ffmpeg(),
    {
      name: 'sbph-render-entry',
      resolveId(id) { if (id === 'virtual:sbph-project') return '\0sbph-project'; },
      load(id) { if (id === '\0sbph-project') return `export {default} from ${JSON.stringify(project + '?project')}`; },
    },
  ],
  resolve: {
    alias: Object.fromEntries(['core', '2d', 'ui', 'ffmpeg'].map(name => [`@motion-canvas/${name}`, path.join(framework, 'node_modules/@motion-canvas', name)])),
    dedupe: ['@motion-canvas/core', '@motion-canvas/2d', '@motion-canvas/ui', 'preact', '@preact/signals'],
  },
  optimizeDeps: {
    // The 2D editor loads through a versioned /@id URL; keep it out of Vite's optimizer.
    exclude: ['@motion-canvas/2d'],
    include: [
      '@motion-canvas/core', '@motion-canvas/ui', '@motion-canvas/ffmpeg/lib/client',
      // CommonJS dependencies of the unbundled 2D components still need interop.
      'parse-svg-path',
      'mathjax-full/js/adaptors/liteAdaptor', 'mathjax-full/js/handlers/html',
      'mathjax-full/js/input/tex', 'mathjax-full/js/input/tex/AllPackages',
      'mathjax-full/js/mathjax', 'mathjax-full/js/output/svg',
    ],
  },
  server: {host: '127.0.0.1', strictPort: false, fs: {allow: [framework, path.dirname(project)]}},
});
