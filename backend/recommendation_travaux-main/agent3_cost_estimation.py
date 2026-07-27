"""
Agent 3 (optionnel) - Estimation de couts et d'aides NON sourcees.

A la difference de l'agent 2 (RAG sur le referentiel), ce script n'utilise aucune source
documentaire: il s'appuie sur la connaissance generale du modele pour proposer des ordres de
grandeur de cout et des pistes d'aides. Ces valeurs sont explicitement marquees comme
"estimation_llm_non_sourcee", distinctes des estimations sourcees (type "estimation_cout")
produites par l'agent 2 - il ne faut jamais les fusionner silencieusement.

Il ne remplit QUE les champs cout_estime / aide deja a null dans le resultat de l'agent 2.
Il ne touche jamais aux recommandations qui ont deja une estimation sourcee.

Usage:
    python agent3_cost_estimation.py --input data/resultat.json --output data/resultat_enrichi.json
"""
import argparse
import json

from utils.mistral_client import chat_json


SYSTEM_PROMPT = """Tu proposes des ordres de grandeur de cout de travaux de renovation/prevention
pour des maisons individuelles en France, a partir de tes connaissances generales du marche du
BTP francais actuel. Tu n'as PAS acces a une source documentaire precise pour cette tache: tes
estimations sont donc explicitement non sourcees et indicatives.

REGLES IMPERATIVES
- Donne une fourchette (montant_min, montant_max) en euros TTC pour la mesure decrite, avec les
  hypotheses de perimetre que tu utilises (surface, materiaux, complexite d'acces...).
- Si tu ne peux vraiment pas produire une fourchette raisonnable (mesure trop vague ou trop
  variable selon le contexte), renvoie cout_estime a null plutot que d'inventer un chiffre.
- Pour les aides: ne dis jamais qu'un menage est eligible. Liste seulement, si pertinent, les
  noms de dispositifs generaux existants en France pour ce type de travaux (ex: MaPrimeRenov,
  eco-pret a taux zero), statut toujours "potential_eligibility_only", sans conditions precises
  que tu ne connais pas avec certitude.
- Reste honnete sur l'incertitude: n'affiche jamais une fausse precision (ex: "3214,50 EUR").
  Prefere une fourchette large a un chiffre precis non justifie.

Reponds uniquement en JSON:
{
  "cout_estime": {
    "montant_min": 0, "montant_max": 0, "devise": "EUR", "unite": "forfait",
    "hypotheses": "texte des hypotheses de perimetre retenues",
    "origine": "estimation_llm_non_sourcee",
    "fiabilite": "indicative - ordre de grandeur general, non issu d'une source documentaire"
  },
  "aide": {
    "dispositifs_generaux": ["..."],
    "statut": "potential_eligibility_only",
    "origine": "estimation_llm_non_sourcee"
  }
}
Mets cout_estime ou aide a null (pas juste des champs vides) si non estimable/non pertinent."""


def build_user_prompt(mesure: str, zone: str, risques: list, bien: dict) -> str:
    return f"""MESURE DE TRAVAUX: {mesure}
ZONE DE LA MAISON: {zone}
RISQUES CONCERNES: {', '.join(risques)}
INFOS SUR LE BIEN: {json.dumps(bien, ensure_ascii=False)}

Propose une estimation de cout et, si pertinent, des pistes d'aides generales, selon les regles
du systeme."""


def enrich_result(result: dict) -> dict:
    bien = result.get("bien", {})
    for zone_info in result.get("zones", []):
        zone = zone_info.get("zone")
        risques = zone_info.get("risques", [])
        for reco in zone_info.get("recommandations", []):
            needs_cost = reco.get("cout_estime") is None
            needs_aide = reco.get("aide") is None
            if not needs_cost and not needs_aide:
                continue

            print(f"[Agent3] {zone} -> {reco.get('mesure', '')[:60]}...")
            try:
                enrich = chat_json(
                    SYSTEM_PROMPT,
                    build_user_prompt(reco.get("mesure", ""), zone, risques, bien),
                )
            except Exception as e:
                print(f"  -> erreur Mistral, recommandation non enrichie: {e}")
                continue

            if needs_cost and enrich.get("cout_estime"):
                reco["cout_estime"] = enrich["cout_estime"]
            if needs_aide and enrich.get("aide"):
                reco["aide"] = enrich["aide"]

    return result


def main():
    parser = argparse.ArgumentParser(description="Agent 3 - estimation LLM non sourcee")
    parser.add_argument("--input", required=True, help="JSON de sortie de agent2_rag.py")
    parser.add_argument("--output", default="data/resultat_enrichi.json")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        result = json.load(f)

    enriched = enrich_result(result)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"\nResultat enrichi -> {args.output}")


if __name__ == "__main__":
    main()
