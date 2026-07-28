from __future__ import annotations

import logging
from typing import Any
from backend.agent_graph.state import TyphoonState
from backend.tools.bank_tools import get_property_market_value, get_current_bank_rates, calculate_risk_premium, calculate_data_confidence, evaluate_hard_stops
from backend.models.bank_schemas import BankDecision
from backend.services.mistral_client import call_mistral_and_validate

logger = logging.getLogger(__name__)

# ── Helper : mapping score → niveau ────────────────────────────────────────────
def _niveau_risque(score: int) -> str:
    if score >= 70: return "critique"
    if score >= 55: return "eleve"
    if score >= 35: return "modere"
    return "faible"

def _niveau_risque_bancaire(score: int) -> str:
    if score >= 60: return "Élevé"
    if score >= 35: return "Modéré"
    return "Faible"

# ── SYSTEM_PROMPT — Aide à la décision (pas de décision automatique) ───────
SYSTEM_PROMPT_BANK = """Tu es un expert en analyse de risque immobilier pour banque et assurance.
Tu génères un rapport d'aide à la décision en 7 sections pour l'analyste crédit.

INSTRUCTIONS :
1. Analyser les informations financières et climatiques du bien
2. Identifier les risques et leur sévérité
3. Lister les points de vigilance et vérifications nécessaires

⚠️ IMPORTANT : Tu es un OUTIL D'AIDE À LA DÉCISION.
N'indique JAMAIS de décision automatique (pas d'acceptation, pas de refus,
  pas de Fast-Track, pas d'Étude Manuelle).
Tu fournis uniquement des éléments d'analyse pour l'expert humain.

STRUCTURE IMPÉRATIVE DE TA RÉPONSE JSON :

1. 📊 Score de risque du bien :
   - score_risque_bancaire (0-100), score_climatique (0-100)
   - niveau_risque_global (Faible, Modéré, Élevé)
   - impact_esg

2. ⚠️ Principaux risques identifiés :
   - risques_identifies: [{nom, score(int), niveau(faible|modere|eleve|critique), zone_impactee, description}]

3. 💰 Valeur ajustée du bien :
   - valeur_marche, valeur_ajustee, decote_pct, source_valorisation

4. 🛡️ Garanties d'assurance :
   - recommandation_garantie (type juridique)

5. 🏗️ Recommandations de prévention :
   - prevention_recommandations (laissées vides)

6. 📈 Projection de l'évolution du risque :
   - projection_risque

7. 📄 Rapport d'analyse :
   - niveau_risque_bancaire (Faible, Modéré, Élevé) — PUREMENT INDICATIF
   - indice_confiance (0-100)
   - avis_analyste (texte argumenté pour l'expert)
   - rapport_synthetique (rapport complet 5-8 phrases)
   - synthese_points_cles (max 5)

Champs supplémentaires : taux_propose, majoration_taux, exigences,
points_a_verifier (2-4), points_forts (2-3), points_faibles (2-3),
conditions_suspensives (1-2), recommandation_garantie, hard_stops.

Sois professionnel, factuel et très pointilleux — mais NE PRENDS AUCUNE DÉCISION.
"""


def build_bank_user_prompt(
    form: dict, score_global: int, tool_data: dict,
    confidence_data: dict, hard_stops: list[str],
    risques_identifies: list[dict],
    projection_data: dict | None = None
) -> str:
    adresse = form.get("adresse", "Adresse inconnue")
    
    # Formatage des risques identifiés
    risques_txt = "\n".join(
        f"  - {r['nom']}: score {r['score']}/100 ({r['niveau']}) — impact: {r['zone_impactee']}"
        for r in risques_identifies
    ) or "  Aucun risque majeur détecté."
    
    # Formatage projection 2050
    proj_txt = ""
    if projection_data and projection_data.get("score_projete"):
        proj_txt = (
            f"\n[Projection 2050]\n"
            f"  Score actuel: {projection_data.get('score_actuel', score_global)}/100\n"
            f"  Score projeté 2050: {projection_data.get('score_projete', score_global)}/100\n"
            f"  Scénario: {projection_data.get('scenario', 'Standard')}\n"
        )
    
    return f"""
    Bien situé au {adresse} :
    
    [Déclarations client]
    - Type: {form.get('type_bien', 'Non spécifié')}
    - Année construction: {form.get('annee_construction', 'Inconnue')}
    - État toiture: {form.get('etat_toiture', 'Inconnu')}
    - Fissures: {form.get('fissures', 'Non')}
    - Infiltrations: {form.get('infiltrations', 'Non')}
    
    [Fiabilité]
    - Indice confiance: {confidence_data['indice']}%
    - Incohérences: {', '.join(confidence_data['incoherences_detectees'][:3]) if confidence_data['incoherences_detectees'] else 'Aucune'}
    - Hard Stops: {', '.join(hard_stops) if hard_stops else 'Aucun'}
    
    [Scores]
    - Score climatique: {score_global}/100
    - Risques identifiés:\n{risques_txt}
    {proj_txt}
    
    [Financier]
    - Valeur marché (DVF): {tool_data['market']['valeur_estimee']} € — Source: {tool_data['market'].get('source', 'N/A')}
    - Taux base 20 ans: {tool_data['rates']['taux_base_20_ans']}%
    - Décote actuarielle: {tool_data['premium']['decote_valeur_garantie_pct']}%
    - Majoration taux: {tool_data['premium']['majoration_taux_interet']}%
    - Exigences: {', '.join(tool_data['premium']['exigences_banque']) if tool_data['premium']['exigences_banque'] else 'Aucune'}
    
    GÉNÈRE LE RAPPORT COMPLET EN 7 SECTIONS AU FORMAT JSON DÉCRIT DANS LE PROMPT SYSTÈME.
    """

