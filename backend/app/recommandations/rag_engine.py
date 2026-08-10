"""
rag_engine — Agent recommandations (RAG), refactore depuis
recommendation_travaux/agent2_rag.py en fonction pure appelable comme noeud
LangGraph (cf. PROMPT_INTEGRATION_ouss.md, section 2).

Differences avec l'agent2_rag.py original (CLI) :
- plus d'argparse ni d'ecriture disque : generate_recommendations() est une
  fonction pure (house: dict, index: list) -> dict.
- l'index (data/index.json) est charge une seule fois via load_index_into_memory(),
  appelee depuis l'evenement startup de FastAPI (app/main.py) — jamais relu
  depuis le disque a chaque requete. get_loaded_index() expose ensuite cette
  copie en memoire au noeud du graphe (app/agents/recommandations_agent.py).
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from . import config
from .mistral_client import chat_json, embed_texts
from app.core.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """Tu es un agent de recommandations de travaux de reduction de vulnerabilite
climatique pour une maison individuelle en France.

Tu recois des informations sur une maison, un risque et une zone de la maison, ainsi qu'un
ensemble de fiches extraites d'un referentiel documentaire source.

REGLES IMPERATIVES
- Utilise UNIQUEMENT les fiches fournies dans FICHES DISPONIBLES. N'invente aucune regle, cout,
  pourcentage, obligation ou condition d'aide qui ne figure pas dans ces fiches.
- Si aucune fiche fournie n'est reellement pertinente pour ce risque et cette zone, renvoie une
  liste de recommandations vide plutot que d'inventer.
- Conserve le type de chaque fiche (recommandation_source, obligation_locale, regle_consolidee,
  estimation_cout, info_aide) dans ta reponse.
- Pour les aides, conserve le statut "potential_eligibility_only" et ne l'affirme jamais comme
  une eligibilite certaine.
- Cite pour chaque recommandation l'id de la fiche d'origine et son source_id.
- Reponds UNIQUEMENT en JSON valide, sans texte autour.
"""

# Index charge une seule fois au demarrage de l'app (cf. app/main.py, startup event).
_LOADED_INDEX: list | None = None


def get_loaded_index() -> list | None:
    return _LOADED_INDEX


def load_index_into_memory() -> list:
    """A appeler une seule fois, au demarrage de FastAPI. Leve une exception
    explicite si l'index n'a pas ete construit (voir build_index.py) — a
    attraper cote appelant pour ne pas empecher le reste de l'app de demarrer."""
    global _LOADED_INDEX
    _LOADED_INDEX = load_index()
    logger.info("recommandations: index RAG charge en memoire (%d fiche(s))", len(_LOADED_INDEX))
    return _LOADED_INDEX


def load_index() -> list:
    if not config.INDEX_PATH.exists():
        raise RuntimeError(
            f"Index introuvable ({config.INDEX_PATH}). Lance d'abord "
            f"`python -m app.recommandations.build_index` depuis backend/."
        )
    with open(config.INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


def cosine_sim(a, b) -> float:
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


def _search(index: list, query_vector, top_k: int, alea: str | None = None, zone: str | None = None) -> list:
    scored = []
    for entry in index:
        fiche = entry["fiche"]
        if alea and fiche.get("alea") and alea.lower() not in str(fiche["alea"]).lower():
            continue
        if zone and fiche.get("zone_maison") and zone.lower() not in str(fiche["zone_maison"]).lower():
            continue
        score = cosine_sim(query_vector, entry["vector"])
        scored.append((score, fiche))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [f for _, f in scored[:top_k]]


def generate_recommendations(house: dict[str, Any], index: list | None) -> dict[str, Any]:
    """Point d'entree du noeud recommandations. Meme structure de sortie que
    l'ancien data/resultat.json (agent2_rag.py CLI) : {adresse, bien, zones:[...]}.

    Si l'index n'est pas disponible, renvoie des recommandations vides plutot
    que de lever une exception (le graphe ne doit pas planter en l'absence du
    RAG — cf. app/agents/recommandations_agent.py).
    """
    zones_out = []

    for zone_info in house.get("zones", []):
        zone_name = zone_info.get("zone")
        risques = zone_info.get("risques", [])
        zone_reco = {"zone": zone_name, "risques": risques, "recommandations": []}

        if not index:
            zones_out.append(zone_reco)
            continue

        for risque in risques:
            logger.info("  [recommandations] %s / %s", zone_name, risque)
            query = f"Risque {risque} sur la zone {zone_name} d'une maison individuelle en France."
            query_vector = embed_texts([query])[0]

            candidates = _search(index, query_vector, config.TOP_K, alea=risque, zone=zone_name)
            if not candidates:
                candidates = _search(index, query_vector, config.TOP_K, alea=risque)
            if not candidates:
                candidates = _search(index, query_vector, config.TOP_K)
            if not candidates:
                logger.info("    -> aucune fiche disponible dans l'index, risque ignore")
                continue

            context = json.dumps(candidates, ensure_ascii=False, indent=2)
            user_prompt = f"""MAISON:
{json.dumps(house.get('bien', {}), ensure_ascii=False)}

RISQUE TRAITE: {risque}
ZONE TRAITEE: {zone_name}

FICHES DISPONIBLES:
{context}

Reponds avec un JSON de la forme:
{{"recommandations": [
  {{
    "mesure": "...",
    "type": "recommandation_source|obligation_locale|regle_consolidee|estimation_cout|info_aide",
    "cout_estime": {{...}} ou null,
    "aide": {{...}} ou null,
    "sources": [{{"fiche_id": "...", "source_id": "...", "extrait_exact": "..."}}]
  }}
]}}"""

            try:
                result = chat_json(SYSTEM_PROMPT, user_prompt)
            except Exception as e:
                logger.warning("    -> erreur Mistral pour %s/%s: %s", zone_name, risque, e)
                continue

            zone_reco["recommandations"].extend(result.get("recommandations", []))

        zones_out.append(zone_reco)

    return {
        "adresse": house.get("adresse"),
        "bien": house.get("bien"),
        "zones": zones_out,
    }
