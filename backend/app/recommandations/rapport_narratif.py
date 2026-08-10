"""
Rapport narratif complet Mistral IA pour le flux /diagnostic/adresse/rapport.

Règles strictes (addendum §4) :
  1. Le prompt Mistral ne reçoit QUE RisqueReport.model_dump() — jamais les
     données Géorisques brutes.
  2. N'invente AUCUNE date, AUCUN chiffre, AUCUN fait absent du JSON fourni.
  3. Génération en un seul appel Mistral (RapportNarratif structuré).
  4. Toute erreur ou timeout Mistral → retourne (None, cause) (fail-soft, la
     cause permet à l'API de renvoyer une erreur 502/503 explicite).
  5. Ce module est synchrone (SDK mistralai) et doit être appelé via
     asyncio.to_thread() depuis le handler FastAPI async.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.risque_report import RisqueReport

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schémas du rapport narratif
# ---------------------------------------------------------------------------

class SectionRapport(BaseModel):
    titre: str
    contenu: str  # 2-4 phrases factuelles, basées uniquement sur le JSON
    aleas_associes: list[str] = []  # ex: ["inondation", "rga"]


class RapportNarratif(BaseModel):
    introduction: str  # 2-3 phrases de cadrage
    sections: list[SectionRapport]
    synthese_finale: str  # hiérarchisation des risques
    obligations_reglementaires: list[str] | None = None
    genere_par: str = "mistral-large-latest"
    metadata: dict[str, Any] = {}
    avertissement_ia: str = (
        "Ce rapport est généré automatiquement par IA à partir des données publiques "
        "Géorisques normalisées. Il ne remplace pas l'ERRIAL ni l'avis d'un expert."
    )


# ---------------------------------------------------------------------------
# Prompt Système
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_RAPPORT = """
Tu es Typhoon, l'expert IA en résilience climatique du bâtiment en France. Tu rédiges, pour un
propriétaire, un rapport de diagnostic PERSONNALISÉ, priorisé et orienté action à partir d'un
JSON de diagnostic normalisé (sources : Géorisques BRGM/MTE, BDNB, recommandations Mistral).

OBJECTIF : le rapport doit être tellement précis sur CE bien qu'il ne pourrait pas être généré
pour n'importe quel autre bâtiment de la même rue. Chaque phrase doit s'appuyer sur un fait du
JSON : les caractéristiques du bâti, le niveau de chaque aléa, l'historique CatNat, le zonage.

TON — EXPERT DE TERRAIN, PAS DOCUMENT ADMINISTRATIF :
- Direct, concret, actionnable. Phrases courtes. Tu vouvoies le propriétaire.
- Tu peux dire « nous » (Typhoon) pour présenter une analyse, jamais « l'IA » ni « le système ».
- Interdits : style passif bureaucratique, jargon juridique gratuit, généralités creuses.
  Chaque phrase apporte un fait, une conséquence concrète pour CE bien, ou une action.

DONNÉES REÇUES (JSON) :
- « batiment » : année de construction, matériaux des murs et de la toiture, nombre de niveaux,
  hauteur, surface d'emprise au sol, usage, aléa argile BDNB. POSSIBLEMENT PARTIEL : certains
  champs peuvent manquer. N'invente JAMAIS une caractéristique absente.
- « aleas_presents » : un objet par aléa avec code, libellé, niveau
  (tres_faible | faible | modere | eleve | critique), zonage, nombre d'arrêtés CatNat et
  exemples d'arrêtés (libellé, dates).
- « recommandations_disponibles » : résumé et actions déjà identifiées (facultatif).
- « adresse », « code_insee », « date_rapport ».

RÈGLES DE FIABILITÉ FACTUELLE (NON NÉGOCIABLES) :
- N'énonce JAMAIS un chiffre, une date, une durée ou une statistique qui n'est pas
  explicitement présent dans les données fournies en entrée. En cas de doute, omets le
  détail plutôt que de l'estimer ou de l'inventer.
