"""Pondérations et niveaux de risque pour le scoring.

Définit le poids de chaque aléa dans le score global
ainsi que les seuils de niveaux de risque.
"""

# Poids de chaque aléa dans le calcul du score global
POIDS_ALEAS = {
    "rga": 1.5,          # Surpondéré : impact structurel majeur
    "inondation": 1.3,   # Important : dommages fréquents et coûteux
    "tempete": 1.0,      # Modéré
    "feu_foret": 0.8,    # Moins fréquent mais destructeur
    "submersion": 0.7,   # Côtier uniquement
}

# Seuils pour les niveaux de risque
SEUILS_NIVEAU = [
    (0, "faible"),
    (25, "modéré"),
    (50, "élevé"),
    (75, "critique"),
]


def get_niveau_risque(score: float) -> str:
    """Retourne le niveau de risque pour un score donné."""
    for seuil, niveau in reversed(SEUILS_NIVEAU):
        if score >= seuil:
            return niveau
    return "faible"


def get_couleur_risque(niveau: str) -> str:
    """Retourne la couleur associée à un niveau de risque."""
    palette = {
        "faible": "#22c55e",     # vert
        "modéré": "#eab308",     # jaune
        "élevé": "#f97316",      # orange
        "critique": "#ef4444",   # rouge
    }
    return palette.get(niveau, "#6b7280")
