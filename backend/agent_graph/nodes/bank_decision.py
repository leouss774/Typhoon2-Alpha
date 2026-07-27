from __future__ import annotations

import logging
from backend.agent_graph.state import TyphoonState
from backend.tools.bank_tools import get_property_market_value, get_current_bank_rates, calculate_risk_premium, calculate_data_confidence, evaluate_hard_stops
from backend.models.bank_schemas import BankDecision
from backend.services.mistral_client import call_mistral_and_validate

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_BANK = """Tu es l'Analyste Crédit IA d'une grande banque de financement immobilier.
Ton rôle est double :
1. Synthétiser les informations financières et climatiques pour générer un 'avis_analyste' justifiant la décision.
2. Analyser les déclarations du client pour établir une liste stricte de 'points_a_verifier' (vérification de conformité, demande de DPE, visite d'expert, etc.) pour lutter contre la fraude et garantir le prêt.
3. Prendre en compte l'indice de confiance et les Hard Stops pour formuler un 'statut_dossier' strict (Fast-Track, Étude Manuelle, ou Refus Automatique).

Sois professionnel, concis et très pointilleux sur la gestion du risque.
"""

def build_bank_user_prompt(form: dict, score_global: int, tool_data: dict, confidence_data: dict, hard_stops: list[str]) -> str:
    adresse = form.get("adresse", "Adresse inconnue")
    return f"""
    Voici les données du bien situé au {adresse} :
    
    [Déclarations du client à vérifier] :
    - Année de construction : {form.get('annee_construction', 'Inconnue')}
    - État de la toiture déclaré : {form.get('etat_toiture', 'Inconnu')}
    - Présence de fissures déclarée : {form.get('fissures', 'Non')}
    
    [Données Techniques et Financières] :
    - Indice de Confiance de la donnée : {confidence_data['indice']}%
    - Incohérences détectées (BDNB/Cadastre) : {', '.join(confidence_data['incoherences_detectees']) if confidence_data['incoherences_detectees'] else 'Aucune'}
    - Règles bloquantes (Hard Stops) : {', '.join(hard_stops) if hard_stops else 'Aucune'}
    
    - Score Risque Climatique : {score_global}/100
    - Valeur de marché estimée (DVF) : {tool_data['market']['valeur_estimee']} €
    - Taux de base bancaire (20 ans) : {tool_data['rates']['taux_base_20_ans']} %
    
    L'actuariat a recommandé :
    - Décote sur la valeur de garantie : {tool_data['premium']['decote_valeur_garantie_pct']} %
    - Majoration du taux d'intérêt : {tool_data['premium']['majoration_taux_interet']} %
    - Exigences : {', '.join(tool_data['premium']['exigences_banque']) if tool_data['premium']['exigences_banque'] else 'Aucune'}

    Ton objectif est de fournir une synthèse exécutive structurée pour le comité de crédit.
    ADAPTE tes recommandations en fonction du type de bien (ex: pour un 'Terrain nu', exige une étude de sol G2 plutôt qu'un DPE ; pour une 'Usine', demande un audit de pollution environnementale, etc.).

    Calcule la 'valeur_ajustee' et le 'taux_propose' exacts, puis génère :
    - Un 'niveau_risque_global' (Faible, Modéré, Élevé)
    - Un 'impact_esg' qualifiant la performance climatique du dossier
    - 2 à 3 'points_forts' du dossier
    - 2 à 3 'points_faibles'
    - Une 'recommandation_garantie' (ex: IPPD, Hypothèque, Caution)
    - 1 à 2 'conditions_suspensives' (ex: Réalisation de travaux DPE obligatoires, Contre-expertise)
    - Un 'avis_analyste' professionnel et tranché.
    - 2 à 4 'points_a_verifier' impérativement par le conseiller bancaire.
    
    Ton 'statut_dossier' DOIT être 'Refus Automatique' si des Hard Stops sont présents, sinon choisis entre 'Fast-Track' et 'Étude Manuelle'.
    Ton 'indice_confiance' DOIT correspondre à {confidence_data['indice']}.
    Ton 'hard_stops' DOIT contenir la liste des règles bloquantes détectées.
    N'oublie pas d'inclure 'decote_pct', 'majoration_taux', 'valeur_marche', 'exigences' et 'score_climatique' ({score_global}).
    IMPORTANT : Place TOUS les champs directement à la racine de ton objet JSON final. Ne crée surtout pas de sous-objet "synthese_executive".
    """

