// =============================================================================
//   TYPHOON — Configuration partagée des fronts.
//   Le backend Python (app.main:app) tourne sur le port 8765 — c'est la seule
//   référence de port pour tous les fronts (voir README.md "port 8765
//   obligatoire"). Chaque page inclut ce fichier dans son <head>.
// =============================================================================
window.TYPHOON_API = window.TYPHOON_API || 'http://127.0.0.1:8765';
