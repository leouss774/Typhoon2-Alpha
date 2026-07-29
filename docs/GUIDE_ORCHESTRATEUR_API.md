# Guide — Orchestrateur API (collector_agent)

Ce guide accompagne le code livré dans `backend/` : le **collector_agent**, l'orchestrateur qui interroge en parallèle toutes les sources de données du diagnostic Typhoon. C'est le premier maillon du graphe LangGraph décrit dans le README ; les autres agents (`scoring_agent`, `rag_agent`, `digital_twin_agent`) viendront se brancher dessus dans une étape suivante.

Règle absolue de ce livrable : **aucune donnée simulée**. Chaque champ du JSON produit provient soit d'un appel réel à une API (BDNB, Géorisques, IGN, Open-Meteo, Copernicus), soit d'un fichier de lookup réellement téléchargé (DVF). Quand une source échoue (clé absente, route indisponible, jeton non configuré...), le champ correspondant reste `null` et l'erreur exacte est consignée dans `erreurs` — jamais remplacé par une valeur inventée.

## Important — je n'ai pas pu tester en conditions live de mon côté

J'ai vérifié explicitement (via `curl -v`) que le bac à sable dans lequel ce code a été écrit bloque tous les domaines utilisés ici (`data.geopf.fr`, `georisques.gouv.fr`, `api.bdnb.io`, `climate-api.open-meteo.com`, `cds.climate.copernicus.eu`) : la réponse du proxy est explicitement `403 blocked-by-allowlist`. J'ai quand même installé `cdsapi`, créé `$HOME/.cdsapirc` avec votre jeton, et essayé d'instancier `cdsapi.Client()` : il tente de contacter le serveur CDS dès sa création et reste bloqué dans une boucle de nouvelle tentative (jusqu'à 500 essais). Je n'ai donc accès à aucune de ces API en conditions réelles depuis mon environnement, quelle que soit la qualité de la configuration.

Ce que j'ai pu faire à la place : un test hors-ligne (`backend/tests/test_collector_offline.py`) qui simule les réponses de chaque API avec des payloads calqués sur les formats réels documentés par chaque fournisseur, pour valider que toute la logique (géocodage, procédure BDNB en 2 étapes, extraction Copernicus au point le plus proche, gestion d'erreurs partielles Géorisques, assemblage final) est correcte. Il passe intégralement. **La main vous revient pour la suite** : c'est vous qui lancez les vrais appels, sur votre machine, avec un accès internet normal — voir la section CLI plus bas pour tester autant d'adresses que vous voulez sans avoir à me redonner la main à chaque fois.

## Vue d'ensemble des sources

