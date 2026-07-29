"""
Coeur RAG de l'agent recommandations — repris de
recommendation_travaux-main/agent2_rag.py (fonction `process_house`), rendu
importable comme fonction pure `generate_recommendations(house, index)` (cf.
PROMPT_INTEGRATION_ouss.md, section 2).

Contrat d'entree (`house`) — impose par l'agent recommandations, cf.
PROMPT_INTEGRATION_ouss.md section 4 :

    {
      "adresse": "...",
      "bien": {"type": ..., "annee_construction": ..., "materiaux": {...}, "coordonnees": {...}},
      "zones": [{"zone": "toiture", "risques": ["tempete", "grele"]}, ...]
    }

(voir app.recommandations.mapping pour la construction de ce payload a
partir de state.building_data / state.risk_scores)

Contrat de sortie : meme structure que data/resultat.json du repo source —
{"adresse", "bien", "zones": [{"zone", "risques", "recommandations": [...]}]},
chaque recommandation ayant desormais un champ "explication" (redaction
detaillee et pedagogique, cf. SYSTEM_PROMPT) en plus de "mesure" (titre
court) — voir aussi frontend/jumeau_numerique/index.html pour l'affichage.

Chargement de l'index : `get_index()` lit data/index.json une seule fois
(cache module-level) et le garde en memoire pour tous les appels suivants,
comme demande par le guide d'integration (pas de re-lecture disque a
chaque requete HTTP). `load_index()` force le (re)chargement — appele
explicitement au startup FastAPI (app/main.py) pour que le premier appel
/diagnostic ne paie pas le cout de lecture des ~19 Mo de data/index.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from app.core.logging import get_logger
from app.recommandations.mistral_client import chat_json, embed_texts

logger = get_logger(__name__)

# backend/app/recommandations/service.py -> backend/app/recommandations/data/index.json
_DATA_DIR = Path(__file__).resolve().parent / "data"
INDEX_PATH = _DATA_DIR / "index.json"

TOP_K = 6  # nombre de fiches recuperees par requete RAG, cf. repo source

SYSTEM_PROMPT = """Tu es un agent de recommandations de travaux de reduction de vulnerabilite
climatique pour une maison individuelle en France. Ton destinataire final est le proprietaire
de la maison, pas un expert du batiment : chaque recommandation doit etre comprehensible sans
jargon non explique.

Tu recois des informations sur une maison, une zone et plusieurs risques associes, ainsi qu'un
ensemble de fiches extraites d'un referentiel documentaire source.

REGLES IMPERATIVES SUR LE FOND
- Utilise UNIQUEMENT les fiches fournies dans FICHES DISPONIBLES. N'invente aucune regle, cout,
  pourcentage, obligation ou condition d'aide qui ne figure pas dans ces fiches.
- Si aucune fiche fournie n'est reellement pertinente pour les risques de cette zone, renvoie une
  liste de recommandations vide plutot que d'inventer.
- Conserve le type de chaque fiche (recommandation_source, obligation_locale, regle_consolidee,
  estimation_cout, info_aide) dans ta reponse.
- Pour les aides, conserve le statut "potential_eligibility_only" et ne l'affirme jamais comme
  une eligibilite certaine.
- Cite pour chaque recommandation l'id de la fiche d'origine et son source_id.
- Chaque recommandation doit avoir un champ "risque_concerne" qui precise a quel risque elle
  se rapporte parmi ceux listes dans RISQUES A TRAITER.

REGLES SUR LA REDACTION (concision) — c'est le point le plus important
- "mesure" : titre court et concret (5-10 mots), ex. "Traitement hydrofuge de la facade".
- "explication" : **1 a 2 phrases maximum**, concises et factuelles. Dis (a) quoi faire
  concretement et (b) pourquoi ca reduit ce risque sur cette zone, sans detail superflu.
  L'utilisateur est proprietaire, pas expert.
- "cout_estime" : si la fiche source donne un cout, RECOPIE integralement tous les champs
  disponibles (montant_min, montant_max, devise, unite, date_estimation, zone_geo, hypotheses) —
  ne resume pas, ne laisse pas de champ vide s'il est renseigne dans la fiche. Si aucun cout
  n'est donne par les fiches, renvoie null (n'estime jamais toi-meme un montant).
- "aide" : si une fiche mentionne un dispositif d'aide, explicite dans "conditions" a qui elle
  s'adresse et sous quelle condition (tel que ecrit dans la fiche), garde "statut":
  "potential_eligibility_only".
