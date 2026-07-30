"""bank_agent — noeud LangGraph pour la décision bancaire.

Portage complet du module `backend/agent_graph/nodes/bank_decision.py`
(projet actuel) vers la nouvelle architecture `backend/app/`.

Structure : 7 sections (calculs 100% déterministes)
1. 📊 Score de risque du bien
2. ⚠️ Principaux risques identifiés
3. 💰 Valeur ajustée du bien
4. 🛡️ Garanties d'assurance recommandées
5. 🏗️ Recommandations de prévention
6. 📈 Projection de l'évolution du risque
7. 📄 Rapport d'analyse synthétique

Aucun appel LLM : tous les calculs sont déterministes à partir
  des données réelles (DVF, Géorisques, BAN, ADEME, MeilleurTaux).
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.state import TyphoonState

logger = logging.getLogger(__name__)

# ── Import conditionnel des outils bancaires ──────────────────────────────────
try:
    from tools.bank_tools import (
        get_property_market_value,
        get_current_bank_rates,
        calculate_risk_premium,
        calculate_data_confidence,
        evaluate_hard_stops,
    )
    HAS_BANK_TOOLS = True
    logger.info("Bank tools chargés avec succès")
except ImportError as e:
    HAS_BANK_TOOLS = False
    logger.warning("Bank tools non disponibles: %s", e)

# ── Import des taux de marché (indépendant) ───────────────────────────────────
try:
    from services.bank_rates import get_market_rates
    HAS_MARKET_RATES = True
except ImportError:
    HAS_MARKET_RATES = False
    logger.warning("get_market_rates non disponible")




# ── Helpers : mapping score → niveau ──────────────────────────────────────────

def _niveau_risque(score: int) -> str:
    if score >= 70:
        return "critique"
    if score >= 55:
        return "eleve"
    if score >= 35:
        return "modere"
    return "faible"


def _niveau_risque_bancaire(score: int) -> str:
    if score >= 60:
        return "Élevé"
    if score >= 35:
        return "Modéré"
    return "Faible"





# ── Extraction des risques depuis les données système ──────────────────────────

def _extraire_risques_identifies(state: TyphoonState, score_global: int) -> list[dict]:
    """Extrait les risques identifiés depuis risk_scores.zones et building_data.georisques."""
    risques: list[dict] = []
    risk_scores = state.get("risk_scores", {}) or {}

    # Depuis les zones du scoring (nouvelle architecture)
    zones = risk_scores.get("zones", {}) or {}
    for zone_name, zone_data in zones.items():
        if isinstance(zone_data, dict) and zone_data.get("risque", 0) >= 25:
            risques.append({
                "nom": zone_data.get("alea_principal", zone_name),
                "score": zone_data.get("risque", 0),
                "niveau": zone_data.get("niveau", _niveau_risque(zone_data.get("risque", 0))),
                "zone_impactee": zone_name.capitalize(),
                "description": zone_data.get("justification", "")[:150],
            })

    # Depuis les aléas Géorisques (enrichissement)
    building_data = state.get("building_data", {}) or {}
    georisques = building_data.get("georisques", {}) or {}

    # Extraction des aléas Géorisques
    ALEA_ZONE_MAP = {
        "inondation": ("Inondation / humidité", "Sous-sol"),
        "rga": ("Retrait-gonflement des argiles", "Fondations"),
        "canicule": ("Canicule / stress thermique", "Toiture"),
        "tempete": ("Tempête / vent", "Toiture & Murs"),
    }

    # Vérifier dans les risques communes
    risques_commune = georisques.get("risques_commune", {}) or {}
    risques_data = risques_commune.get("data", []) if isinstance(risques_commune, dict) else []
    if isinstance(risques_data, list):
        for alea_key, (nom, zone) in ALEA_ZONE_MAP.items():
            if alea_key not in [r["nom"].lower() for r in risques]:
                for entry in risques_data:
                    for detail in entry.get("risques_detail", []):
                        if alea_key in (detail.get("libelle_risque_long") or "").lower():
                            score_alea = min(50, 25 + 5)  # estimation conservative
                            if not any(r["nom"] == nom for r in risques):
                                risques.append({
                                    "nom": nom,
                                    "score": score_alea,
                                    "niveau": _niveau_risque(score_alea),
                                    "zone_impactee": zone,
                                    "description": f"Aléa {nom} détecté via Géorisques.",
                                })

    # Trier par score décroissant
    risques.sort(key=lambda r: r["score"], reverse=True)
    return risques[:6]  # max 6 risques


def _extraire_projection(state: TyphoonState, score_global: int) -> dict | None:
    """Extrait ET améliore la projection 2050 pour l'analyse crédit.

    Si la projection du scoring est trop faible (aggravation < 10 pts),
    calcule une projection plus réaliste spécifique à l'analyse de crédit :
    - Multiplicateur proportionnel au score actuel (plus le risque est élevé,
      plus l'aggravation est sévère — effet compound)
    - Pénalité selon l'état du bien (formulaire : fissures, infiltrations,
      mauvais état → plus vulnérable au changement climatique)
    - Scénario RCP 8.5 +4°C France (réaliste pour 2050)
    """
    risk_scores = state.get("risk_scores", {}) or {}
    projection = risk_scores.get("projection_2050", {}) or {}
    zones = risk_scores.get("zones", {}) or {}

    if not projection:
        return None

    score_projete_scoring = projection.get("score_global", score_global)
    aggravation_scoring = score_projete_scoring - score_global

    # Si la projection du scoring est déjà réaliste (≥ +10 pts), l'utiliser
    if aggravation_scoring >= 10:
        return {
            "horizon": "2050",
            "score_actuel": score_global,
            "score_projete": score_projete_scoring,
            "aggravation": aggravation_scoring,
            "scenario": projection.get("scenario_climatique", "CMIP6 RCP 8.5 +4°C France (DRIAS ADAMONT)"),
            "zones_projetees": projection.get("zones", {}),
        }

    # ── Calcul d'une projection crédit réaliste ──────────────────────────────
    # Principe : le changement climatique aggrave tous les aléas,
    # et un bien déjà dégradé est plus vulnérable.

    form = state.get("formulaire", {}) or {}
    building_data = state.get("building_data", {}) or {}

    # Facteur de vulnérabilité du bien (0.0 → 0.4)
    # Basé sur l'état déclaré dans le formulaire
    vuln = 0.0
    if str(form.get("fissures") or "").lower() in ("importantes", "moyennes", "majeures"):
        vuln += 0.15
    if str(form.get("infiltrations") or "").lower() in ("oui", "majeures"):
        vuln += 0.10
    if str(form.get("affaissement") or "").lower() == "oui":
        vuln += 0.15
    if str(form.get("etat_toiture") or "").lower() == "mauvais":
        vuln += 0.10
    if str(form.get("etat_structure") or "").lower() == "mauvais":
        vuln += 0.10
    annee = form.get("annee_construction")
    if isinstance(annee, (int, float)) and annee < 1950:
        vuln += 0.10
    vuln = min(vuln, 0.4)

    # Multiplicateur de base : proportionnel au score actuel
    # score 0 → x1.0, score 50 → x1.25, score 100 → x1.5
    base_mult = 1.0 + (score_global / 200.0)
    # Ajout de la vulnérabilité
    mult = base_mult + vuln
    # Plafonner le multiplicateur à 1.7 max (évite des scores aberrants >100)
    mult = min(mult, 1.7)

    score_projete = min(100, round(score_global * mult))
    aggravation = score_projete - score_global

    # S'assurer qu'il y a au moins +5 pts même pour les biens à faible risque
    if aggravation < 5:
        score_projete = min(100, score_global + 5)
        aggravation = 5

    # Projection par zone : en utilisant les zones du scoring
    zones_projetees = {}
    for z_name, z_data in zones.items():
        if not isinstance(z_data, dict):
            continue
        risque_actuel = z_data.get("risque", 0)
        ratio_aggravation = max(1.05, mult)  # au moins +5%
        risque_projete = min(100, round(risque_actuel * ratio_aggravation))
        # Les zones déjà critiques s'aggravent plus (effet compound)
        if risque_actuel >= 60:
            risque_projete = min(100, round(risque_actuel * (ratio_aggravation + 0.15)))
        elif risque_actuel >= 40:
            risque_projete = min(100, round(risque_actuel * (ratio_aggravation + 0.08)))
        evolution = risque_projete - risque_actuel
        zones_projetees[z_name] = {
            "risque_projete": risque_projete,
            "evolution": f"+{evolution} point(s) (aggravation climatique crédit)",
        }

    # Qualifier le scénario selon le niveau d'aggravation
    if aggravation >= 25:
        scenario = "RCP 8.5 pessimiste — canicules + sécheresses + inondations amplifiées (+4°C France 2050)"
    elif aggravation >= 15:
        scenario = "RCP 8.5 médian — multiplication des aléas climatiques (+3°C France 2050)"
    else:
        scenario = "RCP 6.0 modéré — stress climatique modéré (+2°C France 2050)"

    logger.info(
        "bank_agent -- projection crédit: score=%d → %d (aggravation=%d, mult=%.2f, vuln=%.2f)",
        score_global, score_projete, aggravation, mult, vuln,
    )

    return {
        "horizon": "2050",
        "score_actuel": score_global,
        "score_projete": score_projete,
        "aggravation": aggravation,
        "scenario": scenario,
        "zones_projetees": zones_projetees,
    }



# ── Fallback : génération de recommandations basiques depuis le formulaire ────

def _generer_recommandations_fallback(formulaire: dict[str, Any] | None) -> list[dict]:
    """Génère des recommandations de prévention basiques à partir du formulaire client.

    Utilisé quand le pipeline digital_twin → generate_zone_recommendations
    n'a pas produit de recommandations. Garantit qu'il y a TOUJOURS au moins
    une recommandation dans l'analyse de crédit.
    """
    recos: list[dict] = []
    form = formulaire or {}

    # Sous-sol / inondation
    infiltrations = str(form.get("infiltrations") or "").lower()
    if infiltrations in ("oui", "majeures"):
        recos.append({
            "zone": "sous_sol",
            "travaux": "Diagnostic d'étanchéité du sous-sol + traitement des infiltrations",
            "cout_estime": "2000€",
            "gain_resilience": 55,
            "priorite": 1,
            "aide_financiere": "Anah (50%)",
        })

    # Fondations / structure
    fissures = str(form.get("fissures") or "").lower()
    affaissement = str(form.get("affaissement") or "").lower()
    etat_struct = str(form.get("etat_structure") or "").lower()

    if affaissement == "oui" or fissures in ("importantes", "majeures"):
        recos.append({
            "zone": "fondations",
            "travaux": "Expertise structurelle des fondations + étude géotechnique G12",
            "cout_estime": "3500€",
            "gain_resilience": 60,
            "priorite": 1,
            "aide_financiere": "Fonds CatNat (80%)",
        })
    elif fissures in ("moyennes", "présentes"):
        recos.append({
            "zone": "fondations",
            "travaux": "Surveillance des fissures + drainage périphérique des fondations",
            "cout_estime": "800€",
            "gain_resilience": 35,
            "priorite": 3,
            "aide_financiere": "Anah (50%)",
        })

    # Toiture
    etat_toit = str(form.get("etat_toiture") or "").lower()
    isolation_toit = str(form.get("isolation_toiture") or "").lower()

    if etat_toit == "mauvais":
        recos.append({
            "zone": "toiture",
            "travaux": "Réfection complète de la toiture + renforcement isolation",
            "cout_estime": "8500€",
            "gain_resilience": 50,
            "priorite": 2,
            "aide_financiere": "MaPrimeRénov' (20€/m²)",
        })
    elif isolation_toit == "faible":
        recos.append({
            "zone": "toiture",
            "travaux": "Isolation des combles (laine de bois R≥7, déphasage >10h)",
            "cout_estime": "2500€",
            "gain_resilience": 40,
            "priorite": 4,
            "aide_financiere": "MaPrimeRénov' (20€/m²)",
        })

    # Mur / façade
    isolation_murs = str(form.get("isolation_murs") or "").lower()
    if isolation_murs == "faible" or etat_struct == "mauvais":
        recos.append({
            "zone": "murs_nord",
            "travaux": "Isolation thermique par l'extérieur (ITE) + enduit hydrofuge",
            "cout_estime": "12000€",
            "gain_resilience": 45,
            "priorite": 5,
            "aide_financiere": "MaPrimeRénov' (75€/m²)",
        })

    # Année de construction ancienne → recommandation générique
    annee = form.get("annee_construction")
    if isinstance(annee, (int, float)) and annee < 1980:
        recos.append({
            "zone": "toiture",
            "travaux": "Audit énergétique complet (bâti antérieur à 1980)",
            "cout_estime": "150€",
            "gain_resilience": 25,
            "priorite": 6,
            "aide_financiere": "",
        })

    # Toujours ajouter une recommandation générique si aucune spécifique
    if not recos:
        recos.append({
            "zone": "general",
            "travaux": "Entretien préventif et suivi périodique de l'état du bien",
            "cout_estime": "200€/an",
            "gain_resilience": 15,
            "priorite": 10,
            "aide_financiere": "",
        })

    return recos


def _extraire_prevention(state: TyphoonState) -> list[dict]:
    """Extrait les recommandations de prévention depuis les zones (risk_scores ou digital_twin).

    Si aucune recommandation trouvée, génère un fallback à partir du formulaire client.
    """
    recos: list[dict] = []

    # Essayer depuis risk_scores d'abord
    risk_scores = state.get("risk_scores", {}) or {}
    zones = risk_scores.get("zones", {}) or {}

    # Puis depuis digital_twin (plus riche)
    digital_twin = state.get("digital_twin", {}) or {}
    twin_zones = digital_twin.get("zones", {}) or {}
    zones = {**zones, **twin_zones}  # fusion, twin prend le dessus

    for zone_name, zone_data in zones.items():
        if not isinstance(zone_data, dict):
            continue
        for reco in zone_data.get("recommandations", []):
            if isinstance(reco, dict):
                recos.append({
                    "zone": zone_name,
                    "travaux": reco.get("travaux", ""),
                    "cout_estime": reco.get("cout_estime", ""),
                    "gain_resilience": reco.get("gain_resilience", 0),
                    "priorite": reco.get("priorite", 99),
                    "aide_financiere": reco.get("aide_financiere", ""),
                })

    # Fallback : si aucune recommandation trouvée dans les zones,
    # générer des recommandations basiques depuis le formulaire
    if not recos:
        logger.info(
            "bank_agent -- aucune recommandation dans les zones digital_twin, "
            "génération fallback depuis formulaire"
        )
        recos = _generer_recommandations_fallback(state.get("formulaire"))
        logger.info(
            "bank_agent -- fallback: %d recommandation(s) générée(s)",
            len(recos),
        )

    return recos


def _extraire_garanties_assurance(score_global: int, premium_data: dict) -> list[dict]:
    """Génère les garanties d'assurance recommandées selon le profil."""
    garanties = [
        {
            "type": "Multirisque habitation standard",
            "obligatoire": True,
            "detail": "Couverture incendie, dégâts des eaux, tempête, bris de glace, responsabilité civile"
        },
        {
            "type": "Assurance Catastrophes Naturelles",
            "obligatoire": True,
            "detail": "Couverture réglementaire incluant inondation, séisme, mouvements de terrain"
        },
    ]
    if score_global > 60:
        garanties.append({
            "type": "Garantie multirisque renforcée",
            "obligatoire": True,
            "detail": "Couverture élargie avec franchise réduite pour risques climatiques — inclut RGA et retrait-gonflement"
        })
    if score_global > 30:
        garanties.append({
            "type": "Assurance pertes financières / loyers",
            "obligatoire": False,
            "detail": "Recommandée pour couvrir la perte de valeur locative en cas de sinistre climatique prolongé"
        })
    if "Prêt Vert" in premium_data.get("exigences_banque", []):
        garanties.append({
            "type": "Garantie Prêt Vert",
            "obligatoire": False,
            "detail": "Assurance spécifique pour financement vert avec conditions préférentielles"
        })
    return garanties