# ── Extraction des risques depuis les données système ──────────────────────────
def _extraire_risques_identifies(state: TyphoonState, score_global: int) -> list[dict]:
    """Extrait les risques identifiés depuis zone_recommandations et georisques."""
    risques = []
    
    # Depuis les zones
    zones = {}
    if state.zone_recommandations and isinstance(state.zone_recommandations, dict):
        zones = state.zone_recommandations.get("zones", {}) or {}
    for zone_name, zone_data in zones.items():
        if isinstance(zone_data, dict) and zone_data.get("risque", 0) >= 25:
            risques.append({
                "nom": zone_data.get("alea_principal", zone_name),
                "score": zone_data.get("risque", 0),
                "niveau": zone_data.get("niveau", _niveau_risque(zone_data.get("risque", 0))),
                "zone_impactee": zone_name.capitalize(),
                "description": zone_data.get("justification", "")[:150],
            })
    
    # Depuis les scores par aléa
    scores_alea = {}
    if state.zone_recommandations and isinstance(state.zone_recommandations, dict):
        scores_alea = state.zone_recommandations.get("scores_par_alea", {}) or {}
    ALEA_ZONE_MAP = {
        "inondation": ("Inondation / humidité", "Sous-sol"),
        "rga": ("Retrait-gonflement des argiles", "Fondations"),
        "canicule": ("Canicule / stress thermique", "Toiture"),
        "tempete": ("Tempête / vent", "Toiture & Murs"),
    }
    for alea_key, (nom, zone) in ALEA_ZONE_MAP.items():
        score_alea = scores_alea.get(alea_key, 0)
        if score_alea >= 25 and not any(r["nom"] == nom for r in risques):
            risques.append({
                "nom": nom,
                "score": score_alea,
                "niveau": _niveau_risque(score_alea),
                "zone_impactee": zone,
                "description": f"Aléa {nom} détecté avec un score de {score_alea}/100.",
            })
    
    # Trier par score décroissant
    risques.sort(key=lambda r: r["score"], reverse=True)
    return risques[:6]  # max 6 risques


def _extraire_projection(state: TyphoonState, score_global: int) -> dict | None:
    """Extrait la projection 2050 depuis zone_recommandations."""
    if not state.zone_recommandations or not isinstance(state.zone_recommandations, dict):
        return None
    projection = state.zone_recommandations.get("projection_2050", {}) or {}
    if not projection:
        return None
    score_projete = projection.get("score_global", score_global)
    return {
        "horizon": "2050",
        "score_actuel": score_global,
        "score_projete": score_projete,
        "aggravation": score_projete - score_global,
        "scenario": projection.get("scenario_climatique", "Standard CMIP6"),
        "zones_projetees": projection.get("zones", {}),
    }


def _extraire_prevention(state: TyphoonState) -> list[dict]:
    """Extrait les recommandations de prévention depuis les zones."""
    recos = []
    if not state.zone_recommandations or not isinstance(state.zone_recommandations, dict):
        return recos
    zones = state.zone_recommandations.get("zones", {}) or {}
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
    rapport.append(f"RAPPORT D'ANALYSE DE RISQUE CRÉDIT")
    rapport.append(f"")
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

