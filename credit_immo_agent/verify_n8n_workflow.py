"""
Vérificateur du workflow n8n `credit_agent`.

Contrôle statique (structure du JSON exporté par n8n) + contrôle dynamique
optionnel (ping des URLs d'outils) pour détecter les problèmes AVANT
l'exécution — comme celui observé sur `dvf_comparables` dans la capture
d'écran fournie (nœud en erreur).

Usage :
    python verify_n8n_workflow.py n8n/credit_agent_workflow.json
    python verify_n8n_workflow.py n8n/credit_agent_workflow.json --ping-urls
"""

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Resultat:
    niveau: str  # "ok" | "avertissement" | "erreur"
    message: str


@dataclass
class RapportVerification:
    resultats: List[Resultat] = field(default_factory=list)

    def ok(self, msg):
        self.resultats.append(Resultat("ok", msg))

    def avertissement(self, msg):
        self.resultats.append(Resultat("avertissement", msg))

    def erreur(self, msg):
        self.resultats.append(Resultat("erreur", msg))

    @property
    def a_des_erreurs(self) -> bool:
        return any(r.niveau == "erreur" for r in self.resultats)

    def resume(self) -> dict:
        return {
            "total": len(self.resultats),
            "ok": sum(1 for r in self.resultats if r.niveau == "ok"),
            "avertissements": sum(1 for r in self.resultats if r.niveau == "avertissement"),
            "erreurs": sum(1 for r in self.resultats if r.niveau == "erreur"),
        }


# URLs connues comme non garanties / sans SLA officiel, à signaler même si le
# workflow est structurellement correct (c'est un avertissement métier, pas
# une erreur de structure).
URLS_NON_GARANTIES = {
    "api.cquest.org": "API DVF communautaire, sans SLA garanti (voir README du projet). "
                       "A causé un nœud en erreur dans votre propre capture d'écran.",
}

CONSTRAINTES_ATTENDUES_DANS_LE_PROMPT = [
    "aide à la décision",
    "RGPD",
    "montant_emprunte",
    "duree_annees",
    "gain_resilience",
    "confiance",
]


def charger_workflow(chemin: str) -> dict:
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)


def trouver_noeuds(workflow: dict, type_n8n: str) -> List[dict]:
    return [n for n in workflow.get("nodes", []) if n.get("type") == type_n8n]


def verifier_structure(workflow: dict, rapport: RapportVerification):
    noms_attendus = {
        "n8n-nodes-base.formTrigger": "formulaire de saisie",
        "@n8n/n8n-nodes-langchain.agent": "agent LLM principal",
        "n8n-nodes-base.form": "formulaire de sortie / rapport",
    }
    for type_node, description in noms_attendus.items():
        noeuds = trouver_noeuds(workflow, type_node)
        if noeuds:
            rapport.ok(f"Nœud {description} présent ({type_node}) : {[n['name'] for n in noeuds]}")
        else:
            rapport.erreur(f"Nœud {description} MANQUANT ({type_node})")

    modeles = [
        n for n in workflow.get("nodes", [])
        if n.get("type", "").startswith("@n8n/n8n-nodes-langchain.lmChat")
    ]
    if modeles:
        rapport.ok(f"Modèle(s) de langage connecté(s) : {[n['name'] for n in modeles]}")
    else:
        rapport.erreur("Aucun nœud de modèle de langage (lmChat...) trouvé — l'agent ne peut pas fonctionner sans.")

    outils = trouver_noeuds(workflow, "n8n-nodes-base.httpRequestTool")
    if outils:
        rapport.ok(f"{len(outils)} outil(s) HTTP connecté(s) : {[n['name'] for n in outils]}")
    else:
        rapport.avertissement("Aucun outil HTTP trouvé — l'agent ne pourra pas géocoder ni consulter DVF lui-même.")


