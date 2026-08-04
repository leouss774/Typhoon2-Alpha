"""
Typhoon Property ID — identité numérique d'un bâtiment.

Généré automatiquement après un diagnostic réussi, le Property ID est
l'objet central partagé entre tous les cas d'usage Typhoon (Assurance,
Banque, Immobilier, Artisan, Certifications).

Ce package contient :
  - schemas.py   : modèles Pydantic de la structure Property ID
  - generator.py : construction du Property ID à partir des données
                   existantes (building_data, risk_scores, digital_twin)
  - service.py   : couche métier (génération, persistance légère)

Conventions (cf. README racine, section "Typhoon Property ID") :
  - Ne crée aucune nouvelle donnée métier — aggrège uniquement les
    sorties existantes des agents.
  - Les modules futurs (bank, real_estate, artisan, certifications)
    ajoutent leurs données via les sections optionnelles, sans modifier
    le noyau.
"""

from __future__ import annotations