| Source | Compte/clé nécessaire ? | Nature de l'appel | Limites |
|---|---|---|---|
| Géocodage (BAN / Géoplateforme IGN) | Non | REST, instantané | 50 requêtes/s/IP |
| Géorisques v1 | Non | REST, instantané | 1000 requêtes/min/IP |
| IGN Altimétrie (Géoplateforme) | Non | REST, instantané | 5 requêtes/s/IP |
| Open-Meteo Climate API | Non (usage non-commercial) | REST, instantané | Voir open-meteo.com/en/pricing pour un usage commercial |
| BDNB | Non (confirmé par un test réel) | REST, instantané | Offre "Open" ; une clé optionnelle existe pour un quota plus élevé |
| Copernicus Climate Data Store | Oui (compte + jeton) | **Asynchrone** (file d'attente + fichier à télécharger) | Voir cds.climate.copernicus.eu |
| DVF | Non (fichier public à télécharger) | Fichier local, pas d'appel réseau après téléchargement | — |

### 1. Géocodage (adresse → coordonnées + code INSEE)

Aucune inscription. `https://data.geopf.fr/geocodage/search`. Utilisé pour Géorisques, IGN Altitude et Copernicus (BDNB a son propre géocodeur, voir plus bas).

### 2. Géorisques v1

Aucune inscription. Base URL : `https://www.georisques.gouv.fr/api/v1`. Trois routes (`zonage_sismique`, `radon`, `mvt`) sont probables mais pas garanties (portail de doc en JS que je n'ai pas pu inspecter entièrement) — si l'une a changé de chemin, l'erreur est capturée proprement dans `erreurs` sans bloquer le reste. À corriger dans `backend/app/connectors/georisques.py` si besoin, une fois vérifié sur `https://www.georisques.gouv.fr/doc-api`.

### 3. IGN Altimétrie

Aucune inscription. Le connecteur découvre lui-même la ressource altimétrique disponible via `/1.0/resources/?keywords=ALTI`, plutôt que de coder en dur un nom qui peut changer.

### 4. Open-Meteo Climate API

Aucune inscription en usage non-commercial. Fournit des projections CMIP6 (référence 2015-2024 vs projection 2041-2050 dans ce script) — reste le connecteur climatique "rapide" du diagnostic, complété par Copernicus pour des indicateurs plus fins.

### 5. BDNB — procédure en 2 appels, sans clé

Confirmée par un test réel (adresse à Bourgueil, 37) : **aucune clé API n'est nécessaire**, les deux appels répondent sans en-tête `Authorization`. C'est la procédure implémentée dans `backend/app/connectors/bdnb.py` :

```bash
# Etape 1 - geocodeur propre a BDNB (different du geocodeur BAN)
curl -s "https://api.bdnb.io/v1/bdnb/geocodage?q=26+rue+victor+hugo+bourgueil"
# -> cherchez le champ "id", ex. "37031_xxxx_00026" (= cle_interop_adr)

# Etape 2 - donnees du batiment a cette adresse EXACTE
curl -s "https://api.bdnb.io/v1/bdnb/donnees/batiment_groupe_complet/adresse?cle_interop_adr=eq.37031_xxxx_00026" | jq .
```

Plus besoin de deviner le bâtiment le plus proche dans toute la commune (l'ancienne approche de la première version de ce livrable) : cette procédure renvoie directement le ou les bâtiments à l'adresse exacte.

`BDNB_API_KEY` reste disponible en option dans `.env` (le code l'ajoute automatiquement en en-tête `Authorization` si elle est renseignée) au cas où vous obtiendriez plus tard une clé pour un quota plus élevé, mais rien à faire pour l'instant.

**À faire après votre prochain appel réel** : inspecter le JSON de l'étape 2 pour repérer les vrais noms de colonnes de géométrie/matériaux/toiture/étages (dictionnaire complet sur `bdnb.io/documentation/modele_donnees/`) — ce sont ces noms qui alimenteront `digital_twin_agent` par la suite.

### 6. Copernicus Climate Data Store — remplace DRIAS, déjà configuré

DRIAS ne proposant aucune API (téléchargement 100 % manuel derrière un compte), il est remplacé par l'API officielle du **Copernicus Climate Data Store (CDS)**, sur le dataset [**"Climate indicators for Europe from 1940 to 2100"**](https://cds.climate.copernicus.eu/datasets/sis-ecde-climate-indicators) (`sis-ecde-climate-indicators`). La requête que vous avez fournie est déjà en place dans `backend/app/connectors/copernicus.py` (`_REQUEST`) : projections GCM IPSL-CM5A-MR / RCM WRF381P, membre r1i1p1, scénarios RCP4.5 et RCP8.5, agrégations mensuelle/saisonnière/annuelle, sur 7 indicateurs (jours chauds, jours de canicule, jours de gel, précipitations extrêmes et leur fréquence, durée et magnitude des sécheresses météorologiques).

**Compte et jeton, sans rien écrire sur C:** : `cdsapi` lit sa configuration en priorité depuis les variables d'environnement `CDSAPI_URL` / `CDSAPI_KEY`, avant de chercher le fichier `$HOME/.cdsapirc` (`C:\Users\<vous>\.cdsapirc` sous Windows, donc sur C:). Comme vous manquez de place sur C:, ce projet utilise les variables d'environnement plutôt que ce fichier — voir la section [Espace disque](#espace-disque--tout-sous-d) plus bas, qui fournit un script prêt à l'emploi.

Il reste nécessaire d'accepter une fois les conditions d'utilisation du dataset sur le site (onglet "Download" de la page ci-dessus, bas du formulaire) — ça ne télécharge rien sur C:, c'est un simple clic lié à votre compte CDS.

**Rappel de sécurité** : ce jeton a été partagé en clair dans notre conversation. Ce n'est pas grave en soi (c'est votre jeton, votre décision), mais gardez `.cdsapirc` hors de tout dépôt Git (c'est un fichier de `$HOME`, donc naturellement en dehors du repo) et régénérez-le depuis votre profil CDS si vous préférez repartir sur un jeton propre.

**Ce que je n'ai pas pu vérifier moi-même** : j'ai testé la connectivité réseau de mon environnement vers `cds.climate.copernicus.eu` (`curl -v` → `403 blocked-by-allowlist`, identique aux autres API de ce projet), puis j'ai quand même essayé d'instancier `cdsapi.Client()` pour voir si au moins la configuration se chargeait : au lieu d'échouer immédiatement, le client tente de contacter le serveur CDS dès sa création (vérification de version) et reste bloqué dans une boucle de nouvelle tentative (jusqu'à 500 essais, 120 secondes d'attente entre chacun) tant que le réseau est refusé. Je n'ai donc **strictement rien pu exécuter en conditions réelles** ici, ni le téléchargement, ni même la simple création du client. Le format exact du fichier NetCDF reçu (fichier unique ou archive `.zip` regroupant plusieurs fichiers, noms des variables/coordonnées) n'a donc pas pu être vérifié sur une vraie réponse — le code de `read_indicators_at_point` gère les deux cas plausibles (zip ou NetCDF direct, coordonnées `latitude/longitude` ou `lat/lon`) mais restez attentif au premier essai réel : s'il échoue, le message d'erreur vous dira exactement quoi ajuster.

**Nature asynchrone, différente de toutes les autres sources** : contrairement à Open-Meteo (réponse JSON instantanée), CDS met chaque demande en file d'attente — de quelques secondes à plusieurs dizaines de minutes selon la charge du service, avant que le fichier soit prêt à télécharger. Pour ne pas payer ce coût à chaque adresse testée, le connecteur télécharge **une seule fois** le jeu de données complet, le met en cache dans `COPERNICUS_CACHE_DIR` (un marqueur `.download_complete` évite tout re-téléchargement), puis chaque adresse suivante est une simple lecture locale instantanée (via `xarray`) — jamais une valeur recalculée ou approximée, uniquement des lectures du fichier officiel.

### 7. DVF — fichier à télécharger (pas d'API)

DVF reste un lookup local : les données géolocalisées (projet "geo-dvf") se téléchargent gratuitement, sans compte :

```bash
# Exemple pour les Alpes-Maritimes (06), millesime 2024
curl -o 06.csv.gz https://files.data.gouv.fr/geo-dvf/latest/csv/2024/departements/06.csv.gz
gunzip 06.csv.gz
mv 06.csv backend/data/lookup/dvf/06.csv
```

Répétez pour les 6 départements PACA : `04`, `05`, `06`, `13`, `83`, `84`. Le connecteur (`backend/app/connectors/dvf_lookup.py`) lit ensuite ces fichiers directement, sans appel réseau.

## Espace disque — tout sous D:

Si l'espace sur `C:` est limité, deux scripts PowerShell sont fournis dans `backend/` pour que **rien** (venv Python, cache pip, fichiers temporaires, config Copernicus, cache Copernicus/DVF) ne soit écrit sur `C:` :

```powershell
cd D:\Talan\Typhoon-2\backend

# Une seule fois : cree le venv sous D:, installe les dependances avec un
# cache pip sous D:, et configure Copernicus par variables d'environnement
# (pas de fichier .cdsapirc sur C:)
powershell -ExecutionPolicy Bypass -File .\setup_windows_d_drive.ps1
```

Dans **toute nouvelle fenêtre** PowerShell où vous relancez le CLI par la suite (Windows retombe sinon sur ses dossiers habituels sur `C:`) :

```powershell
cd D:\Talan\Typhoon-2\backend
. .\activate_d_drive_session.ps1
```

Ce que ces scripts couvrent déjà automatiquement, sans rien écrire sur `C:` :
- le venv Python (`backend\.venv`) et le cache pip (`.pip-cache`), tous deux sous `D:\Talan\Typhoon-2`
- les fichiers temporaires (`TEMP`/`TMP`), redirigés vers `D:\Talan\Typhoon-2\.tmp`
- la configuration Copernicus (`CDSAPI_URL`/`CDSAPI_KEY`), passée en variables d'environnement plutôt que dans `C:\Users\<vous>\.cdsapirc`
- les caches `backend/data/lookup/copernicus/` et `backend/data/lookup/dvf/`, déjà ancrés sous `D:` par défaut dans `app/core/config.py` (chemins absolus basés sur l'emplacement du projet, pas sur le répertoire courant)

Sur macOS/Linux, ou si vous préférez une installation manuelle, l'équivalent est :

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
export CDSAPI_URL=https://cds.climate.copernicus.eu/api
export CDSAPI_KEY=be100142-59b8-4e65-a3ad-f8525d1ce180
```

La requête Copernicus (`_REQUEST` dans `copernicus.py`) est déjà remplie avec ce que vous avez fourni : rien à compléter de ce côté.

## Tester plusieurs adresses — la main est à vous

Trois façons d'utiliser le script selon ce que vous voulez faire :

```bash
cd backend

# 1) Une seule adresse
python -m app.cli "10 Promenade des Anglais, 06000 Nice"

# 2) Mode interactif : tapez une adresse, Entree, regardez le resultat,
#    tapez la suivante... sans jamais relancer le process (le cache
#    Copernicus reste "chaud" d'une adresse a l'autre)
python -m app.cli
# > Adresse a diagnostiquer (ou 'quit') : 1 Place de l'Hotel de Ville, 13000 Marseille
# > Adresse a diagnostiquer (ou 'quit') : 1 Place de la Liberte, 83000 Toulon
# > Adresse a diagnostiquer (ou 'quit') : quit

# 3) Mode batch : toutes les adresses d'un fichier, a la suite
python -m app.cli --batch adresses_paca_exemple.txt
```

Un fichier `backend/adresses_paca_exemple.txt` est fourni avec une adresse par département PACA (Nice, Marseille, Toulon, Avignon, Gap, Digne-les-Bains) pour démarrer immédiatement en mode batch.

Chaque adresse traitée est sauvegardée dans `backend/out/{code_insee}.json`, et le nombre de sources en erreur (avec le détail) est affiché à chaque fois — vous voyez donc immédiatement quelles sources ont réellement répondu.

## Vérifier la logique sans dépendre des API réelles

```bash
cd backend
PYTHONPATH=. python3 tests/test_collector_offline.py
```

Ce test simule les réponses (payloads calqués sur les formats réels documentés) pour valider : le géocodage, l'altitude, le résumé climatique Open-Meteo, la procédure BDNB en 2 étapes, le refus explicite de Copernicus tant que `_REQUEST_TEMPLATE` n'est pas configuré (pas de valeur inventée), l'extraction Copernicus au point le plus proche sur un fichier NetCDF, la gestion d'erreurs partielles de Géorisques, et l'assemblage final du JSON. C'est ce test qui a servi à valider ce livrable en l'absence d'accès réseau réel de mon côté.

## Explication de chaque fichier

```
backend/
├── requirements.txt              httpx, pandas, cdsapi, xarray, netCDF4...
├── .env.example                   Modele de configuration
├── adresses_paca_exemple.txt      6 adresses PACA pretes pour le mode --batch
├── setup_windows_d_drive.ps1      Installation complete (venv, pip, Copernicus) sous D:
├── activate_d_drive_session.ps1   A relancer dans chaque nouvelle fenetre PowerShell
│
├── app/
│   ├── core/
│   │   ├── config.py               URLs de base, cle BDNB, dossiers de cache
│   │   └── paca.py                 Codes departements PACA + utilitaires
│   │
│   ├── connectors/
│   │   ├── geocoding.py            Adresse -> lat/lon/code INSEE (BAN)
│   │   ├── ign_altitude.py         Altitude au point, decouverte auto de ressource
│   │   ├── open_meteo.py           Climat CMIP6 : reference 2015-2024 vs 2041-2050
│   │   ├── georisques.py           7 endpoints Georisques, erreurs isolees
│   │   ├── bdnb.py                  Procedure en 2 appels : geocodage BDNB -> cle_interop_adr,
│   │   │                           puis donnees/batiment_groupe_complet/adresse
│   │   ├── copernicus.py           Indicateurs climatiques CDS (remplace DRIAS) :
│   │   │                           telechargement PACA une fois + cache + lecture au point
│   │   └── dvf_lookup.py           Lecture d'un CSV DVF local par departement
│   │
│   ├── agents/
│   │   └── collector_agent.py      Orchestrateur : geocode puis lance BDNB, Georisques,
│   │                               IGN, Open-Meteo, Copernicus, DVF en parallele
│   │                               (asyncio.gather), assemble le JSON final,
│   │                               isole chaque echec dans "erreurs"
│   │
│   ├── schemas/
│   │   └── building_data.py        Documente la forme du JSON (TypedDict)
│   │
│   └── cli.py                       Script de test : adresse unique, mode interactif,
│                                    ou mode batch (voir section dediee)
│
├── data/lookup/
│   ├── dvf/                        Ou placer les CSV DVF telecharges (un par departement)
│   └── copernicus/                 Cache auto-genere du fichier NetCDF PACA (rien a placer)
│
├── tests/
│   └── test_collector_offline.py   Test hors-ligne (reseau simule) de toute la chaine
│
└── out/                             JSON generes par le CLI (un fichier par adresse)
```

## Forme du JSON produit

```json
{
  "adresse": {
    "label": "10 Promenade des Anglais 06000 Nice",
    "citycode": "06088",
    "postcode": "06000",
    "city": "Nice",
    "score_geocodage": 0.93,
    "lat": 43.6959,
    "lon": 7.2661
  },
  "departement": "06",
  "departement_nom": "Alpes-Maritimes",
  "dans_perimetre_paca": true,
  "altitude_m": 12.34,
  "bdnb": {
    "cle_interop_adr": "06088_1234_00010",
    "batiment": { "...": "champs bruts BDNB de ce batiment exact" },
    "autres_batiments_meme_adresse": []
  },
  "georisques": {
    "risques_commune": { "...": "..." },
    "catnat": { "...": "..." },
    "zones_inondables": { "...": "..." },
    "cavites": { "...": "..." },
    "zonage_sismique": null,
    "radon": null,
    "mouvements_de_terrain": null,
    "lien_rapport_pdf": "https://www.georisques.gouv.fr/api/v1/rapport_pdf?latlon=7.2661,43.6959",
    "erreurs": []
  },
  "climat_open_meteo": {
    "modeles_utilises": ["EC_Earth3P_HR", "MRI_AGCM3_2_S"],
    "reference_2015_2024": { "temperature_max_moyenne_c": 26.8, "...": "..." },
    "projection_2041_2050": { "temperature_max_moyenne_c": 29.4, "...": "..." }
  },
  "climat_copernicus": { "heatwave_days": "...", "consecutive_dry_days": "...", "...": "..." },
  "dvf_local": null,
  "erreurs": [ { "source": "dvf_local", "erreur": "Fichier DVF introuvable..." } ],
  "genere_le": "2026-07-24T10:00:00+00:00"
}
```

## Prochaines étapes

- Créer `C:\Users\<vous>\.cdsapirc` (Windows) avec l'URL et le jeton CDS, accepter une fois les conditions d'utilisation du dataset, puis relancer une adresse : le tout premier appel Copernicus sera lent (téléchargement complet), les suivants seront instantanés (cache local).
- Continuer à tester avec `python -m app.cli --batch adresses_paca_exemple.txt`, ou en mode interactif pour d'autres adresses de votre choix.
- Si le premier appel Copernicus échoue encore après ça (format de fichier différent de ce qui était anticipé, nom de variable/coordonnée inattendu), le message d'erreur de `read_indicators_at_point` pointera directement le problème à ajuster dans `copernicus.py`.
- Confirmer que le correctif de la route `azi` (paramètre `code_insee` au lieu de `latlon`) fonctionne bien sur votre prochain test ; sinon vérifier le nom/paramètre exact sur `https://www.georisques.gouv.fr/doc-api`.
- Inspecter le JSON BDNB obtenu pour repérer les vrais noms de colonnes géométrie/matériaux (dictionnaire complet sur `bdnb.io/documentation/modele_donnees/`), utiles pour préparer `digital_twin_agent`.
- Télécharger les CSV DVF pour les départements que vous testez, si vous voulez que cette source réponde (optionnel, voir le README principal section Sources de données).
- Brancher ce `collector_agent` dans le `StateGraph` LangGraph complet, suivi de `scoring_agent`.
