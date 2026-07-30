"""
interpretation_agent — noeud LangGraph placé entre recommandations_agent et
diagnostic_agent.

Lit `state.building_data` (collector_agent) et `state.risk_scores`
(scoring_agent), croise TOUTES les données disponibles (caractéristiques
du bâtiment, climat, géorisques, altitude, marché) via l'API Mistral,
et produit des conclusions interprétées qui enrichissent le diagnostic.

Contrairement au scoring_agent (déterministe, basé sur des règles) et au
recommandations_agent (RAG sur un référentiel documentaire), cet agent
utilise un LLM pour :
  - Croiser un aléa (ex. feu de forêt) avec la vulnérabilité réelle du
    bâtiment (ex. charpente en bois → d'autant plus exposé)
  - Croiser le climat futur (2050) avec la résistance actuelle du bâti
  - Synthétiser en langage clair les facteurs aggravants et atténuants
  - Produire une conclusion lisible par le propriétaire, sans jargon

Les conclusions sont stockées dans `state.interpretations` sous forme
d'un dict indexé par nom de zone (cf. risk_model.ZONE_NAMES). Chaque
entrée contient :
  - "conclusion" : une phrase ou deux en français clair, grand public
  - "facteurs_aggravants" : liste de chaînes décrivant ce qui aggrave le risque
  - "facteurs_attenuants" : liste de chaînes décrivant ce qui atténue le risque
  - "vulnerabilite" : niveau estimé ("faible", "moderee", "elevee", "critique")

Si Mistral est indisponible (pas de clé API, timeout, etc.), l'agent
produit des interprétations vides plutôt que de faire échouer le graphe :
le diagnostic reste exploitable sans cette surcouche LLM.
"""

from __future__ import annotations

import time
from typing import Any

from app.agents.state import TyphoonState
from app.core.logging import get_logger
from app.recommandations.mistral_client import chat_json

logger = get_logger(__name__)

SYSTEM_PROMPT = """Tu es un expert en diagnostic de résilience climatique et vulnérabilité du bâti
pour l'immobilier en France. Tu travailles pour Typhoon, un service qui aide les
propriétaires à comprendre les risques auxquels leur maison est exposée.

Ton rôle : CROISER TOUTES les informations disponibles sur la maison et son environnement
pour produire un diagnostic de vulnérabilité clair, personnalisé et utile au propriétaire.

Tu reçois pour chaque zone du bâtiment (fondations, murs, toiture, sous-sol) :
- Un score de risque (0-100) et un niveau (faible/modéré/élevé/critique)
- Un aléa principal (ex. "Retrait-gonflement des argiles", "Feu de forêt", "Inondation")
- Une justification technique (données sources)

Tu reçois aussi TOUTES les données disponibles sur la maison et son environnement :
- Caractéristiques du bâtiment : année de construction, matériaux (murs, toiture), étages
- Climat actuel et projeté (2050) : températures, précipitations, jours de chaleur extrême
- Géorisques : zonage sismique, radon, cavités, mouvements de terrain, CATNAT historiques
- Altitude
- Données de marché (DVF) : prix au m², nombre de transactions

RÈGLES IMPÉRATIVES — CONCISION AVANT TOUT :
1. Croise VRAIMENT les informations : ne te contente pas de redire le risque.
   Exemple : "Risque incendie + charpente en bois → vulnérabilité très élevée"
   Exemple : "Année 1965 + zone sismique 4 → normes parasismiques probablement absentes"

2. Sois le PLUS CONCIS possible. Chaque phrase ou item doit tenir sur UNE SEULE LIGNE.
   Va à l'essentiel, pas de phrases longues ou littéraires.

3. Si les matériaux ou l'année de construction ne sont pas disponibles, base-toi
   uniquement sur les données de risque disponibles sans inventer de caractéristiques.

4. Les "facteurs aggravants" sont des éléments qui RENFORCENT le risque.
   Sois précis, cite les données, et reste court (max 1 ligne par item).
   Format : "donnée clé → conséquence" ou "caractéristique : impact".
   Exemple : "719 mm de pluie/an & zone inondable (9 arrêtés CATNAT)"
   Exemple : "Remontées capillaires (faible altitude : 7,49 m)"
   Exemple : "Absence d'hydrofuge moderne & sismicité modérée (Zone 3)"

5. Les "facteurs atténuants" sont des éléments qui RÉDUISENT le risque.
   Même format court (max 1 ligne par item).
   Exemple : "Pierre & ardoises : bonne résistance et étanchéité haute"
   Exemple : "Peu de canicules prévues en 2050 (contraintes thermiques limitées)"

6. La "conclusion" est une phrase UNIQUE très courte (10-20 mots max) qui décrit
   l'état de la zone : ce qui la rend vulnérable ou résistante, sans phrases longues.
   Exemple : "Murs en pierre (1870) solides mais vulnérables à l'humidité et aux intempéries."
   Exemple : "Toiture en tuiles récente offrant une bonne protection contre les intempéries."
   Exemple : "Fondations anciennes exposées au retrait-gonflement des argiles."

7. Le champ "vulnerabilite" doit être l'un de : "faible", "moderee", "elevee",
   "critique". Il reflète le CROISEMENT risque × vulnérabilité du bâti, pas
   le seul score de risque.

8. Ne mentionne jamais qu'il s'agit d'une "interprétation" ou d'une "analyse LLM".
   Présente les faits comme des constats directs et documentés.

9. Réponds UNIQUEMENT en JSON valide, sans texte autour.

Format de réponse attendu (exemple pour une zone "Murs") :
{
  "conclusion": "Murs en pierre (1870) solides mais vulnérables à l'humidité et aux intempéries.",
  "facteurs_aggravants": [
    "719 mm de pluie/an & zone inondable (9 arrêtés CATNAT)",
    "Remontées capillaires (faible altitude : 7,49 m)",
    "Absence d'hydrofuge moderne & sismicité modérée (Zone 3)"
  ],
  "facteurs_attenuants": [
    "Pierre & ardoises : bonne résistance et étanchéité haute",
    "Peu de canicules prévues en 2050 (contraintes thermiques limitées)"
  ],
  "vulnerabilite": "elevee"
}
"""


