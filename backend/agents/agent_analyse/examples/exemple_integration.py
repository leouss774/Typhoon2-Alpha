"""
Exemple d'utilisation de l'agent Digital Twin comme module Python.
Montre comment intégrer l'agent dans un système plus large (2D/3D simulation, carte).
"""
import json
import os
try:
    from ..digital_twin_agent import DigitalTwinAgent
except ImportError:
    from digital_twin_agent import DigitalTwinAgent

# ─── Exemple 1 : Utilisation basique ──────────────────────────────────────────
def exemple_basique():
    """Exemple minimal d'utilisation de genererAnalyse."""

    agent = DigitalTwinAgent(api_key=os.getenv("MISTRAL_API_KEY"))

    # Données du risk engine (normalement fournies par l'orchestrateur)
    donnees_risk_engine = {
        "coordonnees": {"lat": 43.2965, "lon": 5.3698},
        "commune": {"nom": "Marseille", "code_insee": "13055"},
        "georisques": {
            "zone_sismique": 2,
            "alea_inondation": "modere",
            "ppr_inondation": False,
            "retrait_gonflement_argile": "faible",
            "radon": 1
        },
        "open_meteo": {
            "temperature_moy_annuelle_c": 15.5,
            "temperature_max_record_c": 40.2,
            "precipitations_moy_annuelles_mm": 550,
            "jours_canicule_an": 20
        },
        "dvf": {
            "prix_m2_median_commune": 3200,
            "tendance_prix_12mois_pct": 2.5
        },
        "drias": {
            "horizon_2050": {
                "rcp85": {
                    "delta_temp_ete_c": 3.8,
                    "jours_canicule_supplementaires": 35
                }
            },
            "montee_eaux_cm_2050": 38
        }
    }

    formulaire = {
        "adresse": "10 La Canebière, 13001 Marseille",
        "type_bien": "appartement",
        "surface_m2": 75,
        "annee_construction": 1980,
        "valeur_bien": 280000
    }

    # 🚀 L'appel principal
    resultat = agent.genererAnalyse(donnees_risk_engine, formulaire)

    print("Score global :", resultat["score_global"]["note"])
    print("Classe :", resultat["score_global"]["classe"])
    return resultat


# ─── Exemple 2 : Intégration pour la carte/simulation ─────────────────────────
def exemple_integration_simulation(donnees_risk_engine: dict, formulaire: dict):
    """
    Fonction d'intégration pour le système de simulation 2D/3D et la carte.
    Retourne les données structurées pour le rendu.
    """
    agent = DigitalTwinAgent()

    # 1. Analyse principale
    analyse = agent.genererAnalyse(donnees_risk_engine, formulaire)

    # 2. Projection 2050 (les deux scénarios)
    donnees_drias = donnees_risk_engine.get("drias", {})
    proj_rcp45 = agent.projection2050(analyse, donnees_drias, "rcp45")
    proj_rcp85 = agent.projection2050(analyse, donnees_drias, "rcp85")

    # 3. Préparer les données pour la carte
    risques_pour_carte = []
    for nom_risque, risque in analyse.get("risques_actuels", {}).items():
        if isinstance(risque, dict):
            risques_pour_carte.append({
                "type": nom_risque,
                "score": risque.get("score", 0),
                "niveau": risque.get("niveau", "faible"),
                "couleur": _score_vers_couleur(risque.get("score", 0)),
                "lat": formulaire.get("lat", 0) or donnees_risk_engine.get("coordonnees", {}).get("lat", 0),
                "lon": formulaire.get("lon", 0) or donnees_risk_engine.get("coordonnees", {}).get("lon", 0),
                "label": nom_risque.replace("_", " ").title()
            })

    # 4. Préparer les données pour la simulation 2D/3D
    donnees_simulation = {
        "bien": analyse.get("bien", {}),
        "score_resilience": analyse.get("score_global", {}).get("score_resilience", 50),
        "score_vulnerabilite": analyse.get("score_global", {}).get("score_vulnerabilite", 50),
        "evenements_probables": analyse.get("simulation_periode", {}).get("evenements_probables", []),
        "periode": {
            "debut": "2024",
            "fin": "2050"
        },
        "evolution_risques_2050": {
            "rcp45": {
                nom: {
                    "score_actuel": analyse.get("risques_actuels", {}).get(nom, {}).get("score", 0),
                    "score_2050": proj_rcp45.get("risques_actuels", {}).get(nom, {}).get("score", 0)
                }
                for nom in analyse.get("risques_actuels", {}).keys()
            },
            "rcp85": {
                nom: {
                    "score_actuel": analyse.get("risques_actuels", {}).get(nom, {}).get("score", 0),
                    "score_2050": proj_rcp85.get("risques_actuels", {}).get(nom, {}).get("score", 0)
                }
                for nom in analyse.get("risques_actuels", {}).keys()
            }
        }
    }

    return {
        # Pour la carte des risques
        "carte": {
            "centre": donnees_risk_engine.get("coordonnees", {"lat": 0, "lon": 0}),
            "risques_zones": risques_pour_carte,
            "score_global": analyse.get("score_global", {}),
            "adresse": formulaire.get("adresse", "")
        },
        # Pour la simulation 2D/3D
        "simulation": donnees_simulation,
        # JSON brut complet
        "analyse_complete": {
            "actuelle": analyse,
            "projection_rcp45": proj_rcp45,
            "projection_rcp85": proj_rcp85
        }
    }


def _score_vers_couleur(score: float) -> str:
    """Convertit un score de risque en couleur hexadécimale pour la carte."""
    if score <= 20: return "#22c55e"    # Vert
    if score <= 35: return "#84cc16"    # Vert-jaune
    if score <= 50: return "#eab308"    # Jaune
    if score <= 65: return "#f97316"    # Orange
    if score <= 80: return "#ef4444"    # Rouge
    return "#7f1d1d"                     # Rouge foncé


# ─── Exemple 3 : Test de vulnérabilité pour clic sur carte ────────────────────
def exemple_clic_carte(lat: float, lon: float, donnees_contexte: dict = None):
    """
    Appelé quand l'utilisateur clique sur un point de la carte.
    Retourne rapidement un verdict avec explication.
    """
    agent = DigitalTwinAgent()
    return agent.testVulnerabilite(lat, lon, donnees_zone=donnees_contexte)


if __name__ == "__main__":
    # Démo du mode basique (nécessite une clé API)
    print("Exemple d'utilisation de l'agent Digital Twin")
    print("Pour lancer les tests complets : python main.py --test")
    print("Pour la démo sans API : python main.py --demo")