- Reponds UNIQUEMENT en JSON valide, sans texte autour.
"""

_index_cache: list[dict[str, Any]] | None = None


def load_index() -> list[dict[str, Any]]:
    """(Re)charge data/index.json depuis le disque et met a jour le cache."""
    global _index_cache
    if not INDEX_PATH.exists():
        raise RuntimeError(
            f"Index recommandations introuvable ({INDEX_PATH}). "
            "Il doit etre copie depuis recommendation_travaux-main/data/index.json."
        )
    t0 = __import__("time").perf_counter()
    with open(INDEX_PATH, encoding="utf-8") as f:
        _index_cache = json.load(f)
    logger.info(
        "recommandations -- index charge (%d fiches, %.2fs)",
        len(_index_cache),
        __import__("time").perf_counter() - t0,
    )
    return _index_cache


def get_index() -> list[dict[str, Any]]:
    """Retourne l'index en memoire, le charge au premier appel si necessaire."""
    if _index_cache is None:
        return load_index()
    return _index_cache


def cosine_sim(a, b) -> float:
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


def _search(index: list[dict[str, Any]], query_vector, top_k: int, alea: str | None = None, zone: str | None = None):
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


def build_user_prompt_for_zone(
    bien: dict[str, Any],
    zone_name: str,
    risques: list[str],
    candidates: list[dict[str, Any]],
) -> str:
    """Construit le prompt utilisateur pour une zone avec tous ses risques."""
    risques_str = ", ".join(risques)
    context = json.dumps(candidates, ensure_ascii=False, indent=2)
    return f"""MAISON:
{json.dumps(bien, ensure_ascii=False)}

ZONE TRAITEE: {zone_name}
RISQUES A TRAITER: {risques_str}

FICHES DISPONIBLES:
{context}

Reponds avec un JSON de la forme:
{{"recommandations": [
  {{
    "mesure": "titre court et concret",
    "explication": "1 a 2 phrases max : quoi faire et pourquoi ca reduit ce risque",
    "risque_concerne": "nom_du_risque_parmi_la_liste",
    "type": "recommandation_source|obligation_locale|regle_consolidee|estimation_cout|info_aide",
    "cout_estime": {{"montant_min": ..., "montant_max": ..., "devise": "...", "unite": "...", "date_estimation": "...", "zone_geo": "...", "hypotheses": "..."}} ou null,
    "aide": {{"dispositif": "...", "conditions": "...", "statut": "potential_eligibility_only"}} ou null,
    "sources": [{{"fiche_id": "...", "source_id": "...", "extrait_exact": "..."}}]
  }}
]}}"""


def search_zone_candidates(
    index: list[dict[str, Any]],
    zone_name: str,
    risques: list[str],
) -> list[dict[str, Any]]:
    """Recherche des fiches pertinentes pour un ensemble de risques sur une zone.
    Utilise le premier risque pour la requete embedding, puis elargit si necessaire.
    """
    if not risques:
        return []

    # Requete combinee pour l'embedding avec tous les risques de la zone
    risques_str = ", ".join(risques)
    query = f"Risques {risques_str} sur la zone {zone_name} d'une maison individuelle en France."
    query_vector = embed_texts([query])[0]

    # Filtre avec le premier risque et la zone
    candidates = _search(index, query_vector, TOP_K, alea=risques[0], zone=zone_name)
    if not candidates:
        candidates = _search(index, query_vector, TOP_K, alea=risques[0])
    if not candidates:
        candidates = _search(index, query_vector, TOP_K)
    return candidates


def generate_recommendations(house: dict[str, Any], index: list[dict[str, Any]]) -> dict[str, Any]:
    """Point d'entree pur du noeud recommandations (cf. docstring module).

    Optimise : groupe tous les risques d'une zone dans un seul appel Mistral,
    au lieu d'un appel par risque (cf. amelioration_recommandation.md section 1).
    """
    zones_out = []

    for zone_info in house.get("zones", []):
        zone_name = zone_info.get("zone")
        risques = zone_info.get("risques", [])
        zone_reco: dict[str, Any] = {"zone": zone_name, "risques": risques, "recommandations": []}

        if not risques:
            zones_out.append(zone_reco)
            continue

        logger.info("recommandations -- %s / risques: %s", zone_name, ", ".join(risques))

        candidates = search_zone_candidates(index, zone_name, risques)
        if not candidates:
            logger.info("  -> aucune fiche disponible dans l'index pour %s, ignore", zone_name)
            zones_out.append(zone_reco)
            continue

        user_prompt = build_user_prompt_for_zone(
            house.get("bien", {}), zone_name, risques, candidates
        )

        try:
            result = chat_json(SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            logger.warning("  -> erreur Mistral pour %s: %s", zone_name, e)
            zones_out.append(zone_reco)
            continue

        zone_reco["recommandations"].extend(result.get("recommandations", []))
        zones_out.append(zone_reco)

    return {
        "adresse": house.get("adresse"),
        "bien": house.get("bien"),
        "zones": zones_out,
    }
