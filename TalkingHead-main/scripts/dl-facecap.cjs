// Télécharge facecap.glb (visage humain avec morphs de bouche) via l'API GitHub
// (endpoint contents -> base64), plus fiable que raw.githubusercontent ici.
const fs = require('fs');
const path = require('path');
const out = path.join(__dirname, '..', 'public', 'models', 'facecap.glb');
const log = path.join(__dirname, '..', '_dl.log');
const url = 'https://api.github.com/repos/mrdoob/three.js/contents/examples/models/gltf/facecap.glb?ref=dev';

function save(msg) {
  try { fs.writeFileSync(log, String(msg)); } catch (e) { /* ignore */ }
}

(async () => {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(120000) });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const json = await res.json();
    const buf = Buffer.from(json.content, 'base64');
    fs.writeFileSync(out, buf);
    save('OK ' + res.status + ' wrote ' + buf.length + ' bytes\n' + JSON.stringify(json.name));
    console.log('WROTE', buf.length);
  } catch (e) {
    save('ERR ' + e.message);
    console.error('ERR', e.message);
    process.exit(1);
  }
})();
