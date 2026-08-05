"""
Niveau A — Effet des travaux sur le score de risque (F-A1 du doc).

Principe : réutilise EXACTEMENT le moteur du projet
(backend/app/scoring/risk_model.py) :
    R = 100 × (F/100)^0.5 × (V/100)^0.5        (_combine_risk)
    score_global = pondération des 7 zones      (_score_global)

Une mesure mappée réduit soit la composante F (aléa) soit la composante V
(vulnérabilité) d'une zone d'un facteur d'efficacité conservateur ; le
score après travaux est recalculé avec la même formule, puis
Δ = score_avant − score_après devient le `gain_resilience` réel.

Honnêteté : chaque facteur d'efficacité est une HYPOTHÈSE de modèle
(ordre de grandeur issu des référentiels MRN/France Assureurs, réf. 12-13
du doc §4), marquée comme telle et à affiner avec la fiche MRN exacte.
Aucune mesure hors table ne reçoit de taux → son effet reste `null`.

Les zones "murs_nord/sud/est/ouest" sont traitées ensemble (bucket
"facade"), comme dans app/recommandations/mapping.py.
"""

from __future__ import annotations

from typing import Any

from app.economie.schemas import CALCULE, NULL, bloc
from app.economie.sources import source_refs
from app.recommandations.mapping import _strip_accents
from app.scoring.risk_model import ZONE_NAMES, _clamp, _combine_risk, _score_global

_MURS = {"murs_nord", "murs_sud", "murs_est", "murs_ouest"}

