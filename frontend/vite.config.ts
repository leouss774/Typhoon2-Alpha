import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const BIM_VIEWER_DIST = path.join(ROOT, 'bim-viewer', 'dist');

const BIM_MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
  '.wasm': 'application/wasm',
  '.gltf': 'model/gltf+json',
  '.glb': 'model/gltf-binary',
  '.bin': 'application/octet-stream',
};

/**
 * Sert le build statique de frontend/bim-viewer/dist sous /bim-viewer/.
 *
 * En dev : middleware connect sur le dev server Vite (avec fallback SPA vers
 * index.html — le viewer est un routeur Vue en mode history).
 * En build : copie dist/bim-viewer dans l'outDir de Vite pour la prod.
 */
function bimViewerPlugin(): Plugin {
  return {
    name: 'typhoon-bim-viewer-static',
    configureServer(server) {
      server.middlewares.use('/bim-viewer', (req, res, next) => {
        if (!fs.existsSync(BIM_VIEWER_DIST)) {
          console.warn('[bim-viewer] dist introuvable — lancer: cd frontend/bim-viewer && npm run build');
          next();
          return;
        }
        const url = new URL(req.url || '/', 'http://localhost');
        let rel: string;
        try {
          rel = decodeURIComponent(url.pathname.replace(/^\/+/, ''));
        } catch {
          res.statusCode = 400;
          res.end('Bad Request');
          return;
        }
        if (!rel) rel = 'index.html';
        // Sécurité : le chemin résolu doit rester DANS dist (un client non
        // normalisant peut envoyer des segments '..' — /bim-viewer/../../vite.config.ts).
        const resolved = path.resolve(BIM_VIEWER_DIST, rel);
        if (resolved !== BIM_VIEWER_DIST && !resolved.startsWith(BIM_VIEWER_DIST + path.sep)) {
          res.statusCode = 404;
          res.end('Not Found');
          return;
        }
        let file = resolved;
        const ext = path.extname(rel).toLowerCase();
        if (!fs.existsSync(file) || !fs.statSync(file).isFile()) {
          if (ext) {
            // Asset manquant : 404 propre (surtout pas de fallback HTML, qui
            // ferait planter les loaders JSON/wasm du viewer en 'Unexpected token <')
            res.statusCode = 404;
            res.end('Not Found');
            return;
          }
          // Fallback SPA uniquement pour les routes (routes history du
          // viewer : /projects/:projectId, /projects, /)
          file = path.join(BIM_VIEWER_DIST, 'index.html');
        }
        res.setHeader('Content-Type', BIM_MIME[path.extname(file)] || 'application/octet-stream');
        res.setHeader('Cache-Control', 'no-cache');
        fs.createReadStream(file).pipe(res);
      });
    },
    closeBundle() {
      // Production : embarquer le viewer dans le dist Vite
      if (!fs.existsSync(BIM_VIEWER_DIST)) return;
      const outDir = path.resolve(ROOT, 'dist');
      fs.cpSync(BIM_VIEWER_DIST, path.join(outDir, 'bim-viewer'), { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [react(), bimViewerPlugin()],
  server: {
    port: 5173,
  },
});