def _build_house_context(building_data: dict[str, Any]) -> dict[str, Any]:
    """Extrait toutes les caractéristiques de la maison depuis building_data."""
    bdnb = building_data.get("bdnb")
    batiment = {}
    if isinstance(bdnb, dict):
        batiment = bdnb.get("batiment") or bdnb

    materiaux = {}
    if isinstance(batiment, dict):
        materiaux = {
            "murs": batiment.get("mat_mur_txt"),
            "toiture": batiment.get("mat_toit_txt"),
        }

    # Climat : actuel + projection 2050
    climat = building_data.get("climat_open_meteo") or {}
    ref = climat.get("reference_2015_2024") or {}
    proj = climat.get("projection_2041_2050") or {}

    # Géorisques (extraction des infos clés)
    georisques = building_data.get("georisques") or {}
    risques_commune = {}
    if isinstance(georisques.get("risques_commune"), dict):
        risques_commune = georisques["risques_commune"].get("data") or []
    elif isinstance(georisques.get("risques_commune"), list):
        risques_commune = georisques["risques_commune"]

    risques_list = []
    if risques_commune:
        for entry in risques_commune if isinstance(risques_commune, list) else []:
            for detail in entry.get("risques_detail") or []:
                risques_list.append(detail.get("libelle_risque_long", ""))

    catnat_count = {}
    catnat_data = georisques.get("catnat", {})
    if isinstance(catnat_data, dict):
        catnat_list = catnat_data.get("data") or []
        for arrete in catnat_list if isinstance(catnat_list, list) else []:
            risque = arrete.get("libelle_risque_jo", "")
            catnat_count[risque] = catnat_count.get(risque, 0) + 1

    # Altitude
    altitude_m = building_data.get("altitude_m")

    # DVF
    dvf = building_data.get("dvf_local")

    contexte_climat = {}
    if ref:
        contexte_climat["reference_2015_2024"] = {
            k: ref.get(k) for k in [
                "temperature_max_moyenne_c", "temperature_max_absolue_c",
                "precipitation_annuelle_moyenne_mm", "jours_chaleur_extreme_par_an",
            ]
        }
    if proj:
        contexte_climat["projection_2041_2050"] = {
            k: proj.get(k) for k in [
                "temperature_max_moyenne_c", "temperature_max_absolue_c",
                "precipitation_annuelle_moyenne_mm", "jours_chaleur_extreme_par_an",
            ]
        }

    return {
        "annee_construction": batiment.get("annee_construction") if isinstance(batiment, dict) else None,
        "materiaux": materiaux,
        "nb_etages": batiment.get("nb_etages") if isinstance(batiment, dict) else None,
        "surface_plancher_m2": batiment.get("surface_plancher_m2") if isinstance(batiment, dict) else None,
        "altitude_m": altitude_m,
        "climat": contexte_climat,
        "risques_commune": risques_list[:10],  # top 10
        "catnat_historique": catnat_count,
        "dvf_disponible": bool(dvf),
    }


