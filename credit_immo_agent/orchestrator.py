"""
Orchestrateur principal.

Prend en entrée les sorties de l'agent de risque et de l'agent de
recommandation (déjà existants côté utilisateur), plus les données du
dossier de crédit, et produit la sortie JSON complète :
valorisation + projection + décision + plan de suivi.

Usage :
    python orchestrator.py \
        --risque data/exemple_risque.json \
        --recommandations data/exemple_recommandations.json \
        --dossier data/exemple_dossier.json
"""

import argparse
import json
import sys
from datetime import date

from agents.valuation_agent import valoriser, calculer_risque_pondere
from agents.projection_agent import projeter, appliquer_travaux
from agents.credit_decision_agent import calculer_ltv_glissant, decider
from agents.monitoring_agent import generer_plan


CHAMPS_OBLIGATOIRES_DOSSIER = ["valeur_marche_bien", "montant_emprunte", "duree_annees"]


def charger_json(chemin: str) -> dict:
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def valider_dossier(dossier: dict):
    manquants = [c for c in CHAMPS_OBLIGATOIRES_DOSSIER if dossier.get(c) is None]
    if manquants:
        raise ValueError(
            "Impossible de produire une décision : données obligatoires manquantes "
            f"dans le dossier de crédit : {manquants}. "
            "Merci de compléter le dossier avant de relancer l'analyse."
        )


def executer(risque: dict, recommandations: dict, dossier: dict) -> dict:
    valider_dossier(dossier)

    valeur_marche = dossier["valeur_marche_bien"]
    montant = dossier["montant_emprunte"]
    duree = dossier["duree_annees"]
    taux = dossier.get("taux_annuel_propose")
    tendance_marche = dossier.get("tendance_marche_annuelle", 0.0)

    hypotheses_globales = []
    if taux is None:
        taux = 0.034
        hypotheses_globales.append(
            f"taux_annuel_propose non fourni : valeur par défaut utilisée ({taux:.3%}), à remplacer par le taux réel."
        )
    if "tendance_marche_annuelle" not in dossier:
        hypotheses_globales.append(
            "tendance_marche_annuelle non fournie : hypothèse neutre (0%) utilisée par défaut."
        )

    zones = risque["zones"]
    score_2050 = risque["projection_2050"]["score_global"]
    annee_depart = date.today().year

    # --- Étape 1 & 2 : valorisation actuelle ---
    resultat_valo = valoriser(valeur_marche, zones)

    # --- Étape 3 : projections ---
    zones_ameliorees = appliquer_travaux(zones, recommandations)

    points_sans_travaux = projeter(
        valeur_ajustee=resultat_valo.valeur_ajustee,
        zones=zones,
        score_global_2050=score_2050,
        duree_annees=duree,
        tendance_marche_annuelle=tendance_marche,
        annee_depart=annee_depart,
    )

    # La valeur ajustée augmente immédiatement quand le risque baisse (travaux)
    zones_2050_brutes = risque.get("zones_2050", zones)
    zones_2050_ameliorees = appliquer_travaux(zones_2050_brutes, recommandations)
    valo_amelioree = valoriser(valeur_marche, zones_ameliorees)
    score_2050_ameliore = calculer_risque_pondere(zones_2050_ameliorees)

    points_avec_travaux = projeter(
        valeur_ajustee=valo_amelioree.valeur_ajustee,
        zones=zones_ameliorees,
        score_global_2050=score_2050_ameliore,
        duree_annees=duree,
        tendance_marche_annuelle=tendance_marche,
        annee_depart=annee_depart,
    )

    # --- Étape 4 : LTV glissant et décision ---
    ltv_sans_travaux = calculer_ltv_glissant(points_sans_travaux, montant, taux, duree)
    ltv_avec_travaux = calculer_ltv_glissant(points_avec_travaux, montant, taux, duree)

    recommandations_prioritaires = [
        r["titre"] for r in recommandations.values() if r.get("priorite") == 1
    ]

    decision = decider(
        ltv_sans_travaux=ltv_sans_travaux,
        ltv_avec_travaux=ltv_avec_travaux,
        risque_pondere_actuel=resultat_valo.risque_pondere,
        recommandations_prioritaires=recommandations_prioritaires,
    )

    # --- Étape 5 : plan de suivi (basé sur le LTV actuel, année 0) ---
    plan_suivi = generer_plan(ltv_sans_travaux[0].ltv)

    return {
        "valorisation": {
            "valeur_marche": resultat_valo.valeur_marche,
            "risque_pondere": resultat_valo.risque_pondere,
            "decote_pct": resultat_valo.decote_pct,
            "valeur_ajustee": resultat_valo.valeur_ajustee,
            "zones": zones,
            "hypotheses": resultat_valo.hypotheses + hypotheses_globales,
            "risques_presents": risque.get("risques_presents", []),
            "details_climat": risque.get("details_climat", {}),
        },
        "projection": {
            "scenario_sans_travaux": [
                {"annee": p.annee, "valeur": p.valeur_bien, "ltv": p.ltv}
                for p in ltv_sans_travaux
            ],
            "scenario_avec_travaux": [
                {"annee": p.annee, "valeur": p.valeur_bien, "ltv": p.ltv}
                for p in ltv_avec_travaux
            ],
        },
        "decision": {
            "statut": decision.statut,
            "justification": decision.justification,
            "conditions": decision.conditions,
            "prime_de_risque_suggeree": decision.prime_de_risque_suggeree,
        },
        "plan_de_suivi": plan_suivi,
        "avertissement": (
            "Cette sortie est une aide à la décision et ne constitue pas un engagement de crédit. "
            "La décision finale relève de l'établissement prêteur, conformément à son devoir de conseil "
            "et à son analyse du dossier (voir article 22 du RGPD sur les décisions automatisées)."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Agent de valorisation, décision de crédit et suivi immobilier")
    parser.add_argument("--risque", default="data/exemple_risque.json")
    parser.add_argument("--recommandations", default="data/exemple_recommandations.json")
    parser.add_argument("--dossier", default="data/exemple_dossier.json")
    parser.add_argument("--sortie", default=None, help="Chemin de sortie JSON (stdout si non précisé)")
    args = parser.parse_args()

    try:
        risque = charger_json(args.risque)
        recommandations = charger_json(args.recommandations)
        dossier = charger_json(args.dossier)
        resultat = executer(risque, recommandations, dossier)
    except ValueError as e:
        print(json.dumps({"erreur": str(e)}, ensure_ascii=False, indent=2))
        sys.exit(1)

    sortie_json = json.dumps(resultat, ensure_ascii=False, indent=2)
    if args.sortie:
        with open(args.sortie, "w", encoding="utf-8") as f:
            f.write(sortie_json)
        print(f"Résultat écrit dans {args.sortie}")
    else:
        print(sortie_json)


if __name__ == "__main__":
    main()
