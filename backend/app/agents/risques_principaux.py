"""
risques_principaux — synthèse LLM des risques principaux du bien.

Alimente le panneau « Comprendre les risques » du frontend : le classement
des 3 risques principaux est calculé de façon DÉTERMINISTE par le moteur
(`risk_model.compute_alea_risks`, scores F×V traçables), puis un LLM
(Mistral) croise ces scores avec TOUTES les données disponibles (année de
construction, matériaux, climat actuel et 2050, géorisques, altitude, scores
par zone du bâtiment) pour produire pour chaque risque :
  - une « explication » en langage clair qui relie les données entre elles
  - les « facteurs_aggravants » (donnée → conséquence)
  - la « zone_la_plus_exposee » du bâtiment

Fail-soft (convention du projet) : sans clé Mistral ou en cas d'échec, on
renvoie le classement déterministe (score + justification) pour ne jamais
casser le diagnostic. Les scores/niveaux viennent TOUJOURS du moteur : le
LLM ne peut ni les modifier ni en inventer.
"""

from __future__ import annotations

from typing import Any

from app.agents.interpretation_agent import (
    _build_house_context,
    _build_risk_context,
    _format_house_context,
)
from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.mistral_client import chat_json
from app.scoring.risk_model import compute_alea_risks

logger = get_logger(__name__)

TOP_N = 3
SEUIL_SCORE = 20  # en-deçà de 20/100, pas de risque notable (bande « faible »)

# Zone la plus exposée par défaut (repli déterministe si le LLM est absent ou
# ne renvoie pas de zone valide). Code aléa → zone du contrat digital_twin.
_ZONE_PAR_ALEA: dict[str, str] = {
    "rga": "fondations",
    "secheresse": "fondations",
    "inondation": "sous_sol",
    "mouvement_terrain": "fondations",
    "sismicite": "fondations",
    "radon": "sous_sol",
    "canicule": "toiture",
    "feu_foret": "toiture",
}

_ZONES_VALIDES = {
    "fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest",
    "toiture", "sous_sol",
}

SYSTEM_PROMPT = """Tu es un expert en diagnostic de résilience climatique et vulnérabilité du bâti
pour l'immobilier en France. Tu travailles pour Typhoon, un service qui aide les
propriétaires à comprendre les risques auxquels leur maison est exposée.

On te fournit :
- Les 3 risques principaux du bien, CLASSÉS par le moteur déterministe (score 0-100,
  niveau, justification qui cite les données sources). Ces scores sont calculés en
  croisant l'aléa (F) avec la vulnérabilité du bâtiment (V) — tu dois les respecter.
- Le contexte complet de la maison et de son environnement : année de construction,
  matériaux (murs, toiture), étages, climat actuel et projeté 2050, aléas recensés
  sur la commune, historique CATNAT, altitude.
- Les scores de risque par zone du bâtiment (fondations, murs, toiture, sous-sol)
  pour la période courante et la projection 2050.

RÈGLES IMPÉRATIVES :
1. Pour CHAQUE risque, produis une « explication » de 1 à 2 phrases qui CROISE
   VRAIMENT les données : aléa × caractéristiques du bâtiment × environnement.
   Exemple : « Aléa dominant sur la commune, amplifié par une construction
   antérieure à 1949 et des fondations peu profondes. »
   Exemple : « 9 arrêtés CATNAT recensés sur la commune ; sous-sol identifié comme
   zone la plus exposée du bien. »
   Ne te contente jamais de redire le risque.
2. « facteurs_aggravants » : 2 à 3 éléments courts (max 1 ligne chacun) qui
   RENFORCENT le risque, au format « donnée → conséquence ».
   Exemple : « Construction antérieure à 1949 → normes parasismiques absentes ».
   N'invente AUCUNE caractéristique du bâtiment : si l'année ou les matériaux sont
   absents du contexte, base-toi uniquement sur les données fournies.
3. « zone_la_plus_exposee » : la zone du bâtiment la plus exposée à CE risque,
   parmi exactement : fondations, murs_nord, murs_sud, murs_est, murs_ouest,
   toiture, sous_sol. Renvoie null si aucune zone ne se distingue.
4. Ne MODIFIE JAMAIS les champs « code », « libelle », « score », « niveau »
   fournis : tu dois les recopier EXACTEMENT dans ta réponse.
5. Sois concis et factuel. Présente les faits comme des constats documentés, sans
   jamais mentionner qu'il s'agit d'une analyse LLM ou d'un moteur.
6. Réponds UNIQUEMENT en JSON valide, sans texte autour.

Format de réponse attendu :
{
  "risques": [
    {
      "code": "rga",
      "libelle": "Retrait-gonflement des argiles",
      "score": 84,
      "niveau": "eleve",
      "explication": "Une ou deux phrases croisant les données.",
      "facteurs_aggravants": ["donnée → conséquence", "donnée → conséquence"],
      "zone_la_plus_exposee": "fondations"
    },
    {
      "code": "inondation",
      "libelle": "Inondation / remontée de nappe",
      "score": 78,
      "niveau": "eleve",
      "explication": "...",
      "facteurs_aggravants": ["..."],
      "zone_la_plus_exposee": "sous_sol"
    },
    {
      "code": "secheresse",
      "libelle": "Sécheresse",
      "score": 61,
      "niveau": "modere",
      "explication": "...",
      "facteurs_aggravants": ["..."],
      "zone_la_plus_exposee": "fondations"
    }
  ]
}
"""