def _build_risk_context(risk_scores: dict[str, Any]) -> dict[str, Any]:
    """Extrait les infos de risque par zone."""
    zones = {}
    for zone_name, zone_data in risk_scores.get("zones", {}).items():
        zones[zone_name] = {
            "risque": zone_data.get("risque"),
            "niveau": zone_data.get("niveau"),
            "alea_principal": zone_data.get("alea_principal"),
            "justification": zone_data.get("justification"),
        }

    # Projection 2050
    proj_2050 = risk_scores.get("projection_2050", {})
    zones_2050 = {}
    for zone_name, zone_data in proj_2050.get("zones", {}).items():
        zones_2050[zone_name] = {
            "risque": zone_data.get("risque"),
            "niveau": zone_data.get("niveau"),
            "alea_principal": zone_data.get("alea_principal"),
            "justification": zone_data.get("justification"),
        }

    return {
        "score_global": risk_scores.get("score_global"),
        "zones": zones,
        "projection_2050": {
            "score_global": proj_2050.get("score_global"),
            "zones": zones_2050,
        },
    }


def _format_house_context(house: dict[str, Any]) -> str:
    """Formate le contexte maison en texte lisible pour le prompt."""
    lines = []

    if house.get("annee_construction"):
        lines.append(f"Année de construction : {house['annee_construction']}")
    if house.get("materiaux", {}).get("murs"):
        lines.append(f"Matériau des murs : {house['materiaux']['murs']}")
    if house.get("materiaux", {}).get("toiture"):
        lines.append(f"Matériau de la toiture : {house['materiaux']['toiture']}")
    if house.get("nb_etages"):
        lines.append(f"Nombre d'étages : {house['nb_etages']}")
    if house.get("surface_plancher_m2"):
        lines.append(f"Surface plancher : {house['surface_plancher_m2']} m²")
    if house.get("altitude_m") is not None:
        lines.append(f"Altitude : {house['altitude_m']} m")

    # Climat
    climat = house.get("climat", {})
    if climat.get("reference_2015_2024"):
        ref = climat["reference_2015_2024"]
        parts = []
        if ref.get("temperature_max_moyenne_c") is not None:
            parts.append(f"max {ref['temperature_max_moyenne_c']}°C")
        if ref.get("precipitation_annuelle_moyenne_mm") is not None:
            parts.append(f"{ref['precipitation_annuelle_moyenne_mm']} mm/an")
        if parts:
            lines.append(f"Climat actuel : {' · '.join(parts)}")
    if climat.get("projection_2041_2050"):
        proj = climat["projection_2041_2050"]
        parts = []
        if proj.get("temperature_max_moyenne_c") is not None:
            parts.append(f"max {proj['temperature_max_moyenne_c']}°C")
        if proj.get("precipitation_annuelle_moyenne_mm") is not None:
            parts.append(f"{proj['precipitation_annuelle_moyenne_mm']} mm/an")
        if proj.get("jours_chaleur_extreme_par_an") is not None:
            parts.append(f"{proj['jours_chaleur_extreme_par_an']} j canicule/an")
        if parts:
            lines.append(f"Climat 2050 (projeté) : {' · '.join(parts)}")

    # Géorisques
    risques = house.get("risques_commune", [])
    if risques:
        lines.append(f"Aléas recensés sur la commune : {', '.join(risques[:5])}")

    catnat = house.get("catnat_historique", {})
    if catnat:
        catnat_str = " · ".join(f"{k} ({v} arrêté(s))" for k, v in catnat.items())
        lines.append(f"Historique CATNAT : {catnat_str}")

    # Marché
    if house.get("dvf_disponible"):
        lines.append("Données de marché (DVF) disponibles")

    return "\n".join(lines) if lines else "Aucune information complémentaire disponible."


def _zone_label(zone_name: str) -> str:
    """Libellé lisible pour la zone."""
    labels = {
        "fondations": "Fondations",
        "murs_nord": "Murs (nord)",
        "murs_sud": "Murs (sud)",
        "murs_est": "Murs (est)",
        "murs_ouest": "Murs (ouest)",
        "toiture": "Toiture",
        "sous_sol": "Sous-sol",
    }
    return labels.get(zone_name, zone_name)


