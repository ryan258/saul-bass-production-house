/* Standalone wordless example. Only Node built-ins; no fonts or borrowed art. */
const fs = require('node:fs');
const path = require('node:path');
const edit = JSON.parse(fs.readFileSync(path.join(__dirname, '../data/edit.json'), 'utf8'));
const colors = edit.palette;
const clamp = x => Math.max(0, Math.min(1, x));
const ease = x => {const t = clamp(x); return t * t * (3 - 2 * t);};

function draw(scene, localFrame) {
  const u = clamp(localFrame / (scene.end - scene.start - 1));
  let x = 128, bridge = 0, answered = false;
  if (scene.kind === 'approach') x = 35 + 93 * ease(u / .85);
  else if (scene.kind === 'bridge') bridge = ease(u / .85);
  else if (scene.kind === 'arrival') {
    bridge = 1; x = 128 + 154 * ease(u / .78); answered = u >= .78;
  } else throw Error('Unknown example shot kind: ' + scene.kind);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${edit.width}" height="${edit.height}" viewBox="0 0 320 180" role="img">
    <title>The Signal</title><desc>${scene.action}</desc>
    <rect width="320" height="180" fill="${colors.background}"/>
    <path d="M20 90H138M182 90H300" fill="none" stroke="${colors.track}" stroke-width="5"/>
    <rect x="138" y="87.5" width="${44 * bridge}" height="5" fill="${colors.answer}"/>
    <circle cx="282" cy="90" r="20" fill="${answered ? colors.answer : colors.background}" stroke="${colors.track}" stroke-width="3"/>
    <rect x="${x - 7}" y="83" width="14" height="14" fill="${colors.signal}"/>
  </svg>`;
}

async function init() {}
function shotFrame(id, localFrame) {
  const scene = edit.scenes.find(s => s.id === id);
  if (!scene || !Number.isInteger(localFrame)) throw Error('Invalid shot or frame');
  // Handles clamp to this shot's endpoint pose; they never borrow another shot.
  return draw(scene, localFrame);
}
function frame(n) {
  if (!Number.isInteger(n) || n < 0 || n >= edit.frames) throw Error('Frame outside edit');
  const scene = edit.scenes.find(s => n >= s.start && n < s.end);
  return shotFrame(scene.id, n - scene.start);
}
module.exports = {init, frame, shotFrame};
