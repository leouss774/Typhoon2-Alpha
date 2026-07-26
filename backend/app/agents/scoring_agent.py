"""
scoring_agent : deuxieme noeud du graphe LangGraph (voir README.md, section
"Architecture multi-agents"). Consomme state["building_data"] (sortie de
collector_agent) et produit state["risk_scores"].

IMPORTANT - perimetre de cette version :
Le README decrit scoring_agent comme le futur calcul d'un score de risque par alea
et par partie du batiment ("la methode de calcul precise reste a specifier, voir
Roadmap"). Cette version n'implemente PAS encore ce score - elle fournit le strict
minimum requis pour brancher le noeud recommandations (rag_agent) de la collegue,
c'est-a-dire une derivation heuristique, deterministe et sans IA, du contrat exact
attendu par ce noeud (voir recommendation_travaux-main/PROMPT_INTEGRATION_ouss.md
point 4) :

    {
      "adresse": "...",
      "bien": {"type", "annee_construction", "materiaux": {"murs","toiture"}, "coordonnees"},
      "zones": [{"zone": "fondations", "risques": ["retrait_gonflement_argiles"]}, ...]
    }

Vocabulaire impose (normalise ici, cf. point 4 du prompt d'integration) :
    risques : retrait_gonflement_argiles, inondation, tempete, grele, canicule,
              secheresse, feu_vegetation, submersion, ruissellement
    zones   : fondations, toiture, facade, menuiseries, sous_sol

Les sources reelles utilisees (Georisques v1, Open-Meteo, Copernicus) ont des
formats non entierement confirmes a ce jour (voir docs/GUIDE_ORCHESTRATEUR_API.md :
aucun appel reel n'a encore ete effectue depuis un environnement avec acces
reseau). La detection ci-dessous scanne donc le JSON de facon defensive (recherche
de mots-cles dans le texte serialise) plutot que de supposer des noms de champs
precis - a affiner des qu'un premier payload reel aura ete inspecte, exactement
comme deja note pour bdnb.py/georisques.py.

Aucune valeur n'est inventee sur les DONNEES (materiaux, annee de construction) :
si l'information n'est pas trouvee dans building_data, le champ reste None. En
revanche l'association risque -> zone(s) de la maison est un choix de modelisation
(RISQUE_VERS_ZONES ci-dessous), assume et documente, pas une donnee externe.
"""

from __future__ import annotations

import json
import re
import unicodedata

# Vocabulaire impose cote agent recommandations.
ZONES = ("fondations", "toiture", "facade", "menuiseries", "sous_sol")

# Association risque -> zone(s) impactee(s) de la maison. Choix de modelisation
# assume (pas de scoring_agent officiel existant a ce jour, voir docstring).
RISQUE_VERS_ZONES: dict[str, tuple[str, ...]] = {
    "retrait_gonflement_argiles": ("fondations",),
    "secheresse": ("fondations",),
    "inondation": ("sous_sol", "fondations"),
    "submersion": ("sous_sol", "fondations"),
    "ruissellement": ("sous_sol", "facade"),
    "tempete": ("toiture",),
    "grele": ("toiture",),
    "canicule": ("facade", "menuiseries"),
    "feu_vegetation": ("facade", "toiture"),
}

# Mots-cles (normalises : minuscules, sans accents) declenchant chaque risque
# lorsqu'ils apparaissent dans le JSON Georisques serialise. Ordre : du plus
# specifique au plus generique pour eviter les faux positifs (ex. "submersion
# marine" doit matcher submersion, pas inondation).
_MOTS_CLES_RISQUES: list[tuple[str, tuple[str, ...]]] = [
    ("retrait_gonflement_argiles", ("retrait-gonflement", "retrait gonflement", "rga", "argile")),
    ("submersion", ("submersion marine", "submersion")),
    ("inondation", ("inondation", "crue", "coulee de boue", "coulees de boue")),
    ("feu_vegetation", ("feu de foret", "feux de foret", "incendie de foret", "feu de vegetation")),
    ("tempete", ("tempete",)),
    ("grele", ("grele",)),
]


