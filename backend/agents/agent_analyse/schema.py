"""
Schéma JSON du contrat Digital Twin.
Définit la structure complète de la sortie de l'agent.
"""
from typing import Optional

# ─── Schéma JSON du contrat (format cible de sortie Mistral) ──────────────────
CONTRACT_JSON_SCHEMA = {
    "type": "object",
    "required": [
        "meta", "bien", "risques_actuels", "risques_futurs_2050",
        "score_global", "recommandations", "diagnostic_energetique",
        "simulation_periode"
    ],
    "properties": {
        "meta": {
            "type": "object",
            "description": "Métadonnées de l'analyse",
            "properties": {
                "version": {"type": "string"},
                "date_analyse": {"type": "string", "format": "date-time"},
                "adresse": {"type": "string"},
                "coordonnees": {
                    "type": "object",
                    "properties": {
                        "lat": {"type": "number"},
                        "lon": {"type": "number"}
                    }
                },
                "horizon_analyse": {"type": "string"},
                "sources_donnees": {"type": "array", "items": {"type": "string"}}
            }
        },
        "bien": {
            "type": "object",
            "description": "Caractéristiques du bien immobilier",
            "properties": {
                "type": {"type": "string"},
                "surface_m2": {"type": "number"},
                "annee_construction": {"type": "integer"},
                "etages": {"type": "integer"},
                "materiaux_principaux": {"type": "array", "items": {"type": "string"}},
                "dpe_classe": {"type": "string"},
                "valeur_venale_estimee": {"type": "number"},
                "surface_terrain_m2": {"type": "number"}
            }
        },
        "risques_actuels": {
            "type": "object",
            "description": "Évaluation des risques au moment présent",
            "properties": {
                "inondation": {"$ref": "#/definitions/risque"},
                "seisme": {"$ref": "#/definitions/risque"},
                "retrait_gonflement_argiles": {"$ref": "#/definitions/risque"},
                "incendie_foret": {"$ref": "#/definitions/risque"},
                "mouvement_terrain": {"$ref": "#/definitions/risque"},
                "radon": {"$ref": "#/definitions/risque"},
                "tempete": {"$ref": "#/definitions/risque"},
                "chaleur_extreme": {"$ref": "#/definitions/risque"},
                "pollution_sols": {"$ref": "#/definitions/risque"},
                "submersion_marine": {"$ref": "#/definitions/risque"}
            }
        },
        "risques_futurs_2050": {
            "type": "object",
            "description": "Projection des risques à l'horizon 2050 (données DRIAS)",
            "properties": {
                "scenario_rcp45": {
                    "type": "object",
                    "description": "Scénario climatique modéré (+2°C)",
                    "properties": {
                        "inondation": {"$ref": "#/definitions/risque"},
                        "incendie_foret": {"$ref": "#/definitions/risque"},
                        "chaleur_extreme": {"$ref": "#/definitions/risque"},
                        "submersion_marine": {"$ref": "#/definitions/risque"},
                        "secheresse": {"$ref": "#/definitions/risque"},
                        "delta_temperature_celsius": {"type": "number"},
                        "delta_precipitations_pct": {"type": "number"}
                    }
                },
                "scenario_rcp85": {
                    "type": "object",
                    "description": "Scénario climatique pessimiste (+4°C)",
                    "properties": {
                        "inondation": {"$ref": "#/definitions/risque"},
                        "incendie_foret": {"$ref": "#/definitions/risque"},
                        "chaleur_extreme": {"$ref": "#/definitions/risque"},
                        "submersion_marine": {"$ref": "#/definitions/risque"},
                        "secheresse": {"$ref": "#/definitions/risque"},
                        "delta_temperature_celsius": {"type": "number"},
                        "delta_precipitations_pct": {"type": "number"}
                    }
                }
            }
        },
        "score_global": {
            "type": "object",
            "description": "Score de risque global",
            "properties": {
                "note": {"type": "number", "minimum": 0, "maximum": 100},
                "classe": {"type": "string", "enum": ["A", "B", "C", "D", "E", "F"]},
                "interpretation": {"type": "string"},
                "score_resilience": {"type": "number", "minimum": 0, "maximum": 100},
                "score_exposition": {"type": "number", "minimum": 0, "maximum": 100},
                "score_vulnerabilite": {"type": "number", "minimum": 0, "maximum": 100}
            }
        },
        "recommandations": {
            "type": "object",
            "description": "Recommandations structurées par urgence et catégorie",
            "properties": {
                "urgentes": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/recommandation"}
                },
                "court_terme": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/recommandation"}
                },
                "moyen_terme": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/recommandation"}
                },
                "long_terme_2050": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/recommandation"}
                }
            }
        },
        "diagnostic_energetique": {
            "type": "object",
            "description": "Analyse énergétique du bien",
            "properties": {
                "consommation_kwh_m2_an": {"type": "number"},
                "emissions_co2_kg_m2_an": {"type": "number"},
                "potentiel_renovation": {"type": "string"},
                "economies_estimees_an": {"type": "number"},
                "aides_disponibles": {"type": "array", "items": {"type": "string"}}
            }
        },
        "simulation_periode": {
            "type": "object",
            "description": "Données de simulation pour la période analysée",
            "properties": {
                "periode_debut": {"type": "string"},
                "periode_fin": {"type": "string"},
                "evenements_probables": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string"},
                            "probabilite_pct": {"type": "number"},
                            "impact_estime": {"type": "string"},
                            "annee_probable": {"type": "string"}
                        }
                    }
                },
                "cout_risque_cumule_estime": {"type": "number"},
                "indice_assurabilite": {"type": "string"}
            }
        },
        "donnees_marche": {
            "type": "object",
            "description": "Données DVF et tendances marché",
            "properties": {
                "prix_m2_median_commune": {"type": "number"},
                "tendance_12mois_pct": {"type": "number"},
                "impact_risque_sur_valeur_pct": {"type": "number"},
                "valeur_ajustee_risques": {"type": "number"},
                "liquidite_marche": {"type": "string"}
            }
        }
    },
    "definitions": {
        "risque": {
            "type": "object",
            "properties": {
                "niveau": {
                    "type": "string",
                    "enum": ["negligeable", "faible", "modere", "eleve", "tres_eleve"]
                },
                "score": {"type": "number", "minimum": 0, "maximum": 100},
                "present_zone_ppr": {"type": "boolean"},
                "explication": {"type": "string"},
                "source": {"type": "string"},
                "derniere_occurrence": {"type": "string"},
                "periode_retour_ans": {"type": "integer"}
            },
            "required": ["niveau", "score", "explication"]
        },
        "recommandation": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "titre": {"type": "string"},
                "description": {"type": "string"},
                "categorie": {
                    "type": "string",
                    "enum": ["structurel", "energetique", "assurance", "amenagement",
                             "adaptation_climatique", "administratif", "securite"]
                },
                "risque_cible": {"type": "string"},
                "cout_estime_eur": {"type": "number"},
                "gain_resilience_points": {"type": "number"},
                "priorite": {"type": "integer", "minimum": 1, "maximum": 5},
                "aides_financieres": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["id", "titre", "description", "categorie", "priorite"]
        }
    }
}

# ─── Schéma simplifié pour le test de vulnérabilité ───────────────────────────
VULNERABILITY_TEST_SCHEMA = {
    "type": "object",
    "required": ["verdict", "score_risque", "risques_identifies", "explication", "action_immediate"],
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["SUR", "ACCEPTABLE", "VIGILANCE", "RISQUE_ELEVE", "DANGER"]
        },
        "score_risque": {"type": "number", "minimum": 0, "maximum": 100},
        "risques_identifies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "niveau": {"type": "string"},
                    "detail": {"type": "string"}
                }
            }
        },
        "explication": {"type": "string"},
        "action_immediate": {"type": "string"},
        "delai_reponse_ms": {"type": "integer"}
    }
}
