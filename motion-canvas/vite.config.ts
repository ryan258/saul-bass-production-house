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
    include: ['@motion-canvas/core', '@motion-canvas/2d', '@motion-canvas/ui', '@motion-canvas/2d/editor', '@motion-canvas/ffmpeg/lib/client'],
  },
  server: {host: '127.0.0.1', strictPort: true, fs: {allow: [framework, path.dirname(project)]}},
});