def bank_decision_node(state: TyphoonState) -> dict:
    """Noeud LangGraph de l'agent bancaire."""
    logger.info("Exécution de l'Agent Bancaire...")
    
    adresse = state.client_form.get("adresse", "Adresse inconnue") if isinstance(state.client_form, dict) else "Adresse inconnue"
    
    # Extraire le score global
    score_global = 0
    if state.zone_recommandations and isinstance(state.zone_recommandations, dict):
        score_global = state.zone_recommandations.get("score_global", 0)
    
    # 1. Utilisation des Tools (sans hardcoder la logique IA)
    market_data = get_property_market_value(adresse)
    rates_data = get_current_bank_rates()
    premium_data = calculate_risk_premium(score_global)
    
    tool_data = {
        "market": market_data,
        "rates": rates_data,
        "premium": premium_data
    }
    
    # 2. Vérification de Conformité et Hard Stops
    # Normalement on croise avec georisques_data de l'état, ici on simule
    georisques_mock = state.georisques_data or {}
    confidence_data = calculate_data_confidence(state.client_form, georisques_mock)
    hard_stops = evaluate_hard_stops(score_global, state.client_form)
    
    # 3. Construction des Prompts
    user_prompt = build_bank_user_prompt(state.client_form, score_global, tool_data, confidence_data, hard_stops)
    
    # Calcul déterministe (toujours fait, même si Mistral réussit)
    score_risque_bancaire = min(100, max(0, int((score_global * 0.7) + ((100 - confidence_data['indice']) * 0.3))))
    
    # 3. Appel Mistral pour la synthèse narrative (avis_analyste, points_forts/faibles)
    try:
        decision = call_mistral_and_validate(SYSTEM_PROMPT_BANK, user_prompt, BankDecision)
        bank_decision_dict = decision.model_dump()
        # S'assurer que le score bancaire calculé par le code est toujours utilisé
        bank_decision_dict["score_risque_bancaire"] = score_risque_bancaire
    except Exception as e:
        logger.warning(f"Agent bancaire Mistral indisponible, fallback technique : {e}")
        bank_decision_dict = _build_fallback_bank_decision(
            state.client_form, score_global, score_risque_bancaire,
            market_data, rates_data, premium_data, confidence_data, hard_stops
        )
    
    return {"bank_decision": bank_decision_dict}


def _build_fallback_bank_decision(
    form: dict, score_global: int, score_risque_bancaire: int,
    market_data: dict, rates_data: dict, premium_data: dict,
    confidence_data: dict, hard_stops: list[str],
) -> dict:
    """Fallback technique quand Mistral est indisponible.
    Produit des messages DIFFÉRENCIÉS selon les données formulaire.
    """
    form_data = form if isinstance(form, dict) else {}
    
    # Niveau de risque basé sur le score réel
    if hard_stops:
        niveau = "Élevé"
        statut = "Refus Automatique"
    elif score_risque_bancaire >= 60:
        niveau = "Élevé"
        statut = "Étude Manuelle"
    elif score_risque_bancaire >= 35:
        niveau = "Modéré"
        statut = "Étude Manuelle"
    else:
        niveau = "Faible"
        statut = "Fast-Track"
    
    # Points forts personnalisés selon le bien
    pts_forts = []
    if market_data.get("source") and "Fallback" not in str(market_data.get("source", "")):
        pts_forts.append(f"Valorisation DVF : {market_data['valeur_estimee']}€")
    else:
        pts_forts.append("Valeur de marché estimée")
    if score_global < 30:
        pts_forts.append("Faible exposition climatique")
    if confidence_data['indice'] >= 80:
        pts_forts.append("Données déclaratives cohérentes")
    
    # Points faibles personnalisés selon les signaux formulaire
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
            pts_faibles.append(f"Incohérence : {inc[:80]}...")
    if not pts_faibles:
        pts_faibles.append("Aucun point faible critique détecté — vérifications standard requises")
    
    # Avis différencié selon le score
    if niveau == "Élevé":
        avis = (f"Le dossier présente un niveau de risque élevé (score climatique {score_global}/100, "
                f"score bancaire {score_risque_bancaire}/100). "
                f"{len(pts_faibles)} points de vigilance identifiés. Une expertise humaine approfondie est indispensable.")
    elif niveau == "Modéré":
        avis = (f"Risque modéré (score climatique {score_global}/100, score bancaire {score_risque_bancaire}/100). "
                f"Quelques points de vigilance nécessitent une vérification documentaire avant déblocage des fonds.")
    else:
        avis = (f"Profil de risque faible (score climatique {score_global}/100, score bancaire {score_risque_bancaire}/100). "
                f"Les déclarations sont cohérentes. Éligible au circuit Fast-Track.")
    
    
    # Points à vérifier personnalisés
    pts_a_verifier = []
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
    
    # Garantie adaptée au type de bien
    type_b = (form_data.get("type_bien") or "").lower()
    if "terrain" in type_b:
        garantie = "Garantie hypothécaire sur le terrain"
    elif "appartement" in type_b or "immeuble" in type_b:
        garantie = "IPPD (Immeuble par destination)"
    else:
        garantie = "Caution bancaire ou hypothèque conventionnelle"
    
    return {
        "valeur_marche": market_data["valeur_estimee"],
        "valeur_ajustee": market_data["valeur_estimee"] * (1 - premium_data["decote_valeur_garantie_pct"] / 100),
        "decote_pct": premium_data["decote_valeur_garantie_pct"],
        "taux_propose": rates_data["taux_base_20_ans"] + premium_data["majoration_taux_interet"],
        "majoration_taux": premium_data["majoration_taux_interet"],
        "exigences": premium_data["exigences_banque"],
        "points_a_verifier": pts_a_verifier[:4],
        "indice_confiance": confidence_data['indice'],
        "score_climatique": score_global,
        "score_risque_bancaire": score_risque_bancaire,
        "statut_dossier": statut,
        "niveau_risque_global": niveau,
        "impact_esg": "Passoire thermique" if form_data.get("isolation_toiture") == "faible" else "À évaluer",
        "points_forts": pts_forts[:3],
        "points_faibles": pts_faibles[:4],
        "recommandation_garantie": garantie,
        "conditions_suspensives": ["Examen des diagnostics techniques obligatoires avant décaissement"],
        "hard_stops": hard_stops,
        "avis_analyste": avis,
    }
