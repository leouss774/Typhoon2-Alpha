# -*- coding: utf-8 -*-
"""
Package de matching artisans : RGE (ADEME) et non-RGE (Recherche d'Entreprises).
"""

from __future__ import annotations

from app.matching.match_artisans_rge import (
    RECOMMANDATION_VERS_DOMAINE_ADEME,
    matcher_recommandation,
    calculer_score_objectif,
    rechercher_entreprises_rge,
)
from app.matching.generate_rapport_artisans import (
    CATEGORIES_NON_RGE,
    traiter_recommandation,
    _classifier_recommandation,
    _extraire_code_postal,
    _extraire_recommandations,
    generer_rapport,
    rechercher_entreprises_non_rge,
    formater_resultats_non_rge,
)

__all__ = [
    "RECOMMANDATION_VERS_DOMAINE_ADEME",
    "matcher_recommandation",
    "calculer_score_objectif",
    "rechercher_entreprises_rge",
    "CATEGORIES_NON_RGE",
    "traiter_recommandation",
    "_classifier_recommandation",
    "_extraire_code_postal",
    "_extraire_recommandations",
    "generer_rapport",
    "rechercher_entreprises_non_rge",
    "formater_resultats_non_rge",
]