def _normalize(text: str) -> str:
    """minuscules + sans accents, pour un matching de mots-cles robuste."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_accents.lower()


def _flatten_to_text(payload) -> str:
    """Serialise n'importe quelle valeur JSON en texte normalise pour recherche
    de mots-cles, sans hypothese sur la structure exacte (listes, dicts imbriques,
    noms de champs variables selon la version de l'API Georisques)."""
    if payload is None:
        return ""
    try:
        raw = json.dumps(payload, ensure_ascii=False, default=str)
    except TypeError:
        raw = str(payload)
    return _normalize(raw)


def _find_first_value(payload: dict, must_contain: tuple[str, ...]):
    """Cherche, recursivement, la premiere valeur (non nulle) dont la CLE
    contient tous les fragments de `must_contain` (insensible a la casse).
    Utilise pour extraire des champs BDNB dont le nom exact de colonne n'a pas
    encore ete confirme par un appel reel (voir docstring de bdnb.py)."""
    if not isinstance(payload, dict):
        return None
    for key, value in payload.items():
        key_norm = _normalize(str(key))
        if all(fragment in key_norm for fragment in must_contain):
            if value not in (None, "", []):
                return value
    for value in payload.values():
        if isinstance(value, dict):
            found = _find_first_value(value, must_contain)
            if found is not None:
                return found
    return None


def _detect_risques_from_georisques(georisques: dict | None) -> set[str]:
    detected: set[str] = set()
    if not georisques:
        return detected

    # On scanne chaque sous-bloc pertinent independamment (plutot que tout le
    # dict d'un coup) pour ne pas se faire polluer par des cles techniques
    # (ex. "erreurs", "lien_rapport_pdf").
    blocs_pertinents = (
        "risques_commune",
        "catnat",
        "zones_inondables",
        "mouvements_de_terrain",
    )
    for bloc in blocs_pertinents:
        texte = _flatten_to_text(georisques.get(bloc))
        if not texte:
            continue
        for risque, mots_cles in _MOTS_CLES_RISQUES:
            if any(mot in texte for mot in mots_cles):
                detected.add(risque)

    # azi (zones inondables) : presence de donnees exploitables meme sans le
    # mot "inondation" explicite dans le payload -> on la traite comme un
    # signal d'inondation.
    azi = georisques.get("zones_inondables")
    if azi not in (None, {}, [], "null"):
        detected.add("inondation")

    return detected


def _detect_climat(climat_open_meteo: dict | None, climat_copernicus: dict | None) -> set[str]:
    detected: set[str] = set()

    # Open-Meteo : jours de chaleur extreme (>35 degC) sur la projection 2041-2050.
    projection = (climat_open_meteo or {}).get("projection_2041_2050") or {}
    jours_chaleur = projection.get("jours_chaleur_extreme_par_an")
    if isinstance(jours_chaleur, (int, float)) and jours_chaleur >= 3:
        detected.add("canicule")

    # Copernicus : cles au format "{fichier}__{variable}" (voir copernicus.py).
    for cle, valeur in (climat_copernicus or {}).items():
        cle_norm = _normalize(cle)
        if "heatwave_days" in cle_norm or "hot_days" in cle_norm:
            if _a_une_valeur_significative(valeur):
                detected.add("canicule")
        if "drought" in cle_norm:
            if _a_une_valeur_significative(valeur):
                detected.add("secheresse")
                detected.add("retrait_gonflement_argiles")
        if "extreme_precipitation" in cle_norm:
            if _a_une_valeur_significative(valeur):
                detected.add("ruissellement")

    return detected


def _a_une_valeur_significative(valeur) -> bool:
    """True si la valeur (scalaire ou liste imbriquee, cf. xarray .tolist())
    contient au moins un nombre strictement positif."""
    if valeur is None:
        return False
    if isinstance(valeur, (int, float)):
        return valeur > 0
    if isinstance(valeur, list):
        return any(_a_une_valeur_significative(v) for v in valeur)
    return False


def _extraire_bien(building_data: dict) -> dict:
    bdnb = (building_data.get("bdnb") or {}).get("batiment") or {}
    adresse = building_data.get("adresse") or {}

    annee_construction = _find_first_value(bdnb, ("annee", "construction"))
    materiau_murs = _find_first_value(bdnb, ("mur",)) or _find_first_value(bdnb, ("mat", "mur"))
    materiau_toiture = (
        _find_first_value(bdnb, ("toit",))
        or _find_first_value(bdnb, ("toiture",))
        or _find_first_value(bdnb, ("mat", "couv"))
    )

    return {
        "type": "maison individuelle",
        "annee_construction": annee_construction,
        "materiaux": {
            "murs": materiau_murs,
            "toiture": materiau_toiture,
        },
        "coordonnees": {
            "lat": adresse.get("lat"),
            "lon": adresse.get("lon"),
        },
    }


def score_risks(building_data: dict) -> dict:
    """Fonction pure : building_data (sortie collector_agent) -> contrat "maison"
    attendu par rag_agent (voir docstring du module).
    """
    risques_detectes = set()
    risques_detectes |= _detect_risques_from_georisques(building_data.get("georisques"))
    risques_detectes |= _detect_climat(
        building_data.get("climat_open_meteo"),
        building_data.get("climat_copernicus"),
    )

    zones_out = []
    for zone in ZONES:
        risques_zone = sorted(
            risque
            for risque, zones_associees in RISQUE_VERS_ZONES.items()
            if zone in zones_associees and risque in risques_detectes
        )
        if risques_zone:
            zones_out.append({"zone": zone, "risques": risques_zone})

    adresse = building_data.get("adresse") or {}

    return {
        "adresse": adresse.get("label"),
        "bien": _extraire_bien(building_data),
        "zones": zones_out,
    }


# --- Noeud LangGraph --------------------------------------------------------

async def scoring_node(state: dict) -> dict:
    """Noeud LangGraph : lit state['building_data'], ecrit state['risk_scores']."""
    building_data = state["building_data"]
    return {"risk_scores": score_risks(building_data)}