# Table mesure -> effet. `keywords` sont cherchés (sous-chaîne) dans le
# texte normalisé du champ "mesure" des recommandations. `cible` = composante
# F ou V de la zone que la mesure réduit. `efficacite` est une hypothèse
# conservatrice (0-1), ordre de grandeur des référentiels MRN.
MESURE_EFFETS: list[dict[str, Any]] = [
    {
        "keywords": ("drainage", "drain ", "drain francais", "drain français"),
        "zone": "fondations",
        "cible": "F",
        "efficacite": 0.30,
        "source_ids": ("MRN2023", "MRN2024"),
        "hypothese": (
            "drainage périphérique : réduit l'humidité des sols au droit des "
            "fondations (aggrave/attenue le RGA). Taux conservateur d'ordre de "
            "grandeur MRN, à affiner avec la fiche exacte."
        ),
    },
    {
        "keywords": ("ecran racinaire", "écran racinaire", "bordure"),
        "zone": "fondations",
        "cible": "F",
        "efficacite": 0.30,
        "source_ids": ("MRN2023",),
        "hypothese": (
            "écran racinaire / bordures de végétation : écarte les racines "
            "pompantes des fondations (atténuation RGA). Taux conservateur "
            "d'ordre de grandeur MRN, à affiner."
        ),
    },
    {
        "keywords": ("gouttiere", "gouttière", "descente d'eau", "descente deau", "descente de pluie"),
        "zone": "fondations",
        "cible": "F",
        "efficacite": 0.25,
        "source_ids": ("MRN2023",),
        "hypothese": (
            "gouttières / descentes d'eaux pluviales : évacuent l'eau hors des "
            "fondations (atténuation RGA). Taux conservateur MRN, à affiner."
        ),
    },
    {
        "keywords": ("batardeau", "batardeaux"),
        "zone": "sous_sol",
        "cible": "F",
        "efficacite": 0.40,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "batardeaux : barrière physique contre l'entrée d'eau (inondation / "
            "remontée de nappe). Taux conservateur MRN, à affiner."
        ),
    },
    {
        "keywords": ("clapet", "clapet anti-retour", "antiretour", "anti-retour"),
        "zone": "sous_sol",
        "cible": "F",
        "efficacite": 0.35,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "clapet anti-retour : bloque le reflux des canalisations "
            "(inondation / remontée de nappe). Taux conservateur MRN, à affiner."
        ),
    },
    {
        "keywords": ("rehaussement", "rehausse", "surélévation", "surelevation", "relevage", "releve"),
        "zone": "sous_sol",
        "cible": "F",
        "efficacite": 0.50,
        "source_ids": ("FW2022", "MRN2024"),
        "hypothese": (
            "rehaussement / pompe de relevage : réduit l'exposition aux entrées "
            "d'eau. Ordre de grandeur illustratif (Gnan et al. 2022, US) — "
            "valeur à affiner avec une cote de profondeur réelle."
        ),
    },
    {
        "keywords": ("pompe", "pompe de relevage", "pompe immergee", "pompe immergée"),
        "zone": "sous_sol",
        "cible": "V",
        "efficacite": 0.30,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "pompe de relevage : réduit la vulnérabilité au désordre causé par "
            "une entrée d'eau. Taux conservateur MRN, à affiner."
        ),
    },
    {
        "keywords": ("etancheite", "étanchéité", "hydrofuge", "impermeabilis", "imperméabilis"),
        "zone": "murs",
        "cible": "F",
        "efficacite": 0.30,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "traitement d'étanchéité / hydrofuge de la façade : réduit "
            "l'infiltration pluviale (précipitations intenses). Taux conservateur "
            "MRN, à affiner."
        ),
    },
    {
        "keywords": ("vegetalisation", "végétalisation", "toiture vegetale", "toiture végétale", "brise-soleil", "brise soleil"),
        "zone": "toiture",
        "cible": "F",
        "efficacite": 0.30,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "végétalisation / protections solaires : réduit le stress thermique "
            "(canicule). Taux conservateur MRN, à affiner."
        ),
    },
    {
        "keywords": ("isolation", "isolant", "renovation energetique", "rénovation énergétique"),
        "zone": "toiture",
        "cible": "F",
        "efficacite": 0.20,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "isolation : réduit le stress thermique de la toiture. Taux "
            "conservateur MRN, à affiner."
        ),
    },
    {
        "keywords": ("toiture", "toit", "couverture", "ardoise", "tuile", "charpente"),
        "zone": "toiture",
        "cible": "V",
        "efficacite": 0.30,
        "source_ids": ("MRN2024", "MRN2023"),
        "hypothese": (
            "renforcement/rénovation de la toiture : réduit la vulnérabilité "
            "structurelle (tempête, grêle, feu de végétation). Taux conservateur "
            "MRN, à affiner."
        ),
    },
    {
        "keywords": ("entretien", "controle", "contrôle", "inspection", "maintenance", "veille", "nettoyage"),
        "zone": "fondations",
        "cible": "V",
        "efficacite": 0.10,
        "source_ids": ("MRN2024",),
        "hypothese": (
            "entretien / contrôles réguliers : maintien de l'état initial, effet "
            "faible et volontairement conservateur. Taux MRN, à affiner."
        ),
    },
]


def _bucket_zone(zone_name: str) -> str:
    return "murs" if zone_name in _MURS else zone_name


def _trouver_effet(mesure: str) -> dict[str, Any] | None:
    texte = _strip_accents((mesure or "").lower())
    for eff in MESURE_EFFETS:
        for kw in eff["keywords"]:
            if _strip_accents(kw.lower()) in texte:
                return eff
    return None


def _risque_apres(zone_data: dict[str, Any], effets: list[dict[str, Any]]) -> int:
    """Score après travaux : application cumulative (multiplicative) des
    effets sur F ou V, puis même formule R = _combine_risk(F, V)."""
    f = zone_data.get("_f_score")
    v = zone_data.get("_v_score")
    if f is None or v is None:
        return zone_data.get("risque", 0)
    f = float(f)
    v = float(v)
    for eff in effets:
        if eff["cible"] == "F":
            f *= 1.0 - eff["efficacite"]
        else:
            v *= 1.0 - eff["efficacite"]
    return _clamp(_combine_risk(max(f, 0.0), max(v, 0.0)))


