"""
Module « coût des travaux de résilience vs. gain économique » — version
honnête et sourcée (cf. docs/STRATEGIE_RETOUR_INVESTISSEMENT.md).

Règle du projet « aucune donnée simulée » : aucun montant n'est inventé.
Chaque € affiché est le produit d'une formule documentée (registre F-A1 à
F-D2 du doc) appliquée à des entrées réelles ou référencées, avec trois
statuts de sortie seulement : `calcule`, `fourchette`, `null`.

Point d'entrée : `app.economie.service.compute_retour_investissement`.
"""

from app.economie.service import compute_retour_investissement

__all__ = ["compute_retour_investissement"]