def _call_mistral_for_zone(
    zone_name: str,
    zone_data: dict[str, Any],
    house_context: dict[str, Any],
    zone_2050: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Appelle Mistral pour produire une interprétation croisée pour une zone.

    Inclut toutes les données disponibles : climat actuel + 2050, géorisques,
    altitude, matériaux, année de construction, etc.

    Retourne None si l'appel échoue (Mistral indisponible, timeout, etc.).
    """
    # Ne pas interpréter les zones de niveau faible : pas de risque significatif
    if zone_data.get("niveau") == "faible":
        return None

    zone_label = _zone_label(zone_name)
    house_text = _format_house_context(house_context)

    # Ajouter la projection 2050 si disponible et différente
    proj_2050_text = ""
    if zone_2050 and zone_2050.get("niveau") != zone_data.get("niveau"):
        proj_2050_text = (
            f"\nPROJECTION 2050 POUR CETTE ZONE :\n"
            f"Score 2050 : {zone_2050.get('risque')}/100\n"
            f"Niveau 2050 : {zone_2050.get('niveau')}\n"
            f"Aléa 2050 : {zone_2050.get('alea_principal')}\n"
        )

    user_prompt = f"""ZONE DU BÂTIMENT : {zone_label}
SCORE DE RISQUE ACTUEL : {zone_data.get('risque')}/100
NIVEAU : {zone_data.get('niveau')}
ALÉA PRINCIPAL : {zone_data.get('alea_principal')}
JUSTIFICATION TECHNIQUE : {zone_data.get('justification')}
{proj_2050_text}
CONTEXTE COMPLET DE LA MAISON ET DE SON ENVIRONNEMENT :
{house_text}

Croise TOUTES ces informations pour produire une conclusion de vulnérabilité éclairante et personnalisée destinée au propriétaire. Explique POURQUOI cette zone est vulnérable en reliant les données entre elles."""

    try:
        result = chat_json(SYSTEM_PROMPT, user_prompt)
        return {
            "conclusion": result.get("conclusion", ""),
            "facteurs_aggravants": result.get("facteurs_aggravants", []),
            "facteurs_attenuants": result.get("facteurs_attenuants", []),
            "vulnerabilite": result.get("vulnerabilite", "moderee"),
        }
    except Exception as exc:
        logger.warning(
            "  [interpretation] échec Mistral pour %s : %s",
            zone_name, exc,
        )
        return None


def run(state: TyphoonState) -> dict:
    """Noeud LangGraph : interprète les risques à la lumière de TOUTES les données disponibles.

    Lit `state.building_data` et `state.risk_scores`, produit
    `state.interpretations` (dict[str, dict] indexé par nom de zone).
    """
    t0 = time.perf_counter()
    building_data = state["building_data"]
    risk_scores = state["risk_scores"]

    house_context = _build_house_context(building_data)
    risk_context = _build_risk_context(risk_scores)

    logger.info(
        "interpretation_agent -- maison: %d sources, année=%s, matériaux murs=%s, toit=%s",
        sum(1 for v in [building_data.get("bdnb"), building_data.get("georisques"),
                        building_data.get("climat_open_meteo"), building_data.get("altitude_m"),
                        building_data.get("dvf_local")] if v),
        house_context.get("annee_construction", "N/A"),
        house_context.get("materiaux", {}).get("murs", "N/A"),
        house_context.get("materiaux", {}).get("toiture", "N/A"),
    )

    # Vérifier rapidement si Mistral est disponible
    from app.core.config import settings
    if not settings.mistral_api_key:
        logger.info("  interpretation_agent -- MISTRAL_API_KEY absente, aucune interprétation produite")
        return {"interpretations": {}}

    interpretations: dict[str, dict[str, Any]] = {}
    zones_2050 = risk_context.get("projection_2050", {}).get("zones", {})

    for zone_name, zone_data in risk_context["zones"].items():
        logger.info(
            "  interpretation %s (risque=%d, %s)",
            zone_name, zone_data.get("risque", 0), zone_data.get("niveau", "?"),
        )
        zone_2050 = zones_2050.get(zone_name)
        interp = _call_mistral_for_zone(zone_name, zone_data, house_context, zone_2050)
        if interp is not None:
            interpretations[zone_name] = interp

    logger.info(
        "interpretation_agent -- terminé en %.2fs (%d zone(s) interprétée(s) sur %d)",
        time.perf_counter() - t0,
        len(interpretations),
        len(risk_context["zones"]),
    )

    return {"interpretations": interpretations}