def _build_rapport_synthetique(
    score_risque_bancaire: int, niveau: str,
    score_global: int, pts_forts: list, pts_faibles: list,
    nb_risques: int, has_projection: bool, indice_confiance: int
) -> str:
    """Génère le rapport synthétique formaté pour l'analyste bancaire.
    Aucune décision automatique — pure aide à la décision."""
    rapport = []
    rapport.append("RAPPORT D'ANALYSE DE RISQUE CRÉDIT")
    rapport.append("")
    rapport.append(f"1. Synthèse du risque : Le bien présente un niveau de risque {niveau.lower()} "
                   f"(score bancaire {score_risque_bancaire}/100, score climatique {score_global}/100). "
                   f"L'indice de confiance des données est de {indice_confiance}%.")

    if nb_risques > 0:
        rapport.append(f"2. Risques identifiés : {nb_risques} risque(s) principal(aux) identifié(s) "
                       f"nécessitant une attention particulière dans l'instruction du dossier.")

    if pts_forts:
        rapport.append(f"3. Points forts : {'; '.join(pts_forts[:2])}.")
    if pts_faibles:
        rapport.append(f"4. Points de vigilance : {'; '.join(pts_faibles[:2])}.")

    if has_projection:
        rapport.append(f"5. Projection 2050 : L'évolution climatique attendue aggrave le profil de risque. "
                       f"Des travaux de prévention sont recommandés pour limiter l'exposition future.")

    rapport.append(f"6. Recommandation : Analyse humaine requise — ce rapport est un outil d'aide à la "
                   f"décision. L'analyste crédit doit examiner les {nb_risques} points de vigilance identifiés "
                   f"et les éléments financiers avant toute décision d'octroi.")

    return "\n".join(rapport)