def verifier_formulaire_entree(workflow: dict, rapport: RapportVerification):
    triggers = trouver_noeuds(workflow, "n8n-nodes-base.formTrigger")
    if not triggers:
        return
    champs = triggers[0]["parameters"].get("formFields", {}).get("values", [])
    noms_champs = {c["fieldName"]: c for c in champs}

    obligatoires_attendus = ["montant_emprunte", "duree_annees"]
    for champ in obligatoires_attendus:
        if champ not in noms_champs:
            rapport.erreur(f"Champ obligatoire '{champ}' absent du formulaire d'entrée.")
        elif not noms_champs[champ].get("requiredField"):
            rapport.erreur(
                f"Champ '{champ}' présent mais PAS marqué requiredField=true — "
                "l'agent recevra parfois cette donnée vide, contrairement à la contrainte du prompt."
            )
        else:
            rapport.ok(f"Champ obligatoire '{champ}' correctement marqué requis.")

    champs_json_attendus = ["building_data_json", "risk_scores_json", "recommendations_json", "digital_twin_json"]
    manquants = [c for c in champs_json_attendus if c not in noms_champs]
    if manquants:
        rapport.avertissement(f"Champs JSON des agents amont absents du formulaire : {manquants}")
    else:
        rapport.ok("Tous les champs JSON des agents amont (building_data, risk_scores, recommendations, digital_twin) sont présents.")

    # Vérifie que ces champs JSON ne sont pas marqués obligatoires (ils doivent rester optionnels)
    for c in champs_json_attendus:
        if c in noms_champs and noms_champs[c].get("requiredField"):
            rapport.avertissement(
                f"'{c}' est marqué obligatoire dans le formulaire — cela empêche un usage sans les agents amont, "
                "alors que le prompt système prévoit explicitement ce cas (estimation via DVF)."
            )


def verifier_prompt_systeme(workflow: dict, rapport: RapportVerification):
    agents = trouver_noeuds(workflow, "@n8n/n8n-nodes-langchain.agent")
    for agent in agents:
        system_message = agent.get("parameters", {}).get("options", {}).get("systemMessage", "")
        if not system_message:
            rapport.erreur(f"Nœud agent '{agent['name']}' n'a AUCUN systemMessage défini.")
            continue

        for constrainte in CONSTRAINTES_ATTENDUES_DANS_LE_PROMPT:
            if constrainte.lower() not in system_message.lower():
                rapport.avertissement(
                    f"Le systemMessage de '{agent['name']}' ne mentionne pas explicitement « {constrainte} »."
                )
        rapport.ok(f"systemMessage de '{agent['name']}' présent ({len(system_message)} caractères).")

        # Détecte un piège classique : formule d'addition au lieu de composition multiplicative
        if re.search(r"gain_resilience.{0,20}\+", system_message):
            rapport.erreur(
                "Le systemMessage semble additionner les gain_resilience au lieu de les composer "
                "multiplicativement — risque de dépasser 100% de résilience."
            )


def verifier_urls_outils(workflow: dict, rapport: RapportVerification, ping: bool):
    outils = trouver_noeuds(workflow, "n8n-nodes-base.httpRequestTool")
    for outil in outils:
        url = outil.get("parameters", {}).get("url", "")
        for domaine, avertissement in URLS_NON_GARANTIES.items():
            if domaine in url:
                rapport.avertissement(f"Outil '{outil['name']}' ({url}) : {avertissement}")

        if not outil.get("parameters", {}).get("toolDescription"):
            rapport.avertissement(f"Outil '{outil['name']}' n'a pas de toolDescription — l'agent risque de mal savoir quand l'utiliser.")
        else:
            rapport.ok(f"Outil '{outil['name']}' documenté pour l'agent.")

        if ping:
            base = url.split("?")[0]
            try:
                req = urllib.request.Request(base, method="HEAD")
                urllib.request.urlopen(req, timeout=5)
                rapport.ok(f"URL de '{outil['name']}' joignable : {base}")
            except Exception as e:
                rapport.erreur(f"URL de '{outil['name']}' INJOIGNABLE ({base}) : {e}")


