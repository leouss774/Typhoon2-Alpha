# PLAN D'IMPLÉMENTATION — Diagnostic Adresse → Géorisques → Rapport

> Objectif : un flux simple et fiable, **adresse saisie → géocodage → appel Géorisques → rapport de risques affiché**, sur le modèle de GeoRisk, mais branché sur votre backend existant (`app/connectors`, `app/api/routes/diagnostic.py`) plutôt que reconstruit à part. C'est le socle minimal avant de brancher BDNB/RNB/DVF (voir `typhoon_sovereign_geo_engine_SPEC.md` pour la suite).

---

## 0. Périmètre exact

**Dans le scope :**
1. Champ de saisie d'adresse (texte libre, France uniquement)
2. Géocodage adresse → coordonnées + code commune/parcelle
3. Appel à l'API Géorisques avec ces coordonnées
4. Normalisation de la réponse en un contrat interne stable
5. Rapport affiché : liste des aléas, niveau, historique, source

**Hors scope (phases suivantes) :**
- BDNB / RNB (géométrie, matériaux) → SPEC souverain, sprint 0-1
- Score pondéré multi-source, DVF, DPE → sprints suivants
- Génération PDF, rapport promoteur, RAG recommandations

---

## 1. Flux complet

```
[Front] saisie adresse
      │
      ▼
[Back] GET /diagnostic/adresse?q=...
      │
      ├─ 1. Géocodage : API Adresse (BAN, adresse.data.gouv.fr) — gratuit, sans clé, sovereign FR
      │      → { lat, lon, code_insee, label_normalise, score_geocodage }
      │      Si aucun résultat ou score bas (<0.5) → 422 explicite, PAS de fallback silencieux
      │
      ├─ 2. Appel Géorisques (déjà partiellement dans app/connectors/) :
      │      GET https://www.georisques.gouv.fr/api/v1/gaspar/risques?lat={lat}&lon={lon}
      │      + endpoints spécifiques si besoin (azi, catnat, rga, sismicite)
      │
      ├─ 3. Normalisation → RisqueReport (contrat Pydantic, §3)
      │
      └─ 4. Retour JSON complet au front
      │
      ▼
[Front] Affichage : carte + liste d'aléas + fiche détail (comme GeoRisk)
```

---

## 2. Géocodage — brique manquante à ajouter

GeoRisk et Géorisques natif prennent une adresse texte directement ; votre backend actuel (`diagnostic.py`) attend déjà des `bounds`/coordonnées pour la zone, mais **il n'existe pas encore de connecteur adresse → coordonnées** pour le mode "bien unique". C'est la première brique à écrire :

```python
# app/connectors/geocodage_connector.py
import httpx

BASE_URL = "https://api-adresse.data.gouv.fr/search/"

async def geocoder_adresse(adresse: str) -> GeocodageResult:
    """
    API Adresse Base Adresse Nationale (BAN) — Etalab, gratuite, sans clé.
    Aucun fallback si non trouvé : erreur explicite renvoyée au front.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(BASE_URL, params={"q": adresse, "limit": 1})
        r.raise_for_status()
        data = r.json()
        if not data.get("features"):
            raise AdresseNonTrouveeError(adresse)
        feat = data["features"][0]
        lon, lat = feat["geometry"]["coordinates"]
        props = feat["properties"]
        return GeocodageResult(
            lat=lat, lon=lon,
            label=props["label"],
            code_insee=props.get("citycode"),
            score=props.get("score"),
        )
```

**Pourquoi la BAN et pas Nominatim/Google** : source française officielle (Etalab/IGN), déjà cohérente avec le reste de votre stack souverain, pas de clé, pas de quota payant, résultats déjà normalisés à l'adresse française (numéro, voie, code INSEE).

---

## 3. Contrat de sortie — `RisqueReport`

```python
from pydantic import BaseModel
from datetime import date
from enum import Enum

class NiveauRisque(str, Enum):
    TRES_FAIBLE = "tres_faible"
    FAIBLE = "faible"
    MODERE = "modere"
    ELEVE = "eleve"
    CRITIQUE = "critique"

class AleaDetail(BaseModel):
    code: str                    # ex: "inondation", "rga", "sismicite", "feu_foret", "radon"
    libelle: str                 # libellé affichable FR
    present: bool                # l'aléa concerne-t-il la commune/parcelle
    niveau: NiveauRisque | None  # None si Géorisques ne fournit pas de gradation pour cet aléa
    zonage: str | None           # ex: zone sismique "3 - modérée"
    catnat_historique: list[dict] | None  # arrêtés CatNat passés, si dispo
    source: str = "georisques"
    url_detail: str | None       # lien direct vers la fiche Géorisques

class RisqueReport(BaseModel):
    adresse_saisie: str
    adresse_normalisee: str
    lat: float
    lon: float
    code_insee: str
    date_generation: date
    alea_count: int
    aleas: list[AleaDetail]
    avertissement: str = (
        "Ce rapport agrège les données publiques Géorisques. "
        "Il ne remplace pas l'État des Risques (ERRIAL) obligatoire à la vente/location."
    )
```

**Point important, repris de l'audit précédent** : Géorisques lui-même précise que son périmètre diffère du formulaire réglementaire ERRIAL — donc le champ `avertissement` doit être **affiché, pas juste stocké**, pour ne pas laisser croire à un rapport réglementaire.

---

## 4. Endpoint API

