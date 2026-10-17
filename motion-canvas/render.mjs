import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createServer} from 'vite';
import {chromium} from 'playwright-core';

// Use Motion Canvas's own Renderer and ImageExporter. Playwright only hosts the
// browser canvas; it does not implement a clock, tween engine, or screenshot loop.
const framework = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const [mode, projectArg, outputArg, optionsArg] = process.argv.slice(2);
if (!['render', 'editor', 'check-editor'].includes(mode) || !projectArg) throw Error('Usage: node render.mjs render|editor|check-editor project.ts [output]');
const project = path.resolve(projectArg);
const proofFile = path.join(path.dirname(project), 'proof.json');
const config = fs.existsSync(proofFile) ? JSON.parse(fs.readFileSync(proofFile, 'utf8')) : {};
if (optionsArg) Object.assign(config,JSON.parse(optionsArg));
process.env.SBPH_MOTION_PROJECT = project;
if (outputArg) process.env.SBPH_MOTION_OUTPUT = path.resolve(outputArg);
const server = await createServer({configFile: path.join(framework, 'motion-canvas/vite.config.ts'), server: {port: 9139}});
let browser;
try {
  await server.listen();
  const url = server.resolvedUrls.local[0];
  if (mode === 'editor') {
    console.log('Motion Canvas editor: ' + url);
    console.log('Audio is the exact source window. Stop with Ctrl-C.');
    await new Promise(resolve => {process.once('SIGINT', resolve); process.once('SIGTERM', resolve);});
  } else {
    let executablePath = process.env.SBPH_CHROMIUM;
    if (!executablePath && !fs.existsSync(chromium.executablePath())) {
      const chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
      if (fs.existsSync(chrome)) executablePath = chrome;
      else throw Error('No Chromium found. Set SBPH_CHROMIUM; no browser is downloaded automatically.');
    }
    browser = await chromium.launch({executablePath, headless: true, args: ['--force-color-profile=srgb']});
    const page = await browser.newPage({viewport: {width: 1280, height: 720}});
    const pageErrors = [];
    const metaFrames = [];
    page.on('websocket', socket => {
      for (const direction of ['framesent','framereceived']) socket.on(direction, frame => {
        try {const item=JSON.parse(String(frame.payload));if(item.event?.startsWith('motion-canvas:meta'))metaFrames.push({direction,event:item.event,source:item.data?.source});} catch {}
      });
    });
    page.on('requestfailed', request => console.error('Request failed: ' + request.url() + ' ' + request.failure()?.errorText));
    page.on('console', message => {if (message.type() === 'error' || message.text().startsWith('FRAME ')) console.log(message.text());});
    page.on('pageerror', error => {pageErrors.push(error.message);console.error(error.stack);});
    if (mode === 'check-editor') {
      await page.goto(url);
      await page.waitForSelector('canvas', {timeout: 30000, state: 'attached'}).catch(async error => {
        console.error((await page.locator('body').innerText()).slice(0,4000));
        if (outputArg) {fs.mkdirSync(outputArg,{recursive:true});await page.screenshot({path:path.join(outputArg,'editor-failure.png')});}
        throw error;
      });
      const text=await page.locator('body').innerText();
      const metaPath=path.join(path.dirname(project),(config.scene||'shutdown')+'.meta');
      const originalMeta=JSON.parse(fs.readFileSync(metaPath,'utf8'));
      const updatedMeta=structuredClone(originalMeta);
      const testCue=config.testCue||'reach';
      updatedMeta.timeEvents.find(event=>event.name===testCue).targetTime+=1/config.fps;
      try {
        await page.evaluate(async ({url,data}) => {const meta=(await import(url)).default;await meta.saveData(data);}, {url:'/@fs'+metaPath+'?import',data:updatedMeta});
        const saved=JSON.parse(fs.readFileSync(metaPath,'utf8'));
        if (saved.timeEvents.find(event=>event.name===testCue).targetTime!==updatedMeta.timeEvents.find(event=>event.name===testCue).targetTime)throw Error('Cue edit was not persisted');
        await page.evaluate(async ({url,data}) => {const meta=(await import(url)).default;await meta.saveData(data);}, {url:'/@fs'+metaPath+'?import',data:originalMeta});
      } catch (error) {
        fs.writeFileSync(metaPath,JSON.stringify(originalMeta,null,2));
        console.error(JSON.stringify({metaFrames}));throw error;
      }
      if (pageErrors.length) throw Error(JSON.stringify(pageErrors));
      if (outputArg) {
        fs.mkdirSync(outputArg,{recursive:true});
        await page.screenshot({path:path.join(outputArg,'editor.png')});
      }
      console.log(JSON.stringify({editorLoaded:true,cueSaveAndRestore:true,canvasCount:await page.locator('canvas').count(),text:text.slice(0,2000),pageErrors,metaFrames}));
    } else {
    await page.goto(new URL('motion-canvas/render.html', url).href);
    await page.waitForFunction(() => window.sbphReady, null, {timeout: 60000});
    const started = performance.now();
    const result = await page.evaluate(options => window.sbphRender(options), config);
    if (pageErrors.length) throw Error(JSON.stringify(pageErrors));
    console.log(JSON.stringify({...result, renderSeconds: (performance.now() - started) / 1000}));
    }
  }
} finally {
  if (browser) await browser.close();
  await server.close();
}