- N'ajoute jamais de détail narratif non vérifiable (ex. temps de submersion, vitesse d'un
  phénomène) sauf s'il provient explicitement de la source fournie dans le JSON.
- Le score/niveau attribué à un même aléa doit être calculé UNE SEULE FOIS et réutilisé
  identique dans toutes les sections du rapport (résumé, détail, synthèse) — jamais
  recalculé indépendamment section par section, jamais contradictoire.
- Chaque donnée chiffrée (nombre d'installations, nombre d'arrêtés CatNat, …) doit être
  accompagnée en interne d'une référence à sa source exacte et vérifiable dans le JSON —
  jamais d'estimation. N'affiche que ce que le JSON fournit.

RÈGLES STRICTES :

1. LE BIEN D'ABORD — SECTION « LE BIEN EN UN COUP D'ŒIL » :
   Ouvre le rapport par cette section. Cite les données bâti disponibles : année de
   construction, matériaux des murs et de la toiture, nombre de niveaux, hauteur, surface,
   usage, aléa argile BDNB. Traduis-les immédiatement en conséquences pour la vulnérabilité :
   « Bâti de 1930 en meulière, toiture ardoise → structure ancienne sans normes parasismiques,
   murs sensibles aux fissures de retrait-gonflement des argiles. »
   Si une donnée manque, écris-le explicitement (« année de construction non disponible ») et
   transforme-le en action de vérification (diagnostic structurel, inspection toiture…).
   Termine cette section par la hiérarchie des risques de ce bien (voir règle 2).

2. PRIORISATION — ORDRE D'URGENCE EXPLICITE :
   Tu DOIS classer les aléas du plus urgent au moins urgent pour CE bien, et le rendre
   explicite dans « synthese_finale » : « Le plus urgent pour ce bien : X, puis Y, puis Z. »
   Règle de priorité (transparente, à appliquer dans cet ordre) :
     a) gravité du niveau (critique > eleve > modere > faible > tres_faible) ;
     b) aggravant bâtimentaire : un bâtiment ancien ou en matériaux vulnérables rend un aléa
        plus urgent que pour un bâtiment récent aux normes (croise avec « batiment ») ;
     c) historique : plus d'arrêtés CatNat sur un aléa = risque déjà matérialisé.
   Un aléa critique ne se traite JAMAIS comme un aléa modéré : les sections les plus graves
   doivent être plus longues, plus concrètes et contenir les recommandations les plus urgentes.
   SCORES — si le JSON contient un score chiffré (ex. « score » 0-100), cite-le tel quel.
   Sinon, N'INVENTE AUCUN score numérique : utilise uniquement les niveaux qualitatifs et le
   classement ci-dessus. Une estimation de coût de travaux n'est autorisée QUE si le JSON la
   fournit ; sinon écris « à chiffrer par un professionnel ».

3. ALÉA → ZONES DU BÂTIMENT EXPOSÉES :
   Pour chaque aléa, nomme les parties du bien les plus exposées en croisant la nature de
   l'aléa ET les données du bâti :
   - inondation / remontée de nappe → sous-sol, fondations, réseaux, garage ;
   - retrait-gonflement des argiles → fondations, murs porteurs (aggrave si bâti ancien,
     si aléa argile BDNB « moyen » ou « fort ») ;
   - séisme → structure : murs porteurs, chaînages, toiture (aggrave si bâti antérieur aux
     normes parasismiques) ;
   - canicule → toiture, combles, façade sud, menuiseries ;
   - mouvement de terrain / cavités → fondations, structure.
   Présente cela comme un constat d'expert : « les zones les plus exposées sont… », jamais
   comme une mesure. Cite systématiquement l'année de construction ou les matériaux quand ils
   renforcent l'exposition.

