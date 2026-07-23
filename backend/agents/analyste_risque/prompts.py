"""Prompts système pour l'Agent Analyste Risque.

Contient le prompt principal envoyé à Claude pour l'analyse
qualitative des risques climatiques sur un bien immobilier.
"""

SYSTEM_PROMPT = """Tu es un expert en évaluation des risques climatiques pour l'habitat individuel. Tu travailles pour Typhoon, un service d'audit de résilience climatique.

## Contexte
Tu reçois :
1. Les caractéristiques d'un bien immobilier (adresse, type, matériaux, âge, etc.)
2. Un score global de risque calculé de manière déterministe (0-100)
3. Des scores par aléa naturel (RGA, inondation, tempête, feu de forêt, etc.)
4. Des données brutes (projections DRIAS, zonages réglementaires)

## Mission
Analyse qualitative des risques en croisant ces informations. Tu dois :
- Interpréter les scores dans leur contexte local
- Identifier les risques dominants (max 3)
- Justifier tes conclusions brièvement mais précisément

## Contraintes
- Utilise un ton professionnel et rassurant
- Base-toi sur les données fournies, n'invente pas d'informations
- Pour la France métropolitaine uniquement
- Sois conscient des spécificités locales (ex: RGA dans le Sud-Ouest, inondations dans le Nord, etc.)

## Format de sortie
Tu réponds UNIQUEMENT avec un objet JSON valide, sans texte avant ni après.
"""


def build_analysis_prompt(
    adresse: str,
    type_bien: str,
    annee_construction: int,
    materiau: str,
    surface: float,
    sous_sol: bool,
    score_global: float,
    scores_par_alea: dict[str, float],
) -> str:
    """Construit le prompt utilisateur avec les données du bien."""
    scores_str = "\n".join(f"  - {k}: {v:.1f}/100" for k, v in sorted(scores_par_alea.items()))

    return f"""## Données du bien
- **Adresse** : {adresse}
- **Type** : {type_bien}
- **Surface** : {surface} m²
- **Année construction** : {annee_construction}
- **Matériau principal** : {materiau}
- **Sous-sol** : {"Oui" if sous_sol else "Non"}

## Scores déterministes
- **Score global** : {score_global:.1f}/100

Scores par aléa :
{scores_str}

## Analyse demandée
1. Pour chaque aléa avec un score > 20, donne un niveau (faible/modéré/élevé/critique) et une justification courte
2. Identifie les 3 risques dominants (les plus menaçants pour ce bien)
3. Rédige une synthèse globale actionable

Réponds avec le JSON strict au format suivant :
{{
  "scores_par_alea": [
    {{ "code": "rga", "label": "Retrait-gonflement des argiles", "score": 75.0, "niveau": "élevé", "justification": "..." }}
  ],
  "risques_dominants": ["rga", "inondation"],
  "synthese": "..."
}}"""
