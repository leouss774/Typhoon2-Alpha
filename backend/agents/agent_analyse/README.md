# 🏠 Digital Twin Agent — Mistral AI Integration

Agent IA de **jumeau numérique immobilier et climatique** pour la France.
Prend les données brutes du risk engine (BDNB/Géorisques/IGN/Open-Meteo/CATNAT/DVF/DRIAS) et génère un JSON structuré de risques et recommandations.

---

## Architecture

```
donneesRiskEngine + formulaireClient
        │
        ▼
┌─────────────────────────────────────────────────────┐
│              DigitalTwinAgent                       │
│                                                     │
│  ① genererAnalyse()  ──► mistral-large-latest      │
│     • Analyse complète des risques actuels          │
│     • Projection 2050 (RCP4.5 + RCP8.5)            │
│     • Recommandations chiffrées et priorisées       │
│     • Score global A→F                              │
│                                                     │
│  ② testVulnerabilite() ──► mistral-small-latest    │
│     • Appel rapide (~3-5s)                          │
│     • Verdict : SUR/ACCEPTABLE/VIGILANCE/DANGER     │
│     • Déclenché au clic sur la carte                │
│                                                     │
│  ③ projection2050() ──► mistral-large-latest       │
│     • Risques aggravés selon DRIAS                  │
│     • 2 scénarios : RCP 4.5 et RCP 8.5             │
└─────────────────────────────────────────────────────┘
        │
        ▼
  JSON structuré → 2D/3D simulation + carte des risques
```

---

## Installation

```bash
pip install -r requirements.txt
```

---

## Configuration

**Option 1 : Variable d'environnement (recommandé)**
```bash
set MISTRAL_API_KEY=votre-clé-api-mistral
```

**Option 2 : Modifier `config.py`**
```python
MISTRAL_API_KEY = "votre-clé-api-mistral"
```

---

## Utilisation

### En tant que module Python

```python
from agent.digital_twin_agent import DigitalTwinAgent

agent = DigitalTwinAgent(api_key="votre-clé")

# Analyse principale
resultat = agent.genererAnalyse(donnees_risk_engine, formulaire)

# Test de vulnérabilité rapide (clic sur carte)
verdict = agent.testVulnerabilite(lat=48.84, lon=2.29, adresse="Paris 15e")

# Projection 2050
projection = agent.projection2050(resultat, donnees_drias, scenario="rcp85")

# Analyse complète (présent + 2 scénarios 2050)
complet = agent.analyseComplete(donnees_risk_engine, formulaire, donnees_drias)
```

### En ligne de commande

```bash
# Mode démo (sans clé API)
python main.py --demo

# Tests sur 3 adresses réelles
python main.py --test

# Analyse depuis un fichier JSON
python main.py --input mon_adresse.json --output resultat.json --api-key sk-...

# Test de vulnérabilité rapide
python main.py --vuln --lat 43.71 --lon 7.26 --api-key sk-...

# Avec projection 2050
python main.py --input adresse.json --2050 --scenario rcp85
```

---

## Structure du projet

```
digital-twin-agent/
├── config.py                    # Clé API et paramètres Mistral
├── main.py                      # Point d'entrée CLI
├── requirements.txt
├── agent/
│   ├── digital_twin_agent.py    # Classe principale DigitalTwinAgent
│   ├── prompts.py               # Prompts système Mistral (3 types)
│   ├── schema.py                # Schéma JSON du contrat
│   └── fallback.py              # Parsing robuste + fallback
├── tests/
│   ├── test_agent.py            # Tests sur 3 adresses réelles
│   └── test_data.py             # Données de test (Paris, Bordeaux, Nice)
└── examples/
    └── exemple_integration.py   # Intégration pour carte/simulation 2D/3D
```

---

## JSON de sortie — Structure principale

```json
{
  "meta": { "adresse", "coordonnees", "sources_donnees", ... },
  "bien": { "type", "surface_m2", "annee_construction", "dpe_classe", ... },
  "risques_actuels": {
    "inondation": { "niveau", "score", "present_zone_ppr", "explication", ... },
    "seisme": { ... },
    "incendie_foret": { ... },
    "chaleur_extreme": { ... },
    ... (10 risques au total)
  },
  "risques_futurs_2050": {
    "scenario_rcp45": { ... },
    "scenario_rcp85": { ... }
  },
  "score_global": {
    "note": 45,           // 0-100
    "classe": "C",        // A à F
    "score_resilience": 55,
    "score_exposition": 45,
    "score_vulnerabilite": 40
  },
  "recommandations": {
    "urgentes": [ { "id", "titre", "description", "cout_estime_eur", "priorite", ... } ],
    "court_terme": [ ... ],
    "moyen_terme": [ ... ],
    "long_terme_2050": [ ... ]
  },
  "simulation_periode": {
    "evenements_probables": [ ... ],
    "cout_risque_cumule_estime": 85000,
    "indice_assurabilite": "standard"
  },
  "donnees_marche": { "prix_m2_median_commune", "impact_risque_sur_valeur_pct", ... }
}
```

---

## Robustesse & Fallback

L'agent gère automatiquement les cas où Mistral retourne un JSON mal formé :
1. **Parsing direct** → tentative json.loads()
2. **Extraction code fence** → détecte les ` ```json ... ``` `
3. **Extraction par accolades** → cherche `{...}` dans le texte
4. **Nettoyage agressif** → supprime commentaires, virgules traînantes
5. **Fallback complet** → JSON minimal valide avec flag `_erreur`

**Retry automatique** : 3 tentatives avec backoff exponentiel sur les erreurs 429/5xx.

---

## Intégration carte & simulation

Voir `examples/exemple_integration.py` pour la fonction `exemple_integration_simulation()`
qui retourne les données formatées pour :
- **Carte des risques** : zones colorées par score, markers géolocalisés
- **Simulation 2D/3D** : données de résilience, événements probables, évolution 2050
- **Deux scénarios climatiques** : RCP 4.5 et RCP 8.5 comparables

---

## Sources de données supportées

| Source | Données |
|--------|---------|
| **BDNB** | DPE, consommation énergie, matériaux |
| **Géorisques** | PPR, zone sismique, inondation, RGA |
| **IGN** | Altitude, distances, topographie |
| **Open-Meteo** | Températures, précipitations, événements extrêmes |
| **CATNAT** | Historique arrêtés catastrophes naturelles |
| **DVF** | Prix immobiliers, transactions, tendances |
| **DRIAS** | Projections climatiques 2050 (RCP 4.5 & 8.5) |
