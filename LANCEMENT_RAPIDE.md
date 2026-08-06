# 🚀 Lancement rapide de Typhoon

## Prérequis
- Node.js installé
- Python 3.8+ installé
- Les dépendances backend installées (`pip install -r backend/requirements.txt`)
- Les dépendances frontend installées (`cd frontend && npm install`)

## Démarrage en 2 étapes

### Étape 1 : Lancer le Backend
```bash
cd backend
python -m uvicorn app.main:app --reload --port 8765
```
✅ Le backend est accessible sur http://127.0.0.1:8765

### Étape 2 : Lancer le Frontend (dans un nouveau terminal)
```bash
cd frontend
npm run dev
```
✅ Le frontend est accessible sur http://localhost:3000

## Accès
- **Application** : http://localhost:3000
- **API Backend** : http://127.0.0.1:8765
- **Documentation API** : http://127.0.0.1:8765/docs

## Arrêt
- Appuyez sur `Ctrl+C` dans chaque terminal pour arrêter les serveurs

## Notes
- Le backend utilise le port 8765 par défaut
- Le frontend utilise le port 3000 par défaut
- Les deux serveurs ont le rechargement automatique activé (--reload)