def _explication_repli(r: dict[str, Any]) -> str:
    """Première phrase de la justification du moteur, sans le marqueur « • ».

    Repli quand le LLM est absent ou n'a rien renvoyé : le panneau affiche
    quand même un texte factuel pour chaque risque.
    """
    texte = (r.get("justification") or "").replace("• ", "").strip()
    if not texte:
        return ""
    idx = texte.find(". ")
    if idx != -1:
        texte = texte[: idx + 1]
    return texte if texte.endswith(".") else texte + "."


def _premier_risques(building_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Top-N déterministe : scores du moteur + zone la plus exposée (repli)."""
    risques = compute_alea_risks(building_data)
    top = [r for r in risques if r["score"] >= SEUIL_SCORE][:TOP_N]
    for r in top:
        r["zone_la_plus_exposee"] = _ZONE_PAR_ALEA.get(r["code"])
        r.setdefault("explication", "")
        r.setdefault("facteurs_aggravants", [])
    return top


def _prompt_user(top: list[dict[str, Any]], building_data: dict[str, Any], risk_scores: dict[str, Any]) -> str:
    """Construit le prompt utilisateur : top-3 + contexte maison + zones."""
    house_context = _build_house_context(building_data)
    risk_context = _build_risk_context(risk_scores)
    house_text = _format_house_context(house_context)

    lignes_risques = []
    for i, r in enumerate(top, start=1):
        lignes_risques.append(
            f"{i}. {r['libelle']} (code {r['code']}) — score {r['score']}/100, "
            f"niveau « {r['niveau']} »\n   Justification : {r['justification']}"
        )

    zones = risk_context.get("zones", {})
    lignes_zones = []
    for zone_name, z in zones.items():
        lignes_zones.append(
            f"  - {zone_name} : {z.get('risque')}/100 ({z.get('niveau')}) — "
            f"aléa principal : {z.get('alea_principal')}"
        )

    return (
        "RISQUES PRINCIPAUX CLASSÉS PAR LE MOTEUR :\n"
        + "\n".join(lignes_risques)
        + "\n\nCONTEXTE COMPLET DE LA MAISON ET DE SON ENVIRONNEMENT :\n"
        + house_text
        + "\n\nSCORES PAR ZONE DU BÂTIMENT (période courante) :\n"
        + ("\n".join(lignes_zones) if lignes_zones else "  (aucune zone calculée)")
        + "\n\nPour chaque risque, produis l'explication, les facteurs aggravants et "
        "la zone la plus exposée en croisant ces données, sans modifier score et niveau."
    )


def _fusionner_reponse_llm(top: list[dict[str, Any]], payload: Any) -> list[dict[str, Any]]:
    """Fusionne la réponse Mistral avec les faits du moteur.

    Les champs code/libelle/score/niveau/justification restent CEUX du moteur
    (le LLM ne peut pas les modifier) ; seuls explication, facteurs_aggravants
    et zone_la_plus_exposee sont repris de la réponse, validés par code.
    """
    reponses = {}
    if isinstance(payload, dict) and isinstance(payload.get("risques"), list):
        for item in payload["risques"]:
            if isinstance(item, dict) and isinstance(item.get("code"), str):
                reponses[item["code"]] = item

    for r in top:
        rep = reponses.get(r["code"], {})
        # L'explication de repli (justification du moteur) est appliquée par
        # le passe final de generer_risques_principaux si rien n'est fourni.
        explication = rep.get("explication")
        if isinstance(explication, str) and explication.strip():
            r["explication"] = explication.strip()

        facteurs = rep.get("facteurs_aggravants")
        if isinstance(facteurs, list):
            r["facteurs_aggravants"] = [
                str(f).strip() for f in facteurs if isinstance(f, str) and f.strip()
            ][:4]

        zone = rep.get("zone_la_plus_exposee")
        if zone in _ZONES_VALIDES:
            r["zone_la_plus_exposee"] = zone
    return top


def generer_risques_principaux(
    building_data: dict[str, Any],
    risk_scores: dict[str, Any],
) -> dict[str, Any]:
    """Point d'entrée : top-3 des risques principaux, narré par le LLM.

    Contrat retourné (consommé par le frontend, bloc `risques_principaux`) :
      {
        "risques": [
          {code, libelle, score, niveau, explication, facteurs_aggravants,
           zone_la_plus_exposee}, ...
        ],
        "source": "moteur_deterministe" | "moteur_deterministe_et_llm"
      }

    Toujours fail-soft : une absence de clé ou un échec Mistral renvoie le
    classement déterministe, jamais une erreur.
    """
    top = _premier_risques(building_data)
    if not top:
        return {"risques": [], "source": "moteur_deterministe"}

    source = "moteur_deterministe"
    if settings.mistral_api_key:
        try:
            user_prompt = _prompt_user(top, building_data, risk_scores)
            payload = chat_json(SYSTEM_PROMPT, user_prompt)
            top = _fusionner_reponse_llm(top, payload)
            source = "moteur_deterministe_et_llm"
        except Exception as exc:
            logger.warning("  [risques_principaux] échec Mistral, repli déterministe : %s", exc)
    else:
        logger.debug("  [risques_principaux] MISTRAL_API_KEY absente — classement déterministe seul")

    # Nettoyage final : explication de repli si le LLM n'a rien fourni, et le
    # contrat frontend ne doit pas exposer les champs internes du moteur.
    for r in top:
        if not r.get("explication"):
            r["explication"] = _explication_repli(r)
        r.pop("_f_score", None)
        r.pop("_v_score", None)

    return {"risques": top, "source": source}