# ── Noeud principal ─────────────────────────────────────────────────────────────
def bank_decision_node(state: TyphoonState) -> dict:
    """Noeud LangGraph de l'agent bancaire — génère l'analyse crédit complète en 7 sections."""
    logger.info("Exécution de l'Agent Bancaire...")
    
    form = state.client_form if isinstance(state.client_form, dict) else {}
    adresse = form.get("adresse", "Adresse inconnue")
    
    # Extraire le score global depuis les zones
    score_global = 0
    if state.zone_recommandations and isinstance(state.zone_recommandations, dict):
        score_global = state.zone_recommandations.get("score_global", 0) or 0
    
    # 1. Outils financiers (API OpenData réelles)
    surface = float(form.get("surface", 100) or 100)
    type_bien = form.get("type_bien", "Maison") or "Maison"
    market_data = get_property_market_value(adresse, surface, type_bien)
    rates_data = get_current_bank_rates()
    premium_data = calculate_risk_premium(score_global)
    tool_data = {"market": market_data, "rates": rates_data, "premium": premium_data}
    
    # 2. Conformité & Hard Stops
    georisques_data = state.georisques_data or {}
    confidence_data = calculate_data_confidence(form, georisques_data)
    hard_stops = evaluate_hard_stops(score_global, form)
    
    # 3. Extraction depuis les données système existantes
    risques_identifies = _extraire_risques_identifies(state, score_global)
    prevention_recos = _extraire_prevention(state)
    projection_data = _extraire_projection(state, score_global)
    
    # 4. Calcul déterministe du score bancaire
    score_risque_bancaire = min(100, max(0, int((score_global * 0.7) + ((100 - confidence_data['indice']) * 0.3))))
    niveau = _niveau_risque_bancaire(score_risque_bancaire)
    
    # 5. Garanties d'assurance (déterministe)
    garanties = _extraire_garanties_assurance(score_global, premium_data)
    
    # 6. Points forts / faibles (déterministe)
    pts_forts, pts_faibles = _build_points_forces_faibles(form, score_global, confidence_data, market_data, hard_stops)
    
    # 7. Rapport synthétique (sans décision automatique)
    rapport_synth = _build_rapport_synthetique(
        score_risque_bancaire, niveau,
        score_global, pts_forts, pts_faibles,
        len(risques_identifies), projection_data is not None,
        confidence_data['indice']
    )
    
    # 8. Points clés
    synthese_points = _build_synthese_points_cles(
        score_risque_bancaire, niveau,
        len(risques_identifies), len(prevention_recos), projection_data
    )
    
    # 9. Calculs déterministes supplémentaires (pour écraser TOUTE hallucination Mistral)
    # Impact ESG
    isolation_toit = (form.get("isolation_toiture") or "").lower()
    impact_esg = "Passoire thermique" if isolation_toit == "faible" else "À évaluer"
    if score_global <= 30 and "Prêt Vert" in premium_data.get("exigences_banque", []):
        impact_esg = "Éligible au Prêt Vert"
    
    # Taux et financement
    taux_propose_val = round(rates_data["taux_base_20_ans"] + premium_data["majoration_taux_interet"], 2)
    
    # Points à vérifier (déterministes)
    pts_a_verifier = []
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
    
    # 10. Construction du prompt utilisateur enrichi
    user_prompt = build_bank_user_prompt(
        form, score_global, tool_data, confidence_data, hard_stops,
        risques_identifies, projection_data
    )
    
    # 11. Appel Mistral (avec fallback robuste)
    try:
        decision = call_mistral_and_validate(SYSTEM_PROMPT_BANK, user_prompt, BankDecision)
        bank_decision_dict = decision.model_dump()
        # Nettoyage des champs interdits (Mistral peut générer statut_dossier par mégarde)
        bank_decision_dict.pop("statut_dossier", None)
        # ═══════════════════════════════════════════════════════════════════
        # ÉCRASEMENT TOTAL : Aucune valeur Mistral n'est gardée
        # Tous les champs sont forcés avec des valeurs déterministes
        # ═══════════════════════════════════════════════════════════════════
        # Section 1 - Score
        bank_decision_dict["score_risque_bancaire"] = score_risque_bancaire
        bank_decision_dict["score_climatique"] = score_global
        bank_decision_dict["niveau_risque_global"] = niveau
        bank_decision_dict["niveau_risque_bancaire"] = niveau
        bank_decision_dict["impact_esg"] = impact_esg
        bank_decision_dict["indice_confiance"] = confidence_data['indice']
        # Section 2 - Risques
        bank_decision_dict["risques_identifies"] = risques_identifies
        bank_decision_dict["hard_stops"] = hard_stops
        # Section 3 - Valeur
        bank_decision_dict["valeur_marche"] = market_data["valeur_estimee"]
        bank_decision_dict["valeur_ajustee"] = round(market_data["valeur_estimee"] * (1 - premium_data["decote_valeur_garantie_pct"] / 100))
        bank_decision_dict["decote_pct"] = premium_data["decote_valeur_garantie_pct"]
        bank_decision_dict["source_valorisation"] = market_data.get("source", "")
        # Section 4 - Assurance
        bank_decision_dict["garanties_assurance"] = garanties
        bank_decision_dict["recommandation_garantie"] = recommandation_garantie
        # Section 5 - Prévention
        bank_decision_dict["prevention_recommandations"] = prevention_recos
        bank_decision_dict["cout_total_prevention"] = _calc_cout_total(prevention_recos)
        # Section 6 - Projection
        bank_decision_dict["projection_risque"] = projection_data
        # Section 7 - Rapport
        bank_decision_dict["rapport_synthetique"] = rapport_synth
        bank_decision_dict["synthese_points_cles"] = synthese_points
        bank_decision_dict["avis_analyste"] = rapport_synth  # Fallback: utiliser le rapport synthétique
        # Financier
        bank_decision_dict["taux_propose"] = taux_propose_val
        bank_decision_dict["majoration_taux"] = premium_data["majoration_taux_interet"]
        bank_decision_dict["exigences"] = premium_data["exigences_banque"]
        # Points forts/faibles
        bank_decision_dict["points_forts"] = pts_forts[:3]
        bank_decision_dict["points_faibles"] = pts_faibles[:4]
        # Vérifications
        # Source des taux (dynamique selon le scraper / .env / defaut)
        taux_source = rates_data.get("source", "Banque de France")
        taux_date = rates_data.get("date_publication", "N/A")
        # Niveau de confiance = scraper MeilleurTaux = 90, .env = 70, defaut = 40
        if "MeilleurTaux" in taux_source:
            confiance_taux = 90
        elif ".env" in taux_source.lower() or "env" in taux_source.lower():
            confiance_taux = 70
        else:
            confiance_taux = 40
        bank_decision_dict["source_taux"] = taux_source
        bank_decision_dict["date_taux"] = taux_date
        bank_decision_dict["confiance_taux"] = confiance_taux

        bank_decision_dict["points_a_verifier"] = pts_a_verifier[:4]
        bank_decision_dict["conditions_suspensives"] = ["Examen des diagnostics techniques obligatoires avant décaissement"]
        bank_decision_dict["analyse_complete_url"] = f"/api/bank/report/{state.session_id}/pdf"
    except Exception as e:
        logger.warning(f"Agent bancaire Mistral indisponible, fallback technique : {e}")
        form_with_session = {**form, "_session_id": state.session_id}
        bank_decision_dict = _build_fallback_bank_decision(
            form_with_session, score_global, score_risque_bancaire,
            market_data, rates_data, premium_data, confidence_data, hard_stops,
            risques_identifies, garanties, prevention_recos, projection_data
        )
    
    return {"bank_decision": bank_decision_dict}


