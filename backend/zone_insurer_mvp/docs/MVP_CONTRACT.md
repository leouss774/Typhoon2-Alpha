# Zone Insurer API MVP Contract

Version: `1.0`  
Endpoint: `POST /zone/assess`

## Overview

The `/zone/assess` endpoint evaluates single addresses, coordinates, or multi-point polygons for natural hazard exposures in France.
It aggregates data from multiple sources (Géorisques v1/v2, BDNB, WFS Hydro/Forest) into a single deterministic risk assessment, with optional AI narrative generation via Mistral AI.

---

## Endpoint Details

- **URL:** `/zone/assess`
- **Method:** `POST`
- **Content-Type:** `application/json`

---

## Request Schema (`ZoneAssessRequest`)

```json
{
  "mode": "single",
  "points": [
    {
      "lat": 48.8566,
      "lon": 2.3522
    }
  ],
  "polygon": [],
  "address": "10 Rue de la Paix, 75002 Paris"
}
```

### Request Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `mode` | `string` | Mode of analysis (`"single"` or `"multi"`) | Yes |
| `points` | `array[LatLng]` | Array of `{ "lat": float, "lon": float }` | Optional |
| `polygon` | `array[LatLng]` | Array of polygon vertex coordinates | Optional |
| `address` | `string` | Free text address search string | Optional |

---

## Response Schema (`ZoneReport`)

```json
{
  "address": "10 Rue de la Paix, 75002 Paris",
  "nb_points": 1,
  "nb_ok": 1,
  "nb_errors": 0,
  "hazard_breakdown": [
    {
      "hazard": "inondation",
      "label": "Inondation",
      "present_count": 1,
      "total_count": 1,
      "pct_present": 100.0,
      "levels": ["Present"],
      "mean_score": 60.0,
      "max_score": 60.0
    }
  ],
  "catnat_totals": {
    "inondation": 3,
    "secheresse": 1,
    "mouvement_terrain": 0,
    "total": 4
  },
  "buildings": [
    {
      "address_label": "10 Rue de la Paix 75002 Paris",
      "lat": 48.8687,
      "lon": 2.3312,
      "hazards": [
        {
          "hazard": "inondation",
          "label": "Inondation",
          "level": "Present",
          "score": 60.0
        }
      ],
      "catnat_total": 4,
      "distance_cours_eau_m": 420.0,
      "distance_foret_m": 1250.0,
      "bdnb_cle_interop_adr": "75102_6845_00010",
      "bdnb_geom": null,
      "source": "live",
      "source_errors": [
        {"source": "georisques", "ok": true, "error": null},
        {"source": "georisques_v2", "ok": true, "error": null},
        {"source": "wfs", "ok": true, "error": null},
        {"source": "bdnb", "ok": true, "error": null}
      ],
      "data_quality": "ok",
      "score_global": 60.0
    }
  ],
  "narrative": "Zone étudiée : 1 point(s) analysé(s). Score agrégé 60.0/100 (niveau eleve). Aléas présents : Inondation. Historique CATNAT : 4 arrêté(s) recensé(s) (inondation 3, sécheresse 1, mouvement 0).",
  "recommendations": [
    "Risque élevé : inspection individuelle recommandée avant engagement.",
    "Clause de franchise renforcée sur l'aléa principal."
  ],
  "enumeration_method": "single_building",
  "duration_seconds": 1.25,
  "aggregate_score": 60.0,
  "aggregate_tier": "eleve",
  "narrative_source": "template",
  "data_sources_ok": ["bdnb", "georisques", "georisques_v2", "wfs"],
  "report_schema_version": "1.0"
}
```

### Key Enums & Tiers

- **`aggregate_tier`**: `faible` (<30), `modere` (30-59), `eleve` (60-79), `critique` (>=80)
- **`data_quality`**: `ok` (all sources OK), `partial` (some sources failed but hazards fetched), `failed` (complete failure/no data)
- **`narrative_source`**: `template` (deterministic rules) or `mistral` (AI generated)
- **Hazard Identifiers**: `rga_argile`, `inondation`, `mouvement_terrain`, `sismique`, `radon`, `feu_foret`