4. RECOMMANDATIONS — DEUX BLOCS SÉPARÉS, PAS UN MÊME FOURRE-TOUT :
   a) « obligations_reglementaires » : courtes, factuelles et LIÉES À CE BIEN. Chaque
      obligation doit citer l'élément du JSON qui la déclenche (ex. « zone sismique 4 »,
      « zonage PPR inondation », « 3 arrêtés CatNat sécheresse »). Interdiction des phrases
      génériques valables pour toute la France : « respecter les normes parasismiques » seul
      est interdit — précise la zone et la conséquence pour ce bien. Maximum 5 éléments.
   b) Dans les sections aléas : des recommandations de travaux ACTIONNABLES et PRIORISÉES.
      Forme : action concrète (verbe d'action) + partie du bâtiment + pourquoi elle réduit
      le risque + coût (seulement si fourni dans le JSON, sinon « à chiffrer par un
      professionnel »). Exemple : « Contrôler l'étanchéité des canalisations et des fosses
      septiques : une fuite sous dalle fragilise les fondations en zone de retrait-gonflement.
      À chiffrer par un professionnel. »
      Exploite « recommandations_disponibles » s'il est fourni, en le rendant concret et
      priorisé. Commence toujours par le ou les travaux du risque le plus urgent (règle 2).

5. PERSPECTIVE CLIMATIQUE :
   Ajoute un regard prospectif : tendance d'évolution des aléas (épisodes extrêmes plus
   fréquents, sécheresses, canicules) et son impact sur ce bâti. Tu peux énoncer des
   tendances climatiques générales, mais JAMAIS de chiffre de projection absent du JSON.
   Si les données de projection 2050 manquent, précise que Typhoon peut projeter l'exposition
   du bien à l'horizon 2050.

6. AUCUNE INVENTION :
   N'invente ni date, ni chiffre, ni matériau, ni aléa, ni étude, ni obligation absents du
   JSON fourni. Un fait manquant se signale et se transforme en action de vérification.
   Le rapport doit rester factuel : chaque affirmation est traçable dans le JSON.

7. STRUCTURE ET FORMAT DE SORTIE :
   - Une section par aléa présent (present=true) ou avec historique CatNat.
   - Réponds UNIQUEMENT en JSON valide respectant le schéma ci-dessous, sans texte avant ni
     après.

Format JSON attendu :
{
  "introduction": "...",
  "sections": [
    {
      "titre": "...",
      "contenu": "...",
      "aleas_associes": ["code_alea"]
    }
  ],
  "synthese_finale": "...",
  "obligations_reglementaires": ["..."]
}
""".strip()


def _build_rapport_prompt(report: RisqueReport) -> str:
    """Filtre RisqueReport.model_dump() pour ne transmettre que les faits utiles au rapport."""
    data = report.model_dump()
    aleas_propres = []
    for a in data.get("aleas", []):
        if a.get("present") is True or a.get("catnat_historique"):
            aleas_propres.append({
                "code": a.get("code"),
                "libelle": a.get("libelle"),
                "niveau": a.get("niveau"),
                "zonage": a.get("zonage"),
                "nombre_catnat": len(a.get("catnat_historique") or []),
                "catnat_exemples": [
                    {
                        "libelle": c.get("libelle_risque_jo"),
                        "date_debut": c.get("date_debut_evt"),
                        "date_fin": c.get("date_fin_evt"),
                    }
                    for c in (a.get("catnat_historique") or [])[:5]
                ],
            })

    # Données bâtimentaires BDNB (partielles : seuls les champs renseignés sont
    # transmis, pour que le rapport soit PERSONNALISÉ au bâti sans inventer).
    batiment_infos = {}
    bdnb = data.get("bdnb") or {}
    batiment = bdnb.get("batiment") if isinstance(bdnb, dict) else None
    if isinstance(batiment, dict):
        for cle in (
            "annee_construction", "mat_mur_txt", "mat_toit_txt", "nb_niveau",
            "nb_log", "hauteur_mean", "surface_emprise_sol",
            "usage_niveau_1_txt", "alea_argile",
        ):
            valeur = batiment.get(cle)
            if valeur is not None:
                batiment_infos[cle] = valeur

    # Recommandations déjà identifiées (Mistral) — à transformer en actions concrètes.
    recommandations_dispo = {}
    reco = data.get("recommandations") or {}
    if isinstance(reco, dict):
        for cle in ("resume", "actions_prioritaires", "points_vigilance"):
            if reco.get(cle):
                recommandations_dispo[cle] = reco[cle]

    prompt_data = {
        "adresse": data.get("adresse_normalisee"),
        "code_insee": data.get("code_insee"),
        "date_rapport": str(data.get("date_generation")),
        "aleas_presents": aleas_propres,
        "batiment": batiment_infos,
        "recommandations_disponibles": recommandations_dispo,
    }
    return json.dumps(prompt_data, ensure_ascii=False, indent=2)


def _cause_mistral(exc: Exception) -> str:
    """Cause courte et sûre d'un échec Mistral (jamais de secret)."""
    msg = str(exc).strip()[:200]
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


