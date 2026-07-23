"""Agent Analyste Risque - Appel à Claude avec prompt système.

Reçoit les données structurées du bien + scores déterministes,
envoie une requête à Claude avec le prompt système spécialisé,
et retourne une analyse structurée validée par Pydantic.
"""

from __future__ import annotations

import json
import logging

from backend.agent_graph.state import AnalyseRisque, AleaScore
from backend.agents.analyste_risque.prompts import SYSTEM_PROMPT, build_analysis_prompt
from backend.agents.analyste_risque.schemas import AnalyseRisqueOutput

logger = logging.getLogger(__name__)


def analyser_risques(
    client_form: dict,
    scores_par_alea: dict[str, float],
    score_global: float | None,
    raw_data: dict | None = None,
) -> AnalyseRisque:
    """Analyse qualitative des risques via Claude.

    Args:
        client_form: Données du formulaire client.
        scores_par_alea: Scores déterministes par aléa.
        score_global: Score global (0-100).
        raw_data: Données brutes additionnelles (DRIAS, etc.).

    Returns:
        AnalyseRisque structurée et validée.
    """
    prompt = build_analysis_prompt(
        adresse=client_form.get("adresse", "Inconnue"),
        type_bien=client_form.get("type_bien", "maison"),
        annee_construction=client_form.get("annee_construction", 2000),
        materiau=client_form.get("materiau_principal", "brique"),
        surface=client_form.get("surface_m2", 100),
        sous_sol=client_form.get("sous_sol", False),
        score_global=score_global or 50.0,
        scores_par_alea=scores_par_alea,
    )

    # TODO: Remplacer par un vrai appel LangChain/LangGraph à Claude
    # Exemple avec ChatAnthropic :
    # from langchain_anthropic import ChatAnthropic
    # llm = ChatAnthropic(model="claude-sonnet-4-20250514")
    # from backend.config.settings import get_settings
    # llm = ChatAnthropic(model=get_settings().ANTHROPIC_MODEL, api_key=get_settings().ANTHROPIC_API_KEY)
    # message = llm.invoke([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
    # raw_output = message.content

    # Pour l'instant, retour simulé
    raw_output = _simuler_reponse(scores_par_alea, score_global)
    parsed = json.loads(raw_output)

    return _convertir_en_analyse(parsed)


def _simuler_reponse(scores: dict[str, float], score_global: float | None) -> str:
    """Simule une réponse Claude pour le développement."""
    aleas = {
        "rga": "Retrait-gonflement des argiles",
        "inondation": "Inondation",
        "tempete": "Tempête",
        "feu_foret": "Feu de forêt",
        "submersion": "Submersion marine",
    }

    scores_alea = []
    for code, label in aleas.items():
        s = scores.get(code, 0.0)
        if s > 75:
            niveau = "critique"
        elif s > 50:
            niveau = "élevé"
        elif s > 25:
            niveau = "modéré"
        else:
            niveau = "faible"

        scores_alea.append({
            "code": code,
            "label": label,
            "score": s,
            "niveau": niveau,
            "justification": f"Analyse basée sur les données disponibles. Score: {s:.0f}/100 — niveau {niveau}.",
        })

    scores_tries = sorted(scores_alea, key=lambda x: x["score"], reverse=True)
    dominants = [s["code"] for s in scores_tries[:3] if s["score"] > 20]

    return json.dumps({
        "scores_par_alea": scores_alea,
        "risques_dominants": dominants,
        "synthese": f"Analyse terminée. Score global: {score_global:.0f}/100. "
        f"Risques dominants : {', '.join(dominants)}.",
    }, ensure_ascii=False)


def _convertir_en_analyse(parsed: dict) -> AnalyseRisque:
    """Convertit la réponse JSON brute en objet AnalyseRisque."""
    aleas = []
    for a in parsed.get("scores_par_alea", []):
        aleas.append(AleaScore(
            code=a["code"],
            label=a["label"],
            score=a["score"],
            niveau=a["niveau"],
        ))

    justifications = {a["code"]: a["justification"] for a in parsed.get("scores_par_alea", [])}

    return AnalyseRisque(
        scores_par_alea=aleas,
        risques_dominants=parsed.get("risques_dominants", []),
        justifications=justifications,
        synthese=parsed.get("synthese", ""),
    )
