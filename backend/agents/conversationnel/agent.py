"""Agent Conversationnel (Agent #3).

Agent de chat qui répond aux questions du client en exploitant
le contexte du rapport d'analyse déjà généré par les agents #1 et #2.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.agents.conversationnel.prompts import SYSTEM_PROMPT, build_chat_prompt

logger = logging.getLogger(__name__)


def repondre_question_client(
    question: str,
    rapport_contexte: dict,
    historique: list | None = None,
) -> str:
    """Répond à une question du client en utilisant le contexte du rapport.

    Args:
        question: Question posée par le client.
        rapport_contexte: Rapport d'analyse complet (scores, risques, recommandations).
        historique: Messages précédents de la conversation.

    Returns:
        Réponse textuelle à la question.
    """
    prompt = build_chat_prompt(
        question=question,
        rapport_contexte=rapport_contexte,
        historique=historique,
    )

    # TODO: Remplacer par un vrai appel LLM
    # from langchain_anthropic import ChatAnthropic
    # from backend.config.settings import get_settings
    # llm = ChatAnthropic(model=get_settings().ANTHROPIC_MODEL, api_key=get_settings().ANTHROPIC_API_KEY)
    # message = llm.invoke([{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}])
    # return message.content

    return _simuler_reponse(question, rapport_contexte)


def _simuler_reponse(question: str, rapport: dict) -> str:
    """Simule une réponse du chat pour le développement."""
    question_lower = question.lower()

    if "pourquoi" in question_lower or "risque" in question_lower:
        analyse = rapport.get("analyse_risque", {})
        risques = analyse.get("risques_dominants", [])
        synthese = analyse.get("synthese", "")
        return (
            f"D'après l'analyse de votre bien, les risques dominants sont : "
            f"{', '.join(risques)}. {synthese[:200]} "
            f"Souhaitez-vous plus de détails sur un risque en particulier ?"
        )

    if "coût" in question_lower or "prix" in question_lower or "combien" in question_lower:
        recos = rapport.get("recommandations", [])
        if recos:
            total_bas = sum(r.get("cout_estime_bas", 0) for r in recos)
            total_haut = sum(r.get("cout_estime_haut", 0) for r in recos)
            return (
                f"Le coût total estimé des travaux recommandés se situe entre "
                f"{total_bas:,.0f}€ et {total_haut:,.0f}€. "
                f"Chaque recommandation a sa propre fourchette de prix. "
                f"Souhaitez-vous le détail par poste de travaux ?"
            )
        return "Les recommandations de travaux n'ont pas encore été générées pour votre bien."

    if "travaux" in question_lower or "recommande" in question_lower or "priorité" in question_lower:
        recos = rapport.get("recommandations", [])
        if recos:
            lignes = "\n".join(
                f"- {r.get('titre')} (priorité {r.get('priorite')}) : "
                f"{r.get('cout_estime_bas'):,.0f}€-{r.get('cout_estime_haut'):,.0f}€, "
                f"gain de résilience {r.get('gain_resilience_pct')}%"
                for r in recos[:5]
            )
            return f"Voici les travaux prioritaires pour votre bien :\n{lignes}"
        return "Aucune recommandation de travaux n'est disponible actuellement."

    return (
        "Je peux vous renseigner sur les risques identifiés pour votre bien, "
        "le coût des travaux recommandés, ou les priorités d'intervention. "
        "Que souhaitez-vous savoir ?"
    )
