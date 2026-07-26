"""
Agent recommandations (RAG) - version importable pour le graphe LangGraph.

Refactorisation du script CLI d'origine (recommendation_travaux-main/agent2_rag.py,
voir PROMPT_INTEGRATION_ouss.md point 2) : la logique metier est inchangee
(process_house), mais elle est desormais exposee comme une fonction pure
`generate_recommendations(house, index)` sans effet de bord disque, utilisable
directement comme noeud LangGraph (voir app/agents/rag_agent.py).

Le CLI d'origine est conserve en bas de fichier pour tester ce module isolement :
    python -m app.recommandations.agent2_rag --input maison.json --output resultat.json

Entree attendue (contrat exact, voir PROMPT_INTEGRATION_ouss.md point 4) :
    {
      "adresse": "...",
      "bien": {...},
      "zones": [{"zone": "fondations", "risques": ["retrait_gonflement_argiles"]}, ...]
    }

Sortie : meme structure, "zones" enrichi d'une cle "recommandations" sourcees par
zone/risque (voir README.md de recommendation_travaux-main pour le detail des
champs mesure/type/cout_estime/aide/sources).
"""
from __future__ import annotations

import argparse
import json
import os

import numpy as np

from app.recommandations import config
from app.recommandations.mistral_client import chat_json, embed_texts

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


def cosine_sim(a, b) -> float:
    a = np.array(a, dtype=float)
    b = np.array(b, dtype=float)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
    return float(np.dot(a, b) / denom)


def load_index(index_path: str | None = None) -> list:
    """Charge data/index.json. A appeler UNE SEULE FOIS (voir get_index() dans
    app/agents/rag_agent.py pour le cache utilise par le graphe)."""
    path = index_path or config.INDEX_PATH
    if not os.path.exists(path):
        raise RuntimeError(
            f"Index introuvable ({path}). Lance d'abord build_index.py dans "
            "recommendation_travaux-main (ou copie data/index.json depuis ce dossier)."
        )
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def search(index, query_vector, top_k, alea=None, zone=None):
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


def process_house(house: dict, index: list) -> dict:
    """Logique metier inchangee par rapport au script d'origine."""
    zones_out = []

    for zone_info in house.get("zones", []):
        zone_name = zone_info.get("zone")
        risques = zone_info.get("risques", [])
        zone_reco = {"zone": zone_name, "risques": risques, "recommandations": []}

        for risque in risques:
            print(f"[Agent2] {zone_name} / {risque}")
            query = f"Risque {risque} sur la zone {zone_name} d'une maison individuelle en France."
            query_vector = embed_texts([query])[0]

            # filtre strict d'abord, puis relachement progressif si rien trouve
            candidates = search(index, query_vector, config.TOP_K, alea=risque, zone=zone_name)
            if not candidates:
                candidates = search(index, query_vector, config.TOP_K, alea=risque)
            if not candidates:
                candidates = search(index, query_vector, config.TOP_K)
            if not candidates:
                print("  -> aucune fiche disponible dans l'index, zone ignoree")
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
                print(f"  -> erreur Mistral: {e}")
                continue

            zone_reco["recommandations"].extend(result.get("recommandations", []))

        zones_out.append(zone_reco)

    return {
        "adresse": house.get("adresse"),
        "bien": house.get("bien"),
        "zones": zones_out,
    }


def generate_recommendations(house: dict, index: list) -> dict:
    """Point d'entree "noeud LangGraph" : fonction pure, pas d'ecriture disque.

    house : JSON produit par scoring_agent (voir contrat dans le docstring du module).
    index : resultat de load_index(), a charger une seule fois au demarrage du
            process (voir app/agents/rag_agent.py::get_index).
    """
    return process_house(house, index)


# --- CLI conserve pour tester ce module isolement --------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Agent 2 - RAG recommandations")
    parser.add_argument("--input", required=True, help="JSON maison (sortie de l'agent risques)")
    parser.add_argument("--output", default="resultat.json", help="Fichier JSON de sortie")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        house = json.load(f)

    index = load_index()
    result = generate_recommendations(house, index)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nResultat ecrit -> {args.output}")


if __name__ == "__main__":
    main()