def _build_points_forces_faibles(
    form_data: dict, score_global: int,
    confidence_data: dict, market_data: dict,
    hard_stops: list[str]
) -> tuple[list[str], list[str]]:
    pts_forts: list[str] = []
    if market_data.get("source") and "Fallback" not in str(market_data.get("source", "")):
        pts_forts.append(f"Valorisation DVF réelle : {market_data.get('valeur_estimee', 0)}€")
    else:
        pts_forts.append("Valeur de marché estimée")
    if score_global < 30:
        pts_forts.append("Faible exposition climatique")
    if confidence_data.get("indice", 0) >= 80:
        pts_forts.append("Données déclaratives cohérentes (KYC favorable)")

    pts_faibles: list[str] = list(hard_stops) if hard_stops else []
    if form_data.get("fissures") in ("Importantes", "Moyennes"):
        pts_faibles.append(f"Fissures '{form_data['fissures']}' déclarées — risque structurel")
    if form_data.get("infiltrations") in ("Oui", "Majeures"):
        pts_faibles.append("Infiltrations actives déclarées")
    if form_data.get("affaissement") == "Oui":
        pts_faibles.append("Affaissement signalé — étude de sol recommandée")
    if form_data.get("etat_toiture") == "Mauvais":
        pts_faibles.append("Toiture en mauvais état déclaré")
    if form_data.get("etat_structure") == "Mauvais":
        pts_faibles.append("État structurel déclaré mauvais — expertise nécessaire")
    if form_data.get("isolation_toiture") == "faible":
        pts_faibles.append("Isolation toiture insuffisante — passoire thermique potentielle")
    if score_global >= 60:
        pts_faibles.append(f"Score climatique élevé ({score_global}/100)")
    if confidence_data.get("indice", 0) < 70:
        pts_faibles.append(f"Indice de confiance limité ({confidence_data.get('indice', 0)}%)")
    if confidence_data.get("incoherences_detectees"):
        for inc in confidence_data["incoherences_detectees"][:2]:
            pts_faibles.append(f"Incohérence : {inc[:80]}")
    if not pts_faibles:
        pts_faibles.append("Aucun point faible critique détecté — vérifications standard requises")
    return pts_forts[:3], pts_faibles[:4]


