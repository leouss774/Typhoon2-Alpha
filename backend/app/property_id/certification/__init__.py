"""
Typhoon Certification — indicateur de confiance intégré au Property ID.

La certification n'est pas un produit final autonome.
C'est une section du Property ID qui résume le niveau de confiance
du bâtiment selon les critères de la plateforme Typhoon.

Architecture :
  - schemas.py    : modèles Pydantic (niveaux, badge, certification)
  - calculator.py : règles de calcul du niveau à partir des scores
  - badge.py      : métadonnées visuelles (couleur, icône, label)
  - service.py    : orchestration et cohérence

Principes :
  - Aucune nouvelle donnée métier : la certification dérive uniquement
    des scores existants (overall, climate, insurance).
  - Seuils isolés dans calculator.py pour modification sans toucher au code.
  - Recalcul automatique : si les scores changent, la certification suit.
"""

from __future__ import annotations