# ── Helpers : points forts/faibles, synthèse, coûts ───────────────────────────
def _build_points_forces_faibles(
    form_data: dict, score_global: int,
    confidence_data: dict, market_data: dict,
    hard_stops: list[str]
) -> tuple[list[str], list[str]]:
    pts_forts = []
    if market_data.get("source") and "Fallback" not in str(market_data.get("source", "")):
        pts_forts.append(f"Valorisation DVF réelle : {market_data['valeur_estimee']}€")
    else:
        pts_forts.append("Valeur de marché estimée")
    if score_global < 30:
        pts_forts.append("Faible exposition climatique")
    if confidence_data['indice'] >= 80:
        pts_forts.append("Données déclaratives cohérentes (KYC favorable)")
    
    pts_faibles = list(hard_stops) if hard_stops else []
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
    if confidence_data['indice'] < 70:
        pts_faibles.append(f"Indice de confiance limité ({confidence_data['indice']}%)")
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


# ── Fallback complet avec les 7 sections ────────────────────────────────────────
def _build_fallback_bank_decision(
    form_data: dict, score_global: int, score_risque_bancaire: int,
    market_data: dict, rates_data: dict, premium_data: dict,
    confidence_data: dict, hard_stops: list[str],
    risques_identifies: list[dict], garanties_assurance: list[dict],
    prevention_recos: list[dict], projection_data: dict | None,
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
    pts_a_verifier = []

    session_id = form_data.get("_session_id", "rapport")
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
        confidence_data['indice']
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
        "valeur_marche": market_data["valeur_estimee"],
        "valeur_ajustee": round(market_data["valeur_estimee"] * (1 - premium_data["decote_valeur_garantie_pct"] / 100)),
        "decote_pct": premium_data["decote_valeur_garantie_pct"],
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
        "indice_confiance": confidence_data['indice'],
        "avis_analyste": avis,
        "rapport_synthetique": rapport_synth,
        "synthese_points_cles": synthese_points,            "analyse_complete_url": f"/api/bank/report/{session_id}/pdf",
        # Champs legacy
        "taux_propose": rates_data["taux_base_20_ans"] + premium_data["majoration_taux_interet"],
        "majoration_taux": premium_data["majoration_taux_interet"],
        "exigences": premium_data["exigences_banque"],
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