def _appeler_mistral_narratif_sync(report: RisqueReport) -> tuple[RapportNarratif | None, str | None]:
    """Retourne (rapport, cause) — cause est un code de raison machine court
    quand le rapport n'a pas pu être généré (None si succès). Codes possibles :
    `api_key_manquante`, `import_echec`, `mistral_erreur`, `reponse_malformee`,
    ou la description courte d'une erreur Mistral."""
    if not settings.mistral_api_key:
        logger.debug("MISTRAL_API_KEY absent — rapport narratif indisponible")
        return None, "api_key_manquante"

    try:
        from app.recommandations.mistral_client import chat_json
    except ImportError as exc:
        logger.warning("mistralai non disponible — rapport narratif ignoré : %s", exc)
        return None, "import_echec"

    user_prompt = _build_rapport_prompt(report)
    t0 = time.perf_counter()

    try:
        reponse = chat_json(
            system_prompt=_SYSTEM_PROMPT_RAPPORT,
            user_prompt=user_prompt,
            max_retries=2,
            # Le rapport (intro + sections + synthèse + obligations) dépasse
            # facilement les 1000 tokens par défaut : la réponse était tronquée
            # en plein JSON ("Unterminated string", erreur 502).
            max_tokens=4000,
        )
    except Exception as exc:
        logger.warning("Mistral échec rapport narratif pour %r : %s", report.adresse_normalisee, exc)
        return None, f"mistral_erreur: {_cause_mistral(exc)}"

    latence_ms = round((time.perf_counter() - t0) * 1000)

    try:
        sections = [
            SectionRapport(
                titre=s.get("titre", "Analyse"),
                contenu=s.get("contenu", ""),
                aleas_associes=s.get("aleas_associes", []),
            )
            for s in reponse.get("sections", [])
        ]
        return (
            RapportNarratif(
                introduction=reponse.get("introduction", ""),
                sections=sections,
                synthese_finale=reponse.get("synthese_finale", ""),
                obligations_reglementaires=reponse.get("obligations_reglementaires"),
                genere_par="mistral-large-latest",
                metadata={"latence_ms": latence_ms},
            ),
            None,
        )
    except Exception as exc:
        logger.warning("Réponse Mistral rapport narratif malformée : %s", exc)
        return None, "reponse_malformee"


async def generer_rapport_narratif(report: RisqueReport) -> tuple[RapportNarratif | None, str | None]:
    """Point d'entrée async pour le rapport narratif : (rapport, cause)."""
    try:
        return await asyncio.to_thread(_appeler_mistral_narratif_sync, report)
    except Exception as exc:
        logger.warning("Erreur inattendue rapport narratif : %s", exc)
        return None, f"erreur_inattendue: {_cause_mistral(exc)}"
