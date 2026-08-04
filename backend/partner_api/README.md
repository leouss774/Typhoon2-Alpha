# Typhoon Partner API

API dediee aux projets tiers qui veulent lancer une analyse de risque
climatique sur une adresse et recuperer un score exploitable, sans passer
par le backend interne (`app.main:app`) qui sert le jumeau numerique 3D.

Reutilise le meme moteur (collecte BDNB/Georisques/IGN/Open-Meteo +
scoring + recommandations RAG) que le reste du projet Typhoon, exposé
avec un contrat de reponse dedie (pas de geometrie 3D, pas de champs
internes de tracabilite).

## Lancer le service

Depuis `backend/` (meme prerequis que l'API interne : venv installe,
`.env` rempli — voir `docs/GUIDE_ORCHESTRATEUR_API.md`) :

```bash
cd backend
uvicorn partner_api.main:app --reload --port 8001
```

Le service tourne sur un port distinct (`8001`) de l'API interne
(`8000` par defaut) : les deux peuvent tourner en parallele sur la meme
machine. Documentation interactive : `http://localhost:8001/docs`.

## Endpoint

### `POST /v1/analyze`

Requete :

```json
{ "address": "12 rue des Lilas, 33000 Bordeaux" }
```

Reponse (extrait) :

```json
{
  "adresse": {
    "input": "12 rue des Lilas, 33000 Bordeaux",
    "label": "12 Rue des Lilas 33000 Bordeaux",
    "citycode": "33063",
    "postcode": "33000",
    "city": "Bordeaux",
    "lat": 44.84,
    "lon": -0.58
  },
  "score_global": 58,
  "niveau_global": "modere",
  "confidence": { "score": 72, "niveau": "bonne", "n_sources_disponibles": 9, "n_sources_total": 9 },
  "zones": {
    "fondations": {
      "risque": 78,
      "niveau": "eleve",
      "alea_principal": "Retrait-gonflement des argiles",
      "justification": "...",
      "recommandations": [
        { "mesure": "Renforcement des fondations par micropieux", "cout_estime": "9000-16000€", "...": "..." }
      ]
    },
    "murs_nord": { "...": "..." },
    "murs_sud": { "...": "..." },
    "murs_est": { "...": "..." },
    "murs_ouest": { "...": "..." },
    "toiture": { "...": "..." },
    "sous_sol": { "...": "..." }
  },
  "risques_par_alea": {
    "argile": { "label": "Retrait-gonflement des argiles", "risque": 65, "niveau": "modere", "justification": "..." },
    "inondation": { "...": "..." },
    "mouvement_terrain": { "...": "..." },
    "sismique": { "...": "..." },
    "radon": { "...": "..." },
    "canicule": { "...": "..." },
    "precipitation": { "...": "..." },
    "feu_foret": { "...": "..." }
  },
  "projection_2050": {
    "score_global": 81,
    "niveau_global": "eleve",
    "zones": { "...": "meme structure, projetee a horizon 2050" },
    "risques_par_alea": { "...": "..." }
  },
  "erreurs_sources": [],
  "genere_le": "2026-08-04T10:00:00+00:00"
}
```

`score_global` / `risque` sont sur une echelle 0-100 ; `niveau` /
`niveau_global` vaut `tres faible`, `faible`, `modere`, `eleve` ou
`tres eleve` (bandes documentees dans `app.scoring.risk_model`).

`erreurs_sources` liste les sources de collecte indisponibles pour cette
adresse (ex. Copernicus non configure) : une source en erreur n'empeche
jamais la reponse, elle est juste absente du calcul — regardez
`confidence` pour savoir a quel point s'y fier.

Codes d'erreur :
- `422` — adresse non geocodable (texte incomplet, hors de France...).
- `502` — echec d'une etape du pipeline (voir `detail` du message).

## Exemple

```bash
curl -X POST http://localhost:8001/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{"address": "12 rue des Lilas, 33000 Bordeaux"}'
```

## Limites actuelles

- **Pas d'authentification.** Choix explicite le temps d'identifier les
  partenaires reels — a ajouter (cle API par partenaire, header
  `X-API-Key`) avant toute exposition hors du reseau interne.
- **Temps de reponse** : l'appel enchaine collecte reseau (BDNB,
  Georisques, IGN, Open-Meteo, eventuellement Copernicus) puis generation
  des recommandations par zone via Mistral (RAG) — plusieurs secondes a
  quelques dizaines de secondes selon le nombre de zones a risque.
  Un partenaire avec des besoins de latence stricts peut appeler
  directement `app.scoring.risk_model.compute_risk_scores` sans
  recommandations pour une reponse plus rapide (a exposer en variante
  si le besoin se confirme).
- Depend des memes cles/CSV que le backend interne (`MISTRAL_API_KEY`
  pour les recommandations, CSV DVF locaux optionnels) — voir
  `docs/GUIDE_ORCHESTRATEUR_API.md`.
