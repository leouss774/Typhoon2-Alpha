import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import './styles/material-theme.css';
import './styles/app.css';

import '@material/web/button/filled-button.js';
import '@material/web/button/outlined-button.js';
import '@material/web/button/text-button.js';
import '@material/web/button/elevated-button.js';
import '@material/web/chips/filter-chip.js';
import '@material/web/dialog/dialog.js';
import '@material/web/icon/icon.js';
import '@material/web/iconbutton/icon-button.js';
import '@material/web/list/list.js';
import '@material/web/list/list-item.js';
import '@material/web/menu/menu.js';
import '@material/web/menu/menu-item.js';
import '@material/web/progress/linear-progress.js';
import '@material/web/switch/switch.js';
import '@material/web/tabs/tabs.js';
import '@material/web/tabs/primary-tab.js';
import '@material/web/textfield/outlined-text-field.js';

/* ── Nettoyage des cibles tactiles Material Web ────────────────────────────
   Les composants @material/web (md-icon-button, md-switch…) insèrent dans
   leur shadow DOM un <span class="touch"></span> : une zone d'emphase
   invisible de 48 px (accessibilité tactile). L'UI Typhoon est pilotée au
   pointeur/clavier — on retire ces spans du DOM. Seuls les spans sont
   visés (le <input class="touch"> du md-switch est fonctionnel : on le
   garde). Un MutationObserver couvre les composants ajoutés dynamiquement
   (menus, panneaux) et les re-rendus Lit. */
function removeTouchSpans(root: Document | ShadowRoot) {
  root.querySelectorAll('span.touch').forEach((el) => el.remove());
}

const observedShadowRoots = new WeakSet<ShadowRoot>();
function watchShadowRoot(el: Element) {
  if (el.shadowRoot && !observedShadowRoots.has(el.shadowRoot)) {
    observedShadowRoots.add(el.shadowRoot);
    removeTouchSpans(el.shadowRoot);
    new MutationObserver(() => removeTouchSpans(el.shadowRoot!)).observe(el.shadowRoot, {
      childList: true,
      subtree: true,
    });
  }
}

const touchCleaner = new MutationObserver((mutations) => {
  for (const m of mutations) {
    m.addedNodes.forEach((node) => {
      if (node instanceof Element) {
        watchShadowRoot(node);
        node.querySelectorAll('*').forEach(watchShadowRoot);
      }
    });
  }
});
touchCleaner.observe(document.documentElement, { childList: true, subtree: true });

document.querySelectorAll('*').forEach(watchShadowRoot);

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