def _build_synthese_points_cles(
    score_bancaire: int, niveau: str,
    nb_risques: int, nb_prevention: int, projection: dict | None
) -> list[str]:
    points = [
        f"Score risque bancaire : {score_bancaire}/100 ({niveau})",
    ]
    if nb_risques > 0:
        points.append(f"{nb_risques} risque(s) climatique(s) identifié(s)")
    if nb_prevention > 0:
        points.append(f"{nb_prevention} action(s) de prévention recommandée(s)")
    if projection:
        points.append(
            f"Projection 2050 : aggravation de +{projection['aggravation']} points "
            f"({projection['score_projete']}/100)"
        )
    return points[:5]


def _calc_cout_total(recos: list[dict]) -> str:
    """Calcule le coût total estimé des recommandations de prévention."""
    total = 0
    for r in recos:
        cout = r.get("cout_estime", "0").replace(" ", "").replace("€/an", "").replace("€", "")
        try:
            total += int(cout)
        except ValueError:
            pass
    return f"{total}€"


# ── Fallback technique complet ──────────────────────────────────────────────────

def _build_fallback_bank_decision(
    form_data: dict, score_global: int, score_risque_bancaire: int,
    market_data: dict, rates_data: dict, premium_data: dict,
    confidence_data: dict, hard_stops: list[str],
    risques_identifies: list[dict], garanties_assurance: list[dict],
    prevention_recos: list[dict], projection_data: dict | None,
    session_id: str = "rapport", taux_base: float = 3.7,
) -> dict:
    """Fallback technique complet. Produit les 7 sections de façon déterministe.
    Aucune décision automatique — pure aide à la décision."""

    # Niveau de risque (purement indicatif)
    if hard_stops:
        niveau = "Élevé"
    elif score_risque_bancaire >= 60:
        niveau = "Élevé"
    elif score_risque_bancaire >= 35:
        niveau = "Modéré"
    else:
        niveau = "Faible"

    # Points forts/faibles
    pts_forts, pts_faibles = _build_points_forces_faibles(
        form_data, score_global, confidence_data, market_data, hard_stops
    )

    # Avis (indicatif, pas de décision)
    if niveau == "Élevé":
        avis = (f"Niveau de risque élevé (climatique {score_global}/100, bancaire {score_risque_bancaire}/100). "
                f"{len(pts_faibles)} points de vigilance identifiés. Une expertise humaine approfondie est recommandée "
                f"avant toute décision d'octroi.")
    elif niveau == "Modéré":
        avis = (f"Risque modéré (climatique {score_global}/100, bancaire {score_risque_bancaire}/100). "
                f"Quelques points de vigilance nécessitent une vérification documentaire. "
                f"Ce rapport est un outil d'aide à la décision pour l'analyste crédit.")
    else:
        avis = (f"Profil de risque faible (climatique {score_global}/100, bancaire {score_risque_bancaire}/100). "
                f"Les déclarations sont cohérentes. L'analyste peut examiner le dossier en routine.")

    # Points à vérifier
    pts_a_verifier: list[str] = []
    if form_data.get("type_bien", "") not in ("Terrain nu", "Autre"):
        pts_a_verifier.append("Vérifier le DPE du bien")
    if form_data.get("annee_construction", 2000) < 1980:
        pts_a_verifier.append("Demander le diagnostic électrique (bâti antérieur à 1980)")
    if form_data.get("fissures") in ("Moyennes", "Importantes"):
        pts_a_verifier.append("Faire expertiser les fissures déclarées par un bureau d'études")
    if form_data.get("infiltrations") in ("Oui", "Majeures"):
        pts_a_verifier.append("Vérifier l'absence d'infiltrations actives par visite sur place")
    if form_data.get("etat_toiture") == "Mauvais":
        pts_a_verifier.append("Faire réaliser un diagnostic toiture par un couvreur")
    if not pts_a_verifier:
        pts_a_verifier = ["Vérifier la conformité des déclarations par pièces justificatives"]

    # Garantie juridique
    type_b = (form_data.get("type_bien") or "").lower()
    if "terrain" in type_b:
        garantie = "Garantie hypothécaire sur le terrain"
    elif "appartement" in type_b or "immeuble" in type_b:
        garantie = "IPPD (Immeuble par destination)"
    else:
        garantie = "Caution bancaire ou hypothèque conventionnelle"

    # Rapport synthétique
    rapport_synth = _build_rapport_synthetique(
        score_risque_bancaire, niveau,
        score_global, pts_forts, pts_faibles,
        len(risques_identifies), projection_data is not None,
        confidence_data.get("indice", 50)
    )

    # Points clés
    synthese_points = _build_synthese_points_cles(
        score_risque_bancaire, niveau,
        len(risques_identifies), len(prevention_recos), projection_data
    )

    return {
        # Section 1
        "score_risque_bancaire": score_risque_bancaire,
        "score_climatique": score_global,
        "niveau_risque_global": niveau,
        "impact_esg": "Passoire thermique" if form_data.get("isolation_toiture") == "faible" else "À évaluer",
        # Section 2
        "risques_identifies": risques_identifies,
        # Section 3
        "valeur_marche": market_data.get("valeur_estimee", 0),
        "valeur_ajustee": round(market_data.get("valeur_estimee", 0) * (1 - premium_data.get("decote_valeur_garantie_pct", 0) / 100)),
        "decote_pct": premium_data.get("decote_valeur_garantie_pct", 0),
        "source_valorisation": market_data.get("source", ""),
        # Section 4
        "garanties_assurance": garanties_assurance,
        "recommandation_garantie": garantie,
        # Section 5
        "prevention_recommandations": prevention_recos,
        "cout_total_prevention": _calc_cout_total(prevention_recos),
        # Section 6
        "projection_risque": projection_data,
        # Section 7
        "niveau_risque_bancaire": niveau,
        "indice_confiance": confidence_data.get("indice", 50),
        "avis_analyste": avis,
        "rapport_synthetique": rapport_synth,
        "synthese_points_cles": synthese_points,
        "analyse_complete_url": f"/api/bank/report/{session_id}/pdf",
        # Champs legacy
        "taux_propose": round(taux_base + premium_data.get("majoration_taux_interet", 0), 2),
        "majoration_taux": premium_data.get("majoration_taux_interet", 0),
        "exigences": premium_data.get("exigences_banque", []),
        "points_a_verifier": pts_a_verifier[:4],
        "points_forts": pts_forts[:3],
        "points_faibles": pts_faibles[:4],
        "conditions_suspensives": ["Examen des diagnostics techniques obligatoires avant décaissement"],
        "hard_stops": hard_stops,
        # Source des taux
        "source_taux": rates_data.get("source", "Banque de France"),
        "date_taux": rates_data.get("date_publication", "N/A"),
        "confiance_taux": 90 if "MeilleurTaux" in rates_data.get("source", "") else (70 if ".env" in rates_data.get("source", "").lower() else 40),
    }


