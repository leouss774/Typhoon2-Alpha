# Scoring (zone MVP)

Scores are **deterministic** in `app/scoring/zone_hazard_scores.py`. The LLM never recalculates them.

## Per-hazard base (from level text)

| Level | Base points |
|-------|-------------|
| Faible / 1 | 25 |
| Moyen / 2 | 55 |
| Élevé / Fort / 3 | 80 |
| Present (Géorisques v1) | 45 |

Sismique: zone 1–5 → 10, 25, 45, 65, 85.

## Proximity bonuses

- **Inondation**: +15 if water &lt; 100 m, +8 if &lt; 500 m  
- **Feu de forêt**: +12 if forest &lt; 200 m, +6 if &lt; 1000 m  

All scores clamped to 0–100.

## Building score

`0.7 × max(peril scores) + 0.3 × mean(peril scores)`

## Zone score

Mean of building `score_global` over successful points.

## Tier

| Tier | Score |
|------|-------|
| faible | &lt; 30 |
| modere | 30–59 |
| eleve | 60–79 |
| critique | ≥ 80 |
