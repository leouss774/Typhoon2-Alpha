"""
Tests de l'agent Digital Twin sur 3 adresses réelles.
Vérifie que le JSON est toujours valide et cohérent.
"""
import json
import sys
import os
import time
import logging
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from digital_twin_agent import DigitalTwinAgent
from fallback import valider_champs_obligatoires
from tests.test_data import (
    ADRESSE_1_PARIS, ADRESSE_2_BORDEAUX, ADRESSE_3_NICE, DRIAS_FRANCE_GENERIQUE
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Tests")

# ─── Couleurs terminal ─────────────────────────────────────────────────────────
VERT = "\033[92m"
ROUGE = "\033[91m"
JAUNE = "\033[93m"
BLEU = "\033[94m"
RESET = "\033[0m"
GRAS = "\033[1m"


def afficher_resultat(nom_test: str, json_dict: dict, est_valide: bool):
    """Affiche le résultat d'un test de manière lisible."""
    status = f"{VERT}✅ VALIDE{RESET}" if est_valide else f"{ROUGE}❌ INVALIDE{RESET}"
    print(f"\n{'='*60}")
    print(f"{GRAS}{nom_test}{RESET} → {status}")
    print(f"{'='*60}")

    if "_erreur" in json_dict:
        print(f"{ROUGE}ERREUR : {json_dict['_erreur']}{RESET}")
        return

    sg = json_dict.get("score_global", {})
    meta = json_dict.get("meta", {})
    perf = json_dict.get("_performance", {})

    print(f"📍 Adresse    : {meta.get('adresse', 'N/A')}")
    print(f"🎯 Score      : {sg.get('note', 'N/A')}/100 (classe {sg.get('classe', '?')})")
    print(f"📝 Interp.    : {sg.get('interpretation', 'N/A')}")
    print(f"⏱️  Durée      : {perf.get('duree_analyse_s', 'N/A')}s")
    print(f"✔️  JSON OK    : {perf.get('json_valide', 'N/A')}")

    # Risques principaux
    risques = json_dict.get("risques_actuels", {})
    print(f"\n{BLEU}RISQUES ACTUELS :{RESET}")
    for nom, risque in risques.items():
        if isinstance(risque, dict):
            niveau = risque.get('niveau', '?')
            score = risque.get('score', '?')
            couleur = ROUGE if score >= 60 else (JAUNE if score >= 30 else VERT)
            print(f"  {couleur}• {nom:35s}: {niveau:15s} ({score}/100){RESET}")

    # Recommandations urgentes
    recs = json_dict.get("recommandations", {}).get("urgentes", [])
    if recs:
        print(f"\n{ROUGE}RECOMMANDATIONS URGENTES :{RESET}")
        for r in recs[:3]:
            print(f"  🚨 [{r.get('priorite', '?')}] {r.get('titre', '?')}")
            cout = r.get('cout_estime_eur')
            if cout:
                print(f"     → Coût estimé : {cout:,.0f}€")

    # Simulation période
    sim = json_dict.get("simulation_periode", {})
    if sim:
        print(f"\n{BLEU}SIMULATION :{RESET}")
        print(f"  Période      : {sim.get('periode_debut', '?')} → {sim.get('periode_fin', '?')}")
        cout_cumule = sim.get('cout_risque_cumule_estime')
        if cout_cumule:
            print(f"  Coût risques : {cout_cumule:,.0f}€")
        print(f"  Assurabilité : {sim.get('indice_assurabilite', '?')}")


def test_adresse(agent: DigitalTwinAgent, nom: str, data: dict) -> dict:
    """Lance un test sur une adresse et retourne le résultat."""
    print(f"\n{GRAS}{BLEU}🏠 Test : {nom}{RESET}")
    print(f"   Adresse : {data['formulaire']['adresse']}")

    resultat = agent.genererAnalyse(
        donneesRiskEngine=data["donnees_risk_engine"],
        formulaire=data["formulaire"]
    )

    est_valide, erreurs = valider_champs_obligatoires(resultat)
    if erreurs:
        print(f"{JAUNE}  ⚠️  Avertissements : {erreurs[:3]}{RESET}")

    afficher_resultat(nom, resultat, est_valide)
    return resultat


def test_vulnerability(agent: DigitalTwinAgent):
    """Test du mode vulnérabilité rapide."""
    print(f"\n{GRAS}{'='*60}{RESET}")
    print(f"{GRAS}{BLEU}⚡ TEST VULNÉRABILITÉ RAPIDE (clic sur carte){RESET}")
    print(f"{GRAS}{'='*60}{RESET}")

    # Zone de Nice (haute vulnérabilité)
    result = agent.testVulnerabilite(
        lat=43.7102,
        lon=7.2620,
        adresse="Boulevard Carnot, Nice",
        donneesZone={
            "zone_sismique": 4,
            "ppr_inondation": True,
            "distance_mer_m": 800,
            "risque_incendie": "eleve"
        }
    )

    print(f"\nVERDICT : {GRAS}{result.get('verdict', '?')}{RESET}")
    print(f"Score   : {result.get('score_risque', '?')}/100")
    print(f"Délai   : {result.get('delai_reponse_ms', '?')}ms")
    print(f"Action  : {result.get('action_immediate', '?')}")
    print(f"Expl.   : {result.get('explication', '?')[:200]}")

    risques = result.get("risques_identifies", [])
    if risques:
        print(f"\nRisques identifiés :")
        for r in risques[:5]:
            print(f"  • {r.get('type', '?')} → {r.get('niveau', '?')} : {r.get('detail', '')[:80]}")

    return result


def test_projection_2050(agent: DigitalTwinAgent, analyse_bordeaux: dict):
    """Test de la projection 2050."""
    print(f"\n{GRAS}{'='*60}{RESET}")
    print(f"{GRAS}{BLEU}🌡️  TEST PROJECTION 2050 (Bordeaux, RCP 8.5){RESET}")
    print(f"{GRAS}{'='*60}{RESET}")

    projection = agent.projection2050(
        analyseActuelle=analyse_bordeaux,
        donneesDrias=ADRESSE_2_BORDEAUX["donnees_risk_engine"]["drias"],
        scenario="rcp85"
    )

    sg_actuel = analyse_bordeaux.get("score_global", {}).get("note", 0)
    sg_2050 = projection.get("score_global", {}).get("note", 0)

    print(f"\nScore actuel : {sg_actuel}/100")
    print(f"Score 2050   : {sg_2050}/100")
    delta = round(sg_2050 - sg_actuel, 1)
    couleur = ROUGE if delta > 0 else VERT
    print(f"Évolution    : {couleur}{'+' if delta > 0 else ''}{delta} points{RESET}")

    # Comparer les risques
    risques_actuels = analyse_bordeaux.get("risques_actuels", {})
    risques_2050 = projection.get("risques_actuels", {})

    print(f"\nComparaison risques (actuel → 2050) :")
    for risque in ["inondation", "incendie_foret", "chaleur_extreme", "secheresse"]:
        score_a = risques_actuels.get(risque, {}).get("score", 0)
        score_b = risques_2050.get(risque, {}).get("score", 0)
        if score_a and score_b:
            delta_r = score_b - score_a
            c = ROUGE if delta_r > 0 else VERT
            print(f"  {risque:30s}: {score_a} → {c}{score_b} ({'+' if delta_r > 0 else ''}{delta_r}){RESET}")

    return projection


def sauvegarder_resultats(resultats: dict, chemin: str = "resultats_tests.json"):
    """Sauvegarde les résultats en JSON."""
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(resultats, f, ensure_ascii=False, indent=2)
    print(f"\n{VERT}💾 Résultats sauvegardés dans : {chemin}{RESET}")


def main():
    print(f"{GRAS}{'='*60}")
    print(f"  TESTS DIGITAL TWIN AGENT — Mistral Integration")
    print(f"{'='*60}{RESET}")

    # Initialiser l'agent (lira la clé depuis config.py ou MISTRAL_API_KEY)
    agent = DigitalTwinAgent()

    resultats = {}

    # ─── TEST 1 : Paris ───────────────────────────────────────────────────────
    analyse_paris = test_adresse(agent, "Paris 15e (Appartement)", ADRESSE_1_PARIS)
    resultats["paris"] = analyse_paris
    time.sleep(1)  # Respecter le rate limit

    # ─── TEST 2 : Bordeaux ────────────────────────────────────────────────────
    analyse_bordeaux = test_adresse(agent, "Bordeaux (Maison zone inondable)", ADRESSE_2_BORDEAUX)
    resultats["bordeaux"] = analyse_bordeaux
    time.sleep(1)

    # ─── TEST 3 : Nice ────────────────────────────────────────────────────────
    analyse_nice = test_adresse(agent, "Nice (Appartement littoral)", ADRESSE_3_NICE)
    resultats["nice"] = analyse_nice
    time.sleep(1)

    # ─── TEST 4 : Vulnérabilité rapide ────────────────────────────────────────
    vuln = test_vulnerability(agent)
    resultats["vulnerability_test"] = vuln
    time.sleep(1)

    # ─── TEST 5 : Projection 2050 ─────────────────────────────────────────────
    proj = test_projection_2050(agent, analyse_bordeaux)
    resultats["projection_2050_bordeaux"] = proj

    # ─── Résumé ───────────────────────────────────────────────────────────────
    print(f"\n{GRAS}{'='*60}")
    print(f"  RÉSUMÉ DES TESTS")
    print(f"{'='*60}{RESET}")

    adresses_tests = [
        ("Paris 15e", resultats["paris"]),
        ("Bordeaux", resultats["bordeaux"]),
        ("Nice", resultats["nice"])
    ]

    for nom, res in adresses_tests:
        valide, _ = valider_champs_obligatoires(res)
        sg = res.get("score_global", {})
        statut = f"{VERT}✅{RESET}" if valide else f"{ROUGE}❌{RESET}"
        print(f"  {statut} {nom:20s} | Score: {sg.get('note', '?'):5} | Classe: {sg.get('classe', '?')}")

    # Sauvegarder
    sauvegarder_resultats(resultats)

    return resultats


if __name__ == "__main__":
    main()
