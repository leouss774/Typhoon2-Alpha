"""
Point d'entrée principal du Digital Twin Agent.
Peut être utilisé en CLI ou importé comme module.

Usage CLI :
    python main.py --adresse "15 rue Lacordaire, 75015 Paris" --api-key "sk-..."
    python main.py --test  # Lance les tests sur 3 adresses
    python main.py --demo  # Demo avec données fictives (sans API key)
"""
import argparse
import json
import sys
import os
from pathlib import Path

# Forcer UTF-8 sur Windows pour les emojis
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ─── Point d'entrée ───────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="🏠 Digital Twin Agent — Analyse de risques immobiliers par IA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python main.py --test
  python main.py --adresse "8 rue de la Paix, 75001 Paris" --api-key "sk-..."
  python main.py --input donnees.json --output resultat.json
        """
    )
    parser.add_argument("--api-key", type=str, help="Clé API Mistral (ou via MISTRAL_API_KEY env)")
    parser.add_argument("--adresse", type=str, help="Adresse à analyser")
    parser.add_argument("--input", type=str, help="Fichier JSON d'entrée (risk engine + formulaire)")
    parser.add_argument("--output", type=str, help="Fichier de sortie JSON", default="resultat_analyse.json")
    parser.add_argument("--test", action="store_true", help="Lancer les tests sur 3 adresses réelles")
    parser.add_argument("--demo", action="store_true", help="Demo sans API (données fictives)")
    parser.add_argument("--vuln", action="store_true", help="Test vulnérabilité rapide")
    parser.add_argument("--lat", type=float, help="Latitude pour le test de vulnérabilité")
    parser.add_argument("--lon", type=float, help="Longitude pour le test de vulnérabilité")
    parser.add_argument("--2050", action="store_true", dest="proj2050", help="Générer la projection 2050")
    parser.add_argument("--scenario", type=str, default="rcp85",
                        choices=["rcp45", "rcp85"], help="Scénario climatique 2050")
    parser.add_argument("--verbose", "-v", action="store_true", help="Mode verbeux")

    args = parser.parse_args()

    # Configurer l'API key
    if args.api_key:
        os.environ["MISTRAL_API_KEY"] = args.api_key

    # ─── Mode TEST ────────────────────────────────────────────────────────────
    if args.test:
        print("🧪 Lancement des tests sur 3 adresses réelles...")
        from tests.test_agent import main as run_tests
        run_tests()
        return

    # ─── Mode DEMO ────────────────────────────────────────────────────────────
    if args.demo:
        demo_mode()
        return

    # ─── Mode ANALYSE depuis fichier JSON ─────────────────────────────────────
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)

        formulaire = data.get("formulaire", {})
        donnees_risk_engine = data.get("donnees_risk_engine", {})
        donnees_drias = donnees_risk_engine.get("drias", {})

        try:
            from .digital_twin_agent import DigitalTwinAgent
        except ImportError:
            from digital_twin_agent import DigitalTwinAgent
        agent = DigitalTwinAgent()

        print(f"🚀 Analyse de : {formulaire.get('adresse', 'adresse inconnue')}")

        if args.proj2050:
            # Analyse complète avec projection 2050
            resultat = agent.analyseComplete(donnees_risk_engine, formulaire, donnees_drias)
        else:
            resultat = agent.genererAnalyse(donnees_risk_engine, formulaire)

        # Sauvegarder
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(resultat, f, ensure_ascii=False, indent=2)
        print(f"✅ Résultat sauvegardé dans : {args.output}")

        # Afficher résumé
        if not args.proj2050:
            sg = resultat.get("score_global", {})
            print(f"\n📊 SCORE : {sg.get('note', '?')}/100 (classe {sg.get('classe', '?')})")
            print(f"   {sg.get('interpretation', '')}")
        return

    # ─── Mode VULNÉRABILITÉ ───────────────────────────────────────────────────
    if args.vuln:
        if not args.lat or not args.lon:
            print("❌ --lat et --lon requis pour le test de vulnérabilité")
            sys.exit(1)

        try:
            from .digital_twin_agent import DigitalTwinAgent
        except ImportError:
            from digital_twin_agent import DigitalTwinAgent
        agent = DigitalTwinAgent()

        print(f"⚡ Test vulnérabilité : ({args.lat}, {args.lon})")
        result = agent.testVulnerabilite(
            lat=args.lat,
            lon=args.lon,
            adresse=args.adresse or ""
        )

        print(f"\nVERDICT : {result.get('verdict', '?')}")
        print(f"Score   : {result.get('score_risque', '?')}/100")
        print(f"Délai   : {result.get('delai_reponse_ms', '?')}ms")
        print(f"\n{result.get('explication', '')}")
        print(f"\n→ Action : {result.get('action_immediate', '')}")

        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        return

    # ─── Aide si aucun argument ───────────────────────────────────────────────
    parser.print_help()


def demo_mode():
    """Demo en mode local sans appel API — génère un JSON d'exemple."""
    print("🎭 MODE DEMO (sans API Mistral)")
    print("Génération d'un JSON de démonstration...\n")

    demo_json = {
        "meta": {
            "version": "2.0",
            "date_analyse": "2024-07-23T14:00:00",
            "adresse": "42 Avenue des Champs-Élysées, 75008 Paris",
            "coordonnees": {"lat": 48.8698, "lon": 2.3078},
            "horizon_analyse": "2024-2050",
            "sources_donnees": ["BDNB", "Géorisques", "IGN", "Open-Meteo", "CATNAT", "DVF", "DRIAS"]
        },
        "bien": {
            "type": "appartement",
            "surface_m2": 95,
            "annee_construction": 1910,
            "etages": 4,
            "materiaux_principaux": ["pierre de taille", "parquet"],
            "dpe_classe": "E",
            "valeur_venale_estimee": 1200000,
            "surface_terrain_m2": None
        },
        "risques_actuels": {
            "inondation": {"niveau": "faible", "score": 20, "present_zone_ppr": False,
                           "explication": "Zone légèrement en hauteur, hors périmètre PPR inondation.",
                           "source": "Géorisques", "derniere_occurrence": None, "periode_retour_ans": None},
            "seisme": {"niveau": "negligeable", "score": 5, "present_zone_ppr": False,
                       "explication": "Zone de sismicité 1 (très faible) selon classement national.",
                       "source": "Géorisques", "derniere_occurrence": None, "periode_retour_ans": None},
            "retrait_gonflement_argiles": {"niveau": "modere", "score": 45, "present_zone_ppr": False,
                                           "explication": "Présence de sols argileux sensibles à la sécheresse. Risque sur les fondations.",
                                           "source": "Géorisques", "derniere_occurrence": None, "periode_retour_ans": None},
            "incendie_foret": {"niveau": "negligeable", "score": 5, "present_zone_ppr": False,
                               "explication": "Zone urbaine dense, aucune forêt à proximité.",
                               "source": "IGN/BDIFF", "derniere_occurrence": None, "periode_retour_ans": None},
            "mouvement_terrain": {"niveau": "faible", "score": 15, "present_zone_ppr": False,
                                  "explication": "Terrain stable, pas de cavité souterraine signalée dans un rayon de 200m.",
                                  "source": "Géorisques", "derniere_occurrence": None, "periode_retour_ans": None},
            "radon": {"niveau": "negligeable", "score": 10, "present_zone_ppr": False,
                      "explication": "Potentiel radon faible en région parisienne.",
                      "source": "IRSN", "derniere_occurrence": None, "periode_retour_ans": None},
            "tempete": {"niveau": "modere", "score": 35, "present_zone_ppr": False,
                        "explication": "Région Île-de-France exposée aux tempêtes hivernales.",
                        "source": "Météo-France", "derniere_occurrence": None, "periode_retour_ans": None},
            "chaleur_extreme": {"niveau": "eleve", "score": 65, "present_zone_ppr": False,
                                "explication": "îlot de chaleur urbain intensif. Bâtiment ancien sans isolation thermique efficace.",
                                "source": "Open-Meteo/DRIAS", "derniere_occurrence": "2023-08", "periode_retour_ans": 5},
            "pollution_sols": {"niveau": "faible", "score": 20, "present_zone_ppr": False,
                               "explication": "Aucun site BASIAS/BASOL dans un rayon de 300m.",
                               "source": "BASIAS/BASOL", "derniere_occurrence": None, "periode_retour_ans": None},
            "submersion_marine": {"niveau": "negligeable", "score": 5, "present_zone_ppr": False,
                                  "explication": "À 250km de la côte. Aucun risque de submersion marine.",
                                  "source": "Géorisques/SHOM", "derniere_occurrence": None, "periode_retour_ans": None}
        },
        "risques_futurs_2050": {
            "scenario_rcp45": {
                "inondation": {"niveau": "modere", "score": 35, "explication": "Risque accru avec augmentation des pluies intenses."},
                "incendie_foret": {"niveau": "negligeable", "score": 8, "explication": "Zone urbaine, risque limité même en 2050."},
                "chaleur_extreme": {"niveau": "tres_eleve", "score": 85, "explication": "+18 jours de canicule supplémentaires."},
                "submersion_marine": {"niveau": "negligeable", "score": 5, "explication": "Distance marine trop importante."},
                "secheresse": {"niveau": "eleve", "score": 70, "explication": "Sécheresses estivales plus fréquentes et intenses."},
                "delta_temperature_celsius": 1.8,
                "delta_precipitations_pct": -12
            },
            "scenario_rcp85": {
                "inondation": {"niveau": "eleve", "score": 55, "explication": "Précipitations hivernales très intenses, crues soudaines."},
                "incendie_foret": {"niveau": "faible", "score": 15, "explication": "Légère augmentation dans les parcs urbains."},
                "chaleur_extreme": {"niveau": "tres_eleve", "score": 95, "explication": "+28 jours de canicule, vagues de chaleur mortelles."},
                "submersion_marine": {"niveau": "negligeable", "score": 5, "explication": "Non applicable."},
                "secheresse": {"niveau": "tres_eleve", "score": 88, "explication": "Sécheresses chroniques, retrait-gonflement aggravé."},
                "delta_temperature_celsius": 3.2,
                "delta_precipitations_pct": -22
            }
        },
        "score_global": {
            "note": 32,
            "classe": "B",
            "interpretation": "Risque modéré à faible. Principal enjeu : adaptation à la chaleur urbaine et rénovation énergétique.",
            "score_resilience": 68,
            "score_exposition": 32,
            "score_vulnerabilite": 40
        },
        "recommandations": {
            "urgentes": [
                {"id": "REC_001", "titre": "Isolation thermique renforcée (ITE)",
                 "description": "Installer une isolation thermique par l'extérieur pour réduire l'îlot de chaleur et améliorer le DPE E vers C.",
                 "categorie": "energetique", "risque_cible": "chaleur_extreme",
                 "cout_estime_eur": 35000, "gain_resilience_points": 15, "priorite": 1,
                 "aides_financieres": ["MaPrimeRénov'", "Eco-PTZ", "Certificats Économie d'Énergie"]}
            ],
            "court_terme": [
                {"id": "REC_002", "titre": "Système de climatisation réversible",
                 "description": "Installer une pompe à chaleur air-air pour gérer les épisodes de chaleur extrême.",
                 "categorie": "energetique", "risque_cible": "chaleur_extreme",
                 "cout_estime_eur": 8000, "gain_resilience_points": 8, "priorite": 2,
                 "aides_financieres": ["MaPrimeRénov'"]},
                {"id": "REC_003", "titre": "Vérification des fondations",
                 "description": "Audit des fondations face au retrait-gonflement des argiles, surtout sous RCP 8.5.",
                 "categorie": "structurel", "risque_cible": "retrait_gonflement_argiles",
                 "cout_estime_eur": 2500, "gain_resilience_points": 5, "priorite": 2,
                 "aides_financieres": []}
            ],
            "moyen_terme": [
                {"id": "REC_004", "titre": "Toiture végétalisée ou brise-soleil",
                 "description": "Réduire l'absorption solaire et l'effet îlot de chaleur urbain.",
                 "categorie": "adaptation_climatique", "risque_cible": "chaleur_extreme",
                 "cout_estime_eur": 15000, "gain_resilience_points": 10, "priorite": 3,
                 "aides_financieres": ["Aides locales Paris"]}
            ],
            "long_terme_2050": [
                {"id": "REC_005", "titre": "Adaptation structurelle climatique 2050",
                 "description": "Révision complète du système constructif pour résistance aux sécheresses chroniques (RCP 8.5).",
                 "categorie": "adaptation_climatique", "risque_cible": "secheresse",
                 "cout_estime_eur": 45000, "gain_resilience_points": 20, "priorite": 4,
                 "aides_financieres": ["Fonds européens", "Plan National Adaptation Climatique"]}
            ]
        },
        "diagnostic_energetique": {
            "consommation_kwh_m2_an": 285,
            "emissions_co2_kg_m2_an": 58,
            "potentiel_renovation": "eleve",
            "economies_estimees_an": 4200,
            "aides_disponibles": ["MaPrimeRénov' Sérénité", "Eco-PTZ 50000€", "TVA 5.5%"]
        },
        "simulation_periode": {
            "periode_debut": "2024",
            "periode_fin": "2050",
            "evenements_probables": [
                {"type": "Vague de chaleur extrême", "probabilite_pct": 92,
                 "impact_estime": "Dommages isolation, surcoût énergie +3000€/an", "annee_probable": "2026-2030"},
                {"type": "Épisode de sécheresse sévère", "probabilite_pct": 75,
                 "impact_estime": "Tassement des fondations, fissures estimées 8000-25000€", "annee_probable": "2027-2035"},
                {"type": "Tempête hivernale intense", "probabilite_pct": 65,
                 "impact_estime": "Dommages toiture et façade, 5000-15000€", "annee_probable": "2025-2040"}
            ],
            "cout_risque_cumule_estime": 85000,
            "indice_assurabilite": "standard"
        },
        "donnees_marche": {
            "prix_m2_median_commune": 10200,
            "tendance_12mois_pct": -1.8,
            "impact_risque_sur_valeur_pct": -3.5,
            "valeur_ajustee_risques": 1158000,
            "liquidite_marche": "elevee"
        },
        "_performance": {
            "mode": "demo",
            "duree_analyse_s": 0,
            "json_valide": True,
            "model_utilise": "demo"
        }
    }

    print(json.dumps(demo_json, ensure_ascii=False, indent=2))
    print("\n✅ JSON démo généré avec succès !")
    print("💡 Pour une analyse réelle, utilisez : python main.py --test --api-key 'votre-clé'")


if __name__ == "__main__":
    main()