def appliquer_effets(risk_scores: dict[str, Any]) -> dict[str, Any]:
    """Calcule le Δ de score par mesure et par zone (niveau A).

    Retourne :
      {
        "score_global_avant": int,
        "score_global_apres": int,
        "delta_global": int,
        "par_zone": [ {zone, risque_avant, risque_apres, delta, mesures: [...]} ],
        "par_mesure": [ {mesure, zone, cible, efficacite, risque_avant,
                         risque_apres, delta, statut, sources, hypotheses,
                         confidence} ],
        "statut": "calcule"|"null",
        "raison": str | None,
      }
    """
    zones_src: dict[str, dict[str, Any]] = risk_scores.get("zones", {})
    avant = risk_scores.get("score_global")
    if avant is None and zones_src:
        avant = _score_global(zones_src)

    par_zone: list[dict[str, Any]] = []
    par_mesure: list[dict[str, Any]] = []
    zones_apres_all: dict[str, dict[str, Any]] = {}
    # Une même mesure (ex. "Traitement hydrofuge de la facade") est dupliquée
    # sur les 4 zones murs_* par merge_recommendations : on ne la compte qu'une
    # fois dans par_mesure (clé = bucket + texte de mesure).
    vues_mesures: set[tuple[str, str]] = set()

    for zone_name in ZONE_NAMES:
        zone_data = zones_src.get(zone_name)
        if not zone_data:
            continue
        recos = [r for r in (zone_data.get("recommandations") or []) if isinstance(r, dict)]
        effets = [_trouver_effet(r.get("mesure")) for r in recos]
        effets = [e for e in effets if e]

        risque_avant_zone = zone_data.get("risque", 0)
        risque_apres_zone = _risque_apres(zone_data, effets)
        zones_apres_all[zone_name] = {"risque": risque_apres_zone}

        mesures_detail: list[dict[str, Any]] = []
        for reco in recos:
            eff = _trouver_effet(reco.get("mesure"))
            if eff is None:
                continue
            f = zone_data.get("_f_score")
            v = zone_data.get("_v_score")
            if f is None or v is None:
                par_mesure.append(
                    {
                        "mesure": reco.get("mesure"),
                        "zone": zone_name,
                        "statut": NULL,
                        "raison": "composantes F/V absentes pour cette zone",
                    }
                )
                continue
            risque_apres_mesure = _risque_apres(zone_data, [eff])
            delta = int(round(risque_avant_zone - risque_apres_mesure))
            detail = {
                "mesure": reco.get("mesure"),
                "zone": zone_name,
                "cible": eff["cible"],
                "efficacite": eff["efficacite"],
                "risque_avant": risque_avant_zone,
                "risque_apres": risque_apres_mesure,
                "delta": delta,
                "statut": CALCULE,
                "sources": source_refs(*eff["source_ids"]),
                "hypotheses": [eff["hypothese"]],
                "confidence": 40,
            }
            mesures_detail.append(detail)
            cle = (_bucket_zone(zone_name), reco.get("mesure"))
            if cle not in vues_mesures:
                vues_mesures.add(cle)
                par_mesure.append(detail)

        par_zone.append(
            {
                "zone": zone_name,
                "risque_avant": risque_avant_zone,
                "risque_apres": risque_apres_zone,
                "delta": int(round(risque_avant_zone - risque_apres_zone)),
                "n_mesures_appliquees": len(mesures_detail),
                "mesures": mesures_detail,
            }
        )

    apres_global = avant
    if zones_apres_all and set(zones_apres_all) >= set(ZONE_NAMES):
        apres_global = _score_global(zones_apres_all)
    applique = [m for m in par_mesure if m.get("statut") == CALCULE]

    return {
        "score_global_avant": avant,
        "score_global_apres": apres_global,
        "delta_global": int(round((avant or 0) - (apres_global or 0))),
        "par_zone": par_zone,
        "par_mesure": par_mesure,
        "statut": CALCULE if applique else NULL,
        "raison": None if applique else (
            "aucune recommandation ne correspond à une mesure de la table "
            "d'efficacité (MESURE_EFFETS) → aucun taux appliqué, Δ=0"
        ),
    }