# ── Noeud principal ─────────────────────────────────────────────────────────────

def run(state: TyphoonState) -> dict:
    """Exécute l'agent bancaire complet (7 sections) sur l'état courant.

    Intègre :
    - Outils financiers (DVF, taux, prime de risque)
    - Extraction des risques depuis les données système (scoring, géorisques)
    - Appel Mistral (avec fallback déterministe)
    - Génération du rapport complet en 7 sections
    """
    logger.info("bank_agent (noeud) -- analyse bancaire complète")

    if not HAS_BANK_TOOLS:
        logger.warning("bank tools indisponibles -- décision vide")
        return {"bank_decision": {}}

    # ── Récupération des données ─────────────────────────────────────────────
    form = state.get("formulaire", {}) or {}
    building_data = state.get("building_data", {}) or {}
    risk_scores = state.get("risk_scores", {}) or {}
    session_id = state.get("session_id", "rapport")

    adresse = form.get("adresse", building_data.get("adresse", {}).get("label", "Adresse inconnue"))
    score_global = risk_scores.get("score_global", 0)

    # ── 1. Outils financiers (API OpenData réelles) ──────────────────────────
    surface = float(form.get("surface", 100) or 100)
    type_bien = form.get("type_bien", "Maison") or "Maison"

    try:
        market_data = get_property_market_value(adresse, surface, type_bien)
        rates_data = get_current_bank_rates()
        market_rates = get_market_rates() if HAS_MARKET_RATES else {}
        premium_data = calculate_risk_premium(score_global)
        tool_data = {"market": market_data, "rates": rates_data, "premium": premium_data}
    except Exception as e:
        logger.error("bank_agent -- outils financiers échoués: %s", e)
        return {"bank_decision": {"erreur": f"Outils financiers indisponibles: {e}"}}

    # ── 2. Conformité & Hard Stops ───────────────────────────────────────────
    georisques_data = building_data.get("georisques", {})
    try:
        confidence_data = calculate_data_confidence(form, georisques_data)
        hard_stops = evaluate_hard_stops(score_global, form)
    except Exception as e:
        logger.error("bank_agent -- validation échouée: %s", e)
        confidence_data = {"indice": 50, "incoherences_detectees": []}
        hard_stops = []

    # ── 3. Extraction depuis les données système existantes ──────────────────
    try:
        risques_identifies = _extraire_risques_identifies(state, score_global)
    except Exception:
        risques_identifies = []

    prevention_recos = _extraire_prevention(state)
    projection_data = _extraire_projection(state, score_global)

    # ── 4. Calcul déterministe du score bancaire ─────────────────────────────
    score_risque_bancaire = min(100, max(0, int((score_global * 0.7) + ((100 - confidence_data.get("indice", 50)) * 0.3))))
    niveau = _niveau_risque_bancaire(score_risque_bancaire)

    # ── 5. Garanties d'assurance (déterministe) ──────────────────────────────
    garanties = _extraire_garanties_assurance(score_global, premium_data)

    # ── 6. Points forts / faibles (déterministe) ─────────────────────────────
    pts_forts, pts_faibles = _build_points_forces_faibles(form, score_global, confidence_data, market_data, hard_stops)

    # ── 7. Rapport synthétique (sans décision automatique) ───────────────────
    rapport_synth = _build_rapport_synthetique(
        score_risque_bancaire, niveau,
        score_global, pts_forts, pts_faibles,
        len(risques_identifies), projection_data is not None,
        confidence_data.get("indice", 50)
    )

    # ── 8. Points clés ───────────────────────────────────────────────────────
    synthese_points = _build_synthese_points_cles(
        score_risque_bancaire, niveau,
        len(risques_identifies), len(prevention_recos), projection_data
    )

    # ── 9. Calculs déterministes supplémentaires ─────────────────────────────
    isolation_toit = (form.get("isolation_toiture") or "").lower()
    impact_esg = "Passoire thermique" if isolation_toit == "faible" else "À évaluer"
    if score_global <= 30 and "Prêt Vert" in premium_data.get("exigences_banque", []):
        impact_esg = "Éligible au Prêt Vert"

    taux_base = market_rates.get("taux_moyen_20_ans", rates_data.get("taux_base_20_ans", 3.7))
    taux_propose_val = round(taux_base + premium_data.get("majoration_taux_interet", 0), 2)

    # Points à vérifier
    pts_a_verifier: list[str] = []
    type_bien_lower = (form.get("type_bien") or "").lower()
    if type_bien_lower not in ("terrain nu", ""):
        pts_a_verifier.append("Vérifier le DPE du bien")
    if form.get("annee_construction", 2000) < 1980:
        pts_a_verifier.append("Demander le diagnostic électrique (bâti antérieur à 1980)")
    if form.get("fissures") in ("Moyennes", "Importantes"):
        pts_a_verifier.append("Faire expertiser les fissures déclarées par un bureau d'études")
    if form.get("infiltrations") in ("Oui", "Majeures"):
        pts_a_verifier.append("Vérifier l'absence d'infiltrations actives par visite sur place")
    if form.get("etat_toiture") == "Mauvais":
        pts_a_verifier.append("Faire réaliser un diagnostic toiture par un couvreur")
    if not pts_a_verifier:
        pts_a_verifier = ["Vérifier la conformité des déclarations par pièces justificatives"]

    # Garantie juridique
    if "terrain" in type_bien_lower:
        recommandation_garantie = "Garantie hypothécaire sur le terrain"
    elif "appartement" in type_bien_lower or "immeuble" in type_bien_lower:
        recommandation_garantie = "IPPD (Immeuble par destination)"
    else:
        recommandation_garantie = "Caution bancaire ou hypothèque conventionnelle"

    # ── 10. Décision bancaire déterministe ────────────────────────────────
    bank_decision_dict = _build_fallback_bank_decision(
        form, score_global, score_risque_bancaire,
        market_data, rates_data, premium_data, confidence_data, hard_stops,
        risques_identifies, garanties, prevention_recos, projection_data,
        session_id=session_id, taux_base=taux_base,
    )

    logger.info("bank_agent (noeud) -- fallback technique (score_bancaire=%d)", score_risque_bancaire)
    return {"bank_decision": bank_decision_dict}