def verifier_connexions(workflow: dict, rapport: RapportVerification):
    connexions = workflow.get("connections", {})
    triggers = trouver_noeuds(workflow, "n8n-nodes-base.formTrigger")
    agents = trouver_noeuds(workflow, "@n8n/n8n-nodes-langchain.agent")
    sorties = trouver_noeuds(workflow, "n8n-nodes-base.form")

    if triggers and agents:
        nom_trigger = triggers[0]["name"]
        nom_agent = agents[0]["name"]
        cibles = [c["node"] for c in connexions.get(nom_trigger, {}).get("main", [[]])[0]]
        if nom_agent in cibles:
            rapport.ok(f"'{nom_trigger}' est bien connecté à '{nom_agent}'.")
        else:
            rapport.erreur(f"'{nom_trigger}' n'est PAS connecté à '{nom_agent}' — le formulaire n'alimentera pas l'agent.")

    if agents and sorties:
        nom_agent = agents[0]["name"]
        nom_sortie = sorties[0]["name"]
        cibles = [c["node"] for c in connexions.get(nom_agent, {}).get("main", [[]])[0]]
        if nom_sortie in cibles:
            rapport.ok(f"'{nom_agent}' est bien connecté à '{nom_sortie}'.")
        else:
            rapport.erreur(f"'{nom_agent}' n'est PAS connecté à '{nom_sortie}' — le résultat ne sera jamais affiché.")

    # Modèle et outils rattachés à l'agent
    for nom, type_lien in [("ai_languageModel", "modèle"), ("ai_tool", "outil")]:
        rattaches = [
            src for src, liens in connexions.items()
            if any(
                edge.get("type") == nom and edge.get("node") in [a["name"] for a in agents]
                for groupe in liens.get(nom, [])
                for edge in groupe
            )
        ]
        if rattaches:
            rapport.ok(f"{len(rattaches)} nœud(s) {type_lien} rattaché(s) à l'agent : {rattaches}")
        else:
            rapport.avertissement(f"Aucun nœud {type_lien} explicitement rattaché détecté (vérifier manuellement).")


def verifier(chemin: str, ping_urls: bool = False) -> RapportVerification:
    workflow = charger_workflow(chemin)
    rapport = RapportVerification()

    verifier_structure(workflow, rapport)
    verifier_formulaire_entree(workflow, rapport)
    verifier_prompt_systeme(workflow, rapport)
    verifier_urls_outils(workflow, rapport, ping_urls)
    verifier_connexions(workflow, rapport)

    return rapport


def afficher_rapport(rapport: RapportVerification):
    icones = {"ok": "✅", "avertissement": "⚠️ ", "erreur": "❌"}
    for r in rapport.resultats:
        print(f"{icones[r.niveau]} {r.message}")

    print("\n--- Résumé ---")
    resume = rapport.resume()
    print(f"OK : {resume['ok']} | Avertissements : {resume['avertissements']} | Erreurs : {resume['erreurs']}")
    if rapport.a_des_erreurs:
        print("\n❌ Le workflow contient des erreurs structurelles à corriger avant mise en production.")
    else:
        print("\n✅ Aucune erreur structurelle. Vérifiez les avertissements avant mise en production.")


def main():
    parser = argparse.ArgumentParser(description="Vérificateur du workflow n8n credit_agent")
    parser.add_argument("chemin_workflow")
    parser.add_argument("--ping-urls", action="store_true", help="Teste aussi la joignabilité réseau des URLs d'outils")
    args = parser.parse_args()

    rapport = verifier(args.chemin_workflow, ping_urls=args.ping_urls)
    afficher_rapport(rapport)
    sys.exit(1 if rapport.a_des_erreurs else 0)


if __name__ == "__main__":
    main()
