"""
Alignement des noms de champs entre `scoring_agent` (app.scoring.risk_model)
et l'agent recommandations (app.recommandations.service) — cf.
PROMPT_INTEGRATION_ouss.md section 4, "C'est le point critique".

Deux ecarts de vocabulaire a combler, documentes dans le guide :

1. Zones : risk_model produit 7 zones (fondations, murs_nord/sud/est/ouest,
   toiture, sous_sol) ; le referentiel recommandations raisonne en
   fondations/toiture/facade/menuiseries/sous_sol (pas de distinction
   d'orientation). -> ZONE_TO_RECO regroupe les 4 murs_* sous "facade".
   `menuiseries` n'a pas d'equivalent cote risk_model aujourd'hui (aucune
   donnee BDNB/Georisques dediee aux ouvertures) : zone non alimentee pour
   l'instant, cf. limite documentee plus bas.

2. Risques : risk_model ne calcule pas un alea normalise par zone, il donne
   un score composite + un `alea_principal` en francais libre (ex.
   "Retrait-gonflement des argiles", "Canicule / stress thermique"). ->
   `_infer_risques` retape ce texte (+ la justification) vers le vocabulaire
   ferme attendu par le referentiel (retrait_gonflement_argiles, inondation,
   tempete, grele, canicule, secheresse, feu_vegetation, submersion,
   ruissellement), avec un repli par zone si aucun mot-cle ne matche.

Limite assumee (a ecrire au dossier si un vrai mapping BDNB->materiaux ou
un score par-alea distinct est ajoute plus tard cote scoring_agent) : ce
mapping est une heuristique texte, pas une re-derivation des sous-scores
(argile_score, inondation_score, ...) qui restent internes a risk_model.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# 1. Zones
# ---------------------------------------------------------------------------

ZONE_TO_RECO = {
    "fondations": "fondations",
    "toiture": "toiture",
    "sous_sol": "sous_sol",
    "murs_nord": "facade",
    "murs_sud": "facade",
    "murs_est": "facade",
    "murs_ouest": "facade",
}

# ---------------------------------------------------------------------------
# 2. Risques — mots-cles (francais libre, minuscules, sans accent geres a la
# volee) -> vocabulaire ferme du referentiel.
# ---------------------------------------------------------------------------

_KEYWORD_TO_RISQUE = [
    ("retrait-gonflement", "retrait_gonflement_argiles"),
    ("retrait gonflement", "retrait_gonflement_argiles"),
    ("argile", "retrait_gonflement_argiles"),
    ("rga", "retrait_gonflement_argiles"),
    ("secheresse", "secheresse"),
    ("submersion", "submersion"),
    ("inondation", "inondation"),
    ("remontee de nappe", "inondation"),
    ("ruissellement", "ruissellement"),
    ("infiltration", "ruissellement"),
    ("canicule", "canicule"),
    ("stress thermique", "canicule"),
    ("grele", "grele"),
    ("tempete", "tempete"),
    ("intemperie", "tempete"),
    ("vent", "tempete"),
    ("feu de vegetation", "feu_vegetation"),
    ("feu_vegetation", "feu_vegetation"),
    ("incendie", "feu_vegetation"),
]

# Repli par zone si aucun mot-cle du texte (alea_principal + justification)
# ne matche : garde au moins 1 risque pertinent plutot que de laisser la
# zone sans recommandation.
_ZONE_FALLBACK_RISQUE = {
    "fondations": "retrait_gonflement_argiles",
    "toiture": "tempete",
    "sous_sol": "inondation",
    "murs_nord": "tempete",
    "murs_sud": "tempete",
    "murs_est": "tempete",
    "murs_ouest": "tempete",
}


def _strip_accents(s: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _infer_risques(zone_name: str, zone_data: dict[str, Any]) -> list[str]:
    """Deduit les tags de risque normalises pour une zone du risk_model.

    Zone de niveau "faible" -> pas de recommandation (evite d'interroger
    l'agent RAG pour un risque juge negligeable par le scoring).
    """
    if zone_data.get("niveau") == "faible":
        return []

    texte = _strip_accents(
        f"{zone_data.get('alea_principal', '')} {zone_data.get('justification', '')}".lower()
    )
    found: list[str] = []
    for keyword, risque in _KEYWORD_TO_RISQUE:
        keyword_norm = _strip_accents(keyword)
        if keyword_norm in texte and risque not in found:
            found.append(risque)

    if not found:
        fallback = _ZONE_FALLBACK_RISQUE.get(zone_name)
        if fallback:
            found.append(fallback)

    return found


# ---------------------------------------------------------------------------
# 3. Bien (adresse/materiaux) — best-effort depuis la BDNB, jamais invente :
# champ absent -> None plutot qu'une valeur par defaut plausible mais fausse.
# ---------------------------------------------------------------------------


def _bien_type(bdnb: dict[str, Any] | None) -> str:
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    usage = (batiment or {}).get("usage_niveau_1_txt") if isinstance(batiment, dict) else None
    return usage or "maison individuelle"


def _materiaux(bdnb: dict[str, Any] | None) -> dict[str, Any]:
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    batiment = batiment or {}
    return {
        "murs": batiment.get("mat_mur_txt"),
        "toiture": batiment.get("mat_toit_txt"),
    }


def build_house_payload(building_data: dict[str, Any], risk_scores: dict[str, Any]) -> dict[str, Any]:
    """Construit le JSON "maison" attendu par l'agent recommandations (cf.
    docstring module + PROMPT_INTEGRATION_ouss.md section 4) a partir de
    `state.building_data` (collector_agent) et `state.risk_scores`
    (scoring_agent, periode 2025 -- pas la projection 2050).
    """
    adresse_info = building_data.get("adresse") or {}
    bdnb = building_data.get("bdnb")
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else {}
    batiment = batiment or {}

    zones_src: dict[str, dict[str, Any]] = risk_scores.get("zones", {})

    # Regroupe les 4 murs_* sous "facade" (union des risques, dedup).
    risques_par_reco_zone: dict[str, list[str]] = {}
    for zone_name, zone_data in zones_src.items():
        reco_zone = ZONE_TO_RECO.get(zone_name)
        if reco_zone is None:
            continue
        risques = _infer_risques(zone_name, zone_data)
        bucket = risques_par_reco_zone.setdefault(reco_zone, [])
        for r in risques:
            if r not in bucket:
                bucket.append(r)

    zones_out = [
        {"zone": reco_zone, "risques": risques}
        for reco_zone, risques in risques_par_reco_zone.items()
        if risques
    ]

    return {
        "adresse": adresse_info.get("label", ""),
        "bien": {
            "type": _bien_type(bdnb),
            "annee_construction": batiment.get("annee_construction"),
            "materiaux": _materiaux(bdnb),
            "coordonnees": {"lat": adresse_info.get("lat"), "lon": adresse_info.get("lon")},
        },
        "zones": zones_out,
    }


def merge_recommendations(risk_scores: dict[str, Any], reco_result: dict[str, Any]) -> None:
    """Reinjecte les recommandations produites par l'agent RAG dans
    `risk_scores["zones"][*]["recommandations"]` (mutation en place),
    en re-eclatant "facade" vers les 4 zones murs_* (meme liste de
    recommandations pour les 4 -- le referentiel ne distingue pas
    l'orientation, cf. docstring module).
    """
    recos_par_reco_zone: dict[str, list[dict[str, Any]]] = {
        z.get("zone"): z.get("recommandations", []) for z in reco_result.get("zones", [])
    }

    zones_dst: dict[str, dict[str, Any]] = risk_scores.get("zones", {})
    for zone_name, zone_data in zones_dst.items():
        reco_zone = ZONE_TO_RECO.get(zone_name)
        zone_data["recommandations"] = recos_par_reco_zone.get(reco_zone, [])
