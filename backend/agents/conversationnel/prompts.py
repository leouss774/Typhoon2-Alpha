"""Prompts pour l'Agent Conversationnel (Agent #3).

Agent de chat qui répond aux questions du client en piochant
dans le contexte du rapport déjà généré.
"""

SYSTEM_PROMPT = """Tu es un conseiller en rénovation et adaptation climatique pour Typhoon, un service d'audit de résilience. Tu réponds aux questions des propriétaires sur leur diagnostic.

## Règles
- Tu as accès au rapport d'analyse complet de leur bien (scores, risques, recommandations, coûts)
- Réponds UNIQUEMENT en t'appuyant sur les informations du rapport
- Si on te demande quelque chose hors contexte, dis poliment que tu n'as pas l'information
- Sois pédagogue : explique les termes techniques simplement
- Reste court et précis (max 3-4 phrases par réponse)
- N'invente JAMAIS des chiffres ou des coûts

## Ton
Professionnel, rassurant, accessible. Tu es là pour aider le propriétaire à comprendre son diagnostic et à passer à l'action.
"""


def build_chat_prompt(question: str, rapport_contexte: dict, historique: list | None = None) -> str:
    """Construit le prompt utilisateur pour le chat."""
    rapport_str = _formatter_rapport(rapport_contexte)
    historique_str = ""
    if historique:
        historique_str = "\n".join(
            f"{'Client' if m.get('role') == 'user' else 'Conseiller'}: {m.get('content', '')}"
            for m in historique[-6:]  # garder les 6 derniers échanges
        )

    return f"""
## Contexte du rapport
{rapport_str}

## Historique récent
{historique_str or "Nouvelle conversation."}

## Question du client
{question}

Réponds de manière claire et concise en t'appuyant sur le rapport ci-dessus."""


def _formatter_rapport(rapport: dict) -> str:
    """Formate le rapport pour le prompt."""
    score = rapport.get("score_global", "N/A")
    analyse = rapport.get("analyse_risque", {})
    risques = analyse.get("risques_dominants", [])
    recommandations = rapport.get("recommandations", [])

    reco_str = ""
    for r in recommandations[:4]:
        reco_str += f"- {r.get('titre', '')}: {r.get('cout_estime_bas', 0):.0f}€-{r.get('cout_estime_haut', 0):.0f}€ (gain: {r.get('gain_resilience_pct', 0):.0f}%)\n"

    return f"""Score global: {score}/100
Risques dominants: {', '.join(risques) if risques else 'Non déterminés'}
Recommandations:
{reco_str or "Aucune recommandation disponible."}"""