```
GET /diagnostic/adresse?q=14+avenue+des+palmiers+nice

→ 200 OK
{
  "adresse_saisie": "14 avenue des palmiers nice",
  "adresse_normalisee": "14 Avenue des Palmiers 06000 Nice",
  "lat": 43.7102, "lon": 7.2620,
  "code_insee": "06088",
  "date_generation": "2026-08-02",
  "alea_count": 4,
  "aleas": [
    {"code":"inondation","libelle":"Inondation","present":true,"niveau":"eleve", ...},
    {"code":"rga","libelle":"Retrait-gonflement des argiles","present":true,"niveau":"modere", ...},
    {"code":"sismicite","libelle":"Sismicité","present":true,"niveau":"faible","zonage":"Zone 2 - faible", ...},
    {"code":"radon","libelle":"Radon","present":true,"niveau":null,"zonage":"Catégorie 2", ...}
  ],
  "avertissement": "..."
}

→ 422 si adresse non géocodée : {"error":"adresse_non_trouvee","detail":"..."}
→ 502 si Géorisques indisponible : {"error":"source_indisponible","source":"georisques","detail":"..."}
```

**Règle fail-soft** : si un sous-endpoint Géorisques échoue (ex. RGA dispo, sismicité en timeout), on renvoie tout de même le rapport avec cet aléa marqué `present: null` / erreur explicite dans un champ `erreurs_partielles`, jamais un 500 global ni une valeur inventée.

```python
class RisqueReportPartiel(RisqueReport):
    erreurs_partielles: list[str] = []  # ex: ["sismicite: timeout Géorisques"]
```

---

## 5. Rapport affiché (front) — inspiré GeoRisk, structure

```
┌───────────────────────────────────────────┐
│  14 Avenue des Palmiers, 06000 Nice        │
│  Généré le 02/08/2026                      │
├───────────────────────────────────────────┤
│  🌊 Inondation           ● Élevé            │
│  🏗️ Argiles (RGA)        ● Modéré           │
│  🌍 Sismicité            ● Faible (zone 2)  │
│  ☢️ Radon                 zone catégorie 2  │
│  🔥 Feu de forêt          Non concerné       │
├───────────────────────────────────────────┤
│  Historique CatNat : 3 arrêtés (1999, 2011,│
│  2020) — inondation, tempête                │
├───────────────────────────────────────────┤
│  ⚠️ Ce rapport n'est pas l'ERRIAL officiel. │
│  Source : Géorisques (MTE)                  │
└───────────────────────────────────────────┘
```

Composant front minimal (React ou HTML statique selon ce que vous utilisez déjà) :
- Un champ `AdresseSearch` (debounce, autocomplete optionnelle via la même API BAN — bonus, pas obligatoire en V1)
- Une carte de rapport `RisqueCard` par aléa, couleur = bande D03 unifiée (cf. spec sovereign engine, §6) pour rester cohérent avec le futur module zone
- Bloc avertissement toujours visible, jamais masqué dans un tooltip

---

## 6. Étapes de build (dans l'ordre, testable à chaque étape)

| Étape | Livrable | Test de validation |
|---|---|---|
| 1 | `geocodage_connector.py` + test avec adresse réelle (fixture enregistrée) | Adresse valide → lat/lon corrects ; adresse absurde → `AdresseNonTrouveeError` |
| 2 | `georisques_connector.py` généralisé (déjà partiellement existant — vérifier `collector_agent.py`) : accepte lat/lon, retourne les aléas bruts | Coordonnées connues (ex. Nice) → réponse Géorisques réelle capturée en fixture |
| 3 | Normalisation brute Géorisques → `AleaDetail` (mapping des codes Géorisques vers vos libellés/bandes D03) | Table de mapping testée unitairement, aucun aléa "inventé" si absent de la réponse |
| 4 | Endpoint `GET /diagnostic/adresse` complet, avec gestion des 3 cas d'erreur (non trouvé / partiel / total) | Test API : 200 nominal, 422 adresse invalide, 200 avec `erreurs_partielles` si Géorisques partiellement down (mock) |
| 5 | Front : formulaire adresse + affichage `RisqueReport` | Test manuel sur 3 adresses réelles (Nice, zone rurale RGA, zone littorale) |
| 6 | Ajout lien "Voir la fiche complète Géorisques" (`url_detail`) par aléa, comme GeoRisk le fait | Vérifier que chaque lien pointe vers la bonne fiche officielle |

---

## 7. Différences volontaires avec GeoRisk

- **Géocodage propre en amont** (GeoRisk semble s'appuyer sur une saisie plus contrainte) — vous gérez l'adresse texte libre française dès l'entrée.
- **Erreurs partielles explicites** plutôt qu'un échec total si une seule sous-API Géorisques est indisponible.
- **Bandes de risque unifiées (D03)** dès cette V1, pour éviter la dette de vocabulaire déjà identifiée dans votre module zone.
- **Avertissement ERRIAL toujours visible**, pas seulement mentionné en page à propos.
- **Aucune dépendance à un hébergeur non-européen** (contrairement à Vercel pour GeoRisk) — reste sur votre infra existante.

---

## 8. Prompt court (agent de code)

> Implémente le flux `adresse → géocodage BAN → Géorisques → RisqueReport` décrit dans ce document. Commence par `geocodage_connector.py` (§2) avec un test sur une adresse réelle. Puis étends le connecteur Géorisques existant pour accepter lat/lon (§4). Construis le contrat `RisqueReport`/`AleaDetail` (§3) avec le mapping vers les bandes D03 unifiées. Termine par l'endpoint `GET /diagnostic/adresse` avec gestion explicite des 3 cas d'erreur (introuvable / partiel / total) — aucune valeur simulée en cas d'échec, toujours un statut explicite par aléa.
