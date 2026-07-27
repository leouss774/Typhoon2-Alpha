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
    N'oublie pas d'inclure 'decote_pct', 'majoration_taux', 'valeur_marche' et 'exigences' tels que fournis.
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
    
    # 3. Appel Mistral pour la synthèse finale
    try:
        decision = call_mistral_and_validate(SYSTEM_PROMPT_BANK, user_prompt, BankDecision)
        bank_decision_dict = decision.model_dump()
    except Exception as e:
        logger.error(f"Erreur de l'agent bancaire : {e}")
        # Fallback en cas de problème Mistral
        bank_decision_dict = {
            "valeur_marche": market_data["valeur_estimee"],
            "valeur_ajustee": market_data["valeur_estimee"] * (1 - premium_data["decote_valeur_garantie_pct"]/100),
            "decote_pct": premium_data["decote_valeur_garantie_pct"],
            "taux_propose": rates_data["taux_base_20_ans"] + premium_data["majoration_taux_interet"],
            "majoration_taux": premium_data["majoration_taux_interet"],
            "exigences": premium_data["exigences_banque"],
            "points_a_verifier": ["Vérifier le DPE de la maison", "Confirmer l'année de construction"],
            "indice_confiance": confidence_data['indice'],
            "statut_dossier": "Étude Manuelle" if hard_stops else "Fast-Track",
            "niveau_risque_global": "Élevé" if hard_stops else "Modéré",
            "impact_esg": "À évaluer",
            "points_forts": ["Valeur immobilière évaluée"],
            "points_faibles": hard_stops if hard_stops else ["Incohérences de données"],
            "recommandation_garantie": "Étude approfondie requise",
            "conditions_suspensives": ["Vérification humaine requise"],
            "hard_stops": hard_stops,
            "avis_analyste": "Erreur IA : Décision technique appliquée par défaut sans analyse approfondie."
        }
    
    return {
        "bank_decision": bank_decision_dict
    }
