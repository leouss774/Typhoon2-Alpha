"""Outils (Tools) fournis à l'Agent Analyste Crédit.
Ces fonctions simulent des appels à des services externes (API bancaires, base DVF pour l'immobilier, etc.).
"""

import random
import requests
import logging
import urllib.parse
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

def get_property_market_value(adresse: str) -> dict:
    """Appel réel aux API OpenData (API Adresse + DVF) pour obtenir la valeur de marché d'un bien.
    
    Args:
        adresse: L'adresse complète du bien.
    Returns:
        dict: Contient la 'valeur_estimee' en euros et l''indice_confiance'.
    """
    if not adresse or adresse == "Adresse inconnue":
        return {"valeur_estimee": 300000, "devise": "EUR", "indice_confiance": 0, "source": "Fallback (Adresse manquante)"}

    try:
        # 1. Géocodage (API Adresse Gouv)
        url_adresse = f"https://api-adresse.data.gouv.fr/search/?q={urllib.parse.quote(adresse)}&limit=1"
        res_adresse = requests.get(url_adresse, timeout=5)
        res_adresse.raise_for_status()
        features = res_adresse.json().get("features", [])
        
        if not features:
            raise ValueError("Adresse introuvable")
            
        coords = features[0]["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]
        
        # 2. DVF (Demandes Valeurs Foncières - api.cquest.org)
        # Recherche des ventes immobilières dans un rayon de 250m
        url_dvf = f"https://api.cquest.org/dvf?lat={lat}&lon={lon}&dist=250"
        res_dvf = requests.get(url_dvf, timeout=8)
        res_dvf.raise_for_status()
        
        mutations = res_dvf.json().get("resultats", [])
        valeurs_foncieres = [m["valeur_fonciere"] for m in mutations if m.get("valeur_fonciere") and m["nature_mutation"] == "Vente"]
        
        if valeurs_foncieres:
            # Moyenne des ventes récentes autour de l'adresse
            valeur_moyenne = sum(valeurs_foncieres) / len(valeurs_foncieres)
            return {
                "valeur_estimee": round(valeur_moyenne),
                "devise": "EUR",
                "indice_confiance": 90,
                "source": "OpenData DVF (Temps Réel)"
            }
        else:
            raise ValueError("Aucune mutation trouvée dans DVF")
            
    except Exception as e:
        logger.error(f"Erreur DVF, utilisation du fallback actuariel: {e}")
        # Fallback si l'API DVF est hors-ligne ou ne trouve rien
        return {
            "valeur_estimee": 350000,
            "devise": "EUR",
            "indice_confiance": 40,
            "source": "Moyenne Nationale (Fallback)"
        }

def get_current_bank_rates() -> dict:
    """Appel à l'API interne de la banque pour obtenir les taux directeurs du jour.
    (Ici, on garde des taux fixes pour l'exemple, car la Banque de France n'a pas d'API REST directe sans clé).
    """
    return {
        "taux_base_15_ans": 3.10,
        "taux_base_20_ans": 3.45,
        "taux_base_25_ans": 3.65,
        "date_maj": "aujourd'hui"
    }

def calculate_risk_premium(score_climatique: int) -> dict:
    """Simule un service actuariel qui évalue l'impact du risque sur le prêt.
    
    Args:
        score_climatique: Le score de risque global de 0 à 100 (0 = sans risque).
    Returns:
        dict: Recommandations sur la décote de la valeur du bien et la majoration du taux.
    """
    decote_pourcentage = 0
    majoration_taux = 0.0
    exigences = []

    if score_climatique > 80:
        decote_pourcentage = 15
        majoration_taux = 0.50
        exigences = ["Assurance multirisque renforcée obligatoire", "Étude approfondie des fondations requise"]
    elif score_climatique > 60:
        decote_pourcentage = 10
        majoration_taux = 0.20
        exigences = ["Preuve d'apport supplémentaire demandée", "Clause de rénovation sous 2 ans"]
    elif score_climatique > 30:
        decote_pourcentage = 5
        majoration_taux = 0.05
        exigences = []
    else:
        decote_pourcentage = 0
        majoration_taux = -0.10  # Taux préférentiel (Bonification ESG)
        exigences = ["Éligible au Prêt Vert"]

    return {
        "decote_valeur_garantie_pct": decote_pourcentage,
        "majoration_taux_interet": majoration_taux,
        "exigences_banque": exigences
    }

def calculate_data_confidence(client_form: dict, georisques_data: dict) -> dict:
    '''Compare le formulaire avec la réalité (API OpenData ADEME DPE) pour sortir un indice de confiance.'''
    confiance = 100
    mismatches = []
    
    annee_declaree = client_form.get('annee_construction')
    surface_declaree = client_form.get('surface')
    adresse = client_form.get('adresse')
    
    # Appel réel à l'API ADEME DPE (Open Data de l'État Français)
    if adresse and adresse != "Adresse inconnue":
        try:
            url_ademe = f"https://data.ademe.fr/data-fair/api/v1/datasets/dpe-france/lines?q={urllib.parse.quote(adresse)}&size=1"
            res_ademe = requests.get(url_ademe, timeout=5)
            res_ademe.raise_for_status()
            
            ademe_data = res_ademe.json().get("results", [])
            if ademe_data and len(ademe_data) > 0:
                batiment = ademe_data[0]
                annee_dpe = batiment.get("annee_construction")
                
                # Vérification croisée réelle de l'année
                if annee_declaree and annee_dpe and abs(int(annee_declaree) - int(annee_dpe)) > 5:
                    confiance -= 20
                    mismatches.append(f'Année déclarée ({annee_declaree}) divergente du registre officiel DPE ({annee_dpe}).')
                
                # Vérification croisée réelle de la surface
                surface_dpe = batiment.get("surface_thermique_lot")
                if surface_declaree and surface_dpe and float(surface_declaree) > float(surface_dpe) * 1.2:
                    confiance -= 15
                    mismatches.append(f'Surface déclarée ({surface_declaree}m²) supérieure au DPE officiel ({surface_dpe}m²).')
            else:
                confiance -= 5
                mismatches.append("Aucun DPE trouvé à cette adresse. Les déclarations n'ont pas pu être vérifiées.")
                
        except Exception as e:
            logger.error(f"Erreur de connexion API ADEME DPE : {e}")
            mismatches.append("API ADEME indisponible, vérification des déclarations impossible.")
            confiance -= 10
    else:
        confiance -= 15
        mismatches.append("Adresse manquante. Impossible de vérifier le cadastre/DPE.")

    return {
        'indice': max(0, confiance),
        'incoherences_detectees': mismatches
    }

def evaluate_hard_stops(score_climatique: int, client_form: dict) -> list[str]:
    '''Détecte les cas de refus automatique (Hard Stops).'''
    hard_stops = []
    if score_climatique >= 90:
        hard_stops.append('Score de risque critique (>= 90). Financement standard impossible.')
    if client_form.get('fissures', 'Non') == 'Importantes':
        hard_stops.append('Fissures majeures déclarées. Expertise mandatée exigée avant octroi.')
    if client_form.get('infiltrations', 'Non') == 'Oui':
         hard_stops.append('Infiltrations en cours détectées. Risque structurel immédiat.')
    return hard_stops
