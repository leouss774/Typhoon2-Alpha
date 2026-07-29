"""Outils (Tools) fournis a l'Agent Analyste Credit.
Ces fonctions appellent des API OpenData de l'Etat Francais pour valider les declarations clients.
"""

import datetime
import json
import logging
import os
import time
import urllib.parse

import requests

from backend.config.settings import get_settings
from backend.services import dvf_service
from backend.services.retry_decorator import retry
from backend.services.bank_rates import get_bank_rates, get_actuarial_grid

logger = logging.getLogger(__name__)

OPENDATA_TIMEOUT = 5


# ── Moyenne nationale dynamique depuis la base DVF ───────────────────────────
def _get_national_avg_m2() -> float:
    """Calcule la moyenne nationale du prix au m2 depuis la base DVF.

    Si la base DVF n'est pas disponible, utilise une valeur de secours
    issue des dernieres statistiques officielles (INSEE/CCI).
    """
    try:
        meta = dvf_service.get_metadata()
        if meta.get("total_mutations", 0) < 1000:
            logger.warning("Base DVF insuffisante pour calculer la moyenne nationale")
            return 2500.0

        # La moyenne est calculee periodiquement et stockee dans les metadonnees
        avg_m2 = meta.get("prix_m2_national")
        if avg_m2 and avg_m2 > 0:
            return float(avg_m2)

        # Fallback sur les dernieres statistiques INSEE connues
        # Valeur actualisee : moyenne nationale France entiere (INSEE, 2025)
        return 2650.0
    except Exception as e:
        logger.warning(f"Impossible de recuperer la moyenne nationale : {e}")
        return 2650.0


# ── Prix au m2 par defaut (calcule depuis la base DVF si disponible) ─────────
def get_default_m2() -> float:
    """Retourne le prix au m2 national calcule depuis les donnees DVF reelles.

    La valeur est mise a jour automatiquement a chaque execution de
    python scripts/update_dvf.py qui stocke la moyenne dans les metadonnees.
    """
    return _get_national_avg_m2()


def get_property_market_value(adresse: str, surface: float = 100, type_bien: str = "Maison") -> dict:
    """Recupere la valeur de marche d'un bien via la base DVF locale (data.gouv.fr).

    Sources par ordre de priorite :
    1. Base DVF locale SQLite (DGFiP officiel) -> transactions reelles par commune
    2. Estimation departementale DVF -> fallback par departement
    3. Estimation forfaitaire -> fallback ultime (moyenne nationale dynamique)

    La base DVF est mise a jour via : python scripts/update_dvf.py
    Les donnees sont publiees semestriellement par la DGFiP (avril + octobre).
    """
    default_m2 = get_default_m2()

    if not adresse or adresse == "Adresse inconnue":
        return {
            "valeur_estimee": round(default_m2 * 100),
            "devise": "EUR",
            "indice_confiance": 0,
            "source": "Adresse manquante",
            "dvf_update": dvf_service.get_metadata().get("last_update"),
        }

    # 1. Source principale : Base DVF locale SQLite
    result = dvf_service.query_market_value(adresse, surface, type_bien)

    # 2. Si donnees trouvees dans la base locale
    if not result.get("donnees_manquantes", True):
        return {
            "valeur_estimee": result["valeur_estimee"],
            "devise": "EUR",
            "indice_confiance": result["indice_confiance"],
            "source": result["source"],
            "nb_transactions": result.get("nb_transactions", 0),
            "prix_m2_median": result.get("prix_m2_median"),
            "periode_transactions": f"{result.get('date_min')} - {result.get('date_max')}",
            "dvf_update": dvf_service.get_metadata().get("last_update"),
        }

    # 3. Fallback : Estimation departementale via DVF
    geo = dvf_service._geocode(adresse)
    depcode = geo["citycode"][:2] if geo and geo.get("citycode") else ""
    if depcode:
        est_result = dvf_service.estimate_from_department(depcode, surface)
        if not est_result.get("donnees_manquantes", True):
            return {
                "valeur_estimee": est_result["valeur_estimee"],
                "devise": "EUR",
                "indice_confiance": est_result["indice_confiance"],
                "source": est_result["source"],
                "dvf_update": dvf_service.get_metadata().get("last_update"),
            }

    # 4. Fallback ultime (moyenne nationale dynamique depuis DVF)
    logger.warning(f"Aucune donnee DVF pour {adresse}, fallback estimation nationale")
    return {
        "valeur_estimee": round(default_m2 * max(surface, 50)),
        "devise": "EUR",
        "indice_confiance": 15,
        "source": f"Estimation nationale ({round(default_m2)} EUR/m2)",
        "dvf_update": dvf_service.get_metadata().get("last_update"),
        "aide": "Executez 'python scripts/update_dvf.py' pour initialiser la base DVF locale",
    }


def get_current_bank_rates() -> dict:
    """Taux directeurs bancaires actualises.

    Source : Banque de France - Observatoire Credit Logement (juillet 2026).
    Les valeurs sont configurables via les variables d'environnement :
    - TAUX_BASE_20_ANS : taux de reference pour un pret sur 20 ans
    - TAUX_DIRECTEUR_BCE : taux directeur de la Banque Centrale Europeenne

    Returns:
        dict: Taux avec metadonnees (date, source, grille actuarielle)
    """
    return get_bank_rates()


def calculate_risk_premium(score_climatique: int) -> dict:
    """Grille actuarielle : calcule la decote et la majoration de taux selon le score climatique.

    Les seuils et coefficients sont definis dans la grille actuarielle
    (bank_rates.py) et configurables via les variables d'environnement.

    Args:
        score_climatique: Score climatique du bien (0-100)

    Returns:
        dict: Decote, majoration de taux et exigences bancaires
    """
    grille = get_actuarial_grid()

    decote_pourcentage = 0
    majoration_taux = 0.0
    exigences = []

    if score_climatique > grille["seuil_critique"]:
        decote_pourcentage = grille["decote_critique_pct"]
        majoration_taux = grille["majo_critique"]
        exigences = [
            "Assurance multirisque renforcee obligatoire",
            "Etude approfondie des fondations requise"
        ]
    elif score_climatique > grille["seuil_eleve"]:
        decote_pourcentage = grille["decote_eleve_pct"]
        majoration_taux = grille["majo_eleve"]
        exigences = [
            "Preuve d'apport supplementaire demandee",
            "Clause de renovation sous 2 ans"
        ]
    elif score_climatique > grille["seuil_modere"]:
        decote_pourcentage = grille["decote_modere_pct"]
        majoration_taux = grille["majo_modere"]
        exigences = []
    else:
        decote_pourcentage = grille["decote_faible_pct"]
        majoration_taux = grille["majo_faible"]
        exigences = ["Eligible au Pret Vert"]

    return {
        "decote_valeur_garantie_pct": decote_pourcentage,
        "majoration_taux_interet": majoration_taux,
        "exigences_banque": exigences,
        "seuils_appliques": {
            "score_climatique": score_climatique,
            "seuil_critique": grille["seuil_critique"],
            "seuil_eleve": grille["seuil_eleve"],
            "seuil_modere": grille["seuil_modere"],
        }
    }


def calculate_data_confidence(client_form: dict, georisques_data: dict) -> dict:
    """Validation multi-sources des inputs pour TOUS les types de biens.

    Sources officielles utilisees :
    - BAN  : Base Adresse Nationale (api-adresse.data.gouv.fr) - validation adresse
    - ADEME: DPE France - verification surface & annee pour batiments
    - Logique structurelle - coherence des champs entre eux

    Chaque appel API est protege par un mecanisme de retry (3 tentatives, backoff exponentiel).
    """
    confiance = 100
    mismatches = []

    annee_declaree = client_form.get('annee_construction')
    surface_declaree = client_form.get('surface')
    adresse = client_form.get('adresse', '') or ''
    type_bien = client_form.get('type_bien', '').lower()
    is_terrain = 'terrain' in type_bien

    # SOURCE 1 : BAN - Base Adresse Nationale
    if adresse and adresse != "Adresse inconnue":
        try:
            url_ban = f"https://api-adresse.data.gouv.fr/search/?q={urllib.parse.quote(adresse)}&limit=1"
            @retry(tries=3, delay=0.5)
            def _call_ban():
                r = requests.get(url_ban, timeout=OPENDATA_TIMEOUT)
                r.raise_for_status()
                return r.json()
            data_ban = _call_ban()
            features = data_ban.get("features", [])
            if features:
                score_ban = features[0]["properties"].get("score", 0)
                label_officiel = features[0]["properties"].get("label", "")
                if score_ban < 0.5:
                    confiance -= 25
                    mismatches.append(f"[BAN] Adresse tres ambiguë (score={score_ban:.2f}). Adresse officielle suggeree : {label_officiel}.")
                elif score_ban < 0.7:
                    confiance -= 10
                    mismatches.append(f"[BAN] Adresse partiellement reconnue. Verifier : {label_officiel}.")
            else:
                confiance -= 30
                mismatches.append("[BAN] Adresse introuvable dans la Base Adresse Nationale. Risque de dossier fictif.")
        except Exception as e:
            logger.error(f"Erreur API BAN : {e}")
            confiance -= 10
            mismatches.append("[BAN] Service BAN indisponible, localisation non verifiee.")
    else:
        confiance -= 30
        mismatches.append("[FORMULAIRE] Adresse manquante. Champ obligatoire pour toute analyse bancaire.")

    # SOURCE 2 : Code INSEE
    code_insee = str(client_form.get('code_insee', '') or '')
    if code_insee:
        if not (code_insee.isdigit() and len(code_insee) == 5):
            confiance -= 10
            mismatches.append(f"[INSEE] Code INSEE invalide : '{code_insee}'. Format attendu : 5 chiffres (ex: 75056).")
    else:
        confiance -= 5
        mismatches.append("[FORMULAIRE] Code INSEE absent. Recommande pour la geolocalisation precise.")

    # SOURCE 3 : Coherence Numerique
    if surface_declaree is not None:
        try:
            s = float(surface_declaree)
            if s <= 0:
                confiance -= 20
                mismatches.append("[FORMULAIRE] Surface nulle ou negative : impossible.")
            elif not is_terrain and s > 50000:
                confiance -= 15
                mismatches.append(f"[FORMULAIRE] Surface batie ({s} m2) exceptionnellement grande. Verification requise.")
            elif is_terrain and s > 1_000_000:
                confiance -= 10
                mismatches.append(f"[FORMULAIRE] Surface terrain ({s} m2) extraordinairement grande. A documenter.")
        except (ValueError, TypeError):
            confiance -= 15
            mismatches.append("[FORMULAIRE] Surface non numerique. Valeur illisible.")

    if not is_terrain and annee_declaree is not None:
        try:
            annee = int(annee_declaree)
            annee_courante = datetime.date.today().year
            if annee < 1500 or annee > annee_courante:
                confiance -= 20
                mismatches.append(f"[FORMULAIRE] Annee de construction incoherente ({annee}). Plage valide : 1500-{annee_courante}.")
        except (ValueError, TypeError):
            confiance -= 10
            mismatches.append("[FORMULAIRE] Annee de construction non numerique.")

    # SOURCE 4 : ADEME DPE
    types_avec_dpe = ['maison', 'appartement', 'immeuble', 'commerce']
    if any(t in type_bien for t in types_avec_dpe) and adresse and adresse != "Adresse inconnue":
        try:
            url_ademe = f"https://data.ademe.fr/data-fair/api/v1/datasets/dpe-france/lines?q={urllib.parse.quote(adresse)}&size=1"
            @retry(tries=3, delay=0.5)
            def _call_ademe():
                r = requests.get(url_ademe, timeout=OPENDATA_TIMEOUT)
                r.raise_for_status()
                return r.json()
            data_ademe = _call_ademe()
            results = data_ademe.get("results", [])
            if results:
                bat = results[0]
                annee_dpe = bat.get("annee_construction")
                surface_dpe = bat.get("surface_thermique_lot")
                classe_dpe = bat.get("classe_consommation_energie", "?")

                if annee_declaree and annee_dpe:
                    try:
                        if abs(int(annee_declaree) - int(annee_dpe)) > 5:
                            confiance -= 20
                            mismatches.append(f"[ADEME] Annee declaree ({annee_declaree}) vs DPE officiel ({annee_dpe}) : ecart > 5 ans.")
                    except (ValueError, TypeError):
                        pass

                if surface_declaree and surface_dpe:
                    try:
                        if float(surface_declaree) > float(surface_dpe) * 1.20:
                            confiance -= 15
                            mismatches.append(f"[ADEME] Surface declaree ({surface_declaree} m2) superieure de >20% au DPE ({surface_dpe} m2). Suspicion de surestimation.")
                    except (ValueError, TypeError):
                        pass

                if classe_dpe in ['F', 'G']:
                    confiance -= 5
                    mismatches.append(f"[ADEME] DPE classe {classe_dpe} (passoire thermique). Fort impact ESG et valeur residuelle degradee.")
            else:
                confiance -= 5
                mismatches.append("[ADEME] Aucun DPE enregistre pour cette adresse. Donnees thermiques non verifiables.")
        except Exception as e:
            logger.error(f"Erreur ADEME : {e}")
            confiance -= 5
            mismatches.append("[ADEME] API DPE indisponible. Verification energetique impossible.")

    # SOURCE 5 : Coherence structurelle
    if not is_terrain:
        etat = (client_form.get('etat_structure') or '').lower()
        fissures = client_form.get('fissures', 'Non')
        infiltrations = client_form.get('infiltrations', 'Non')
        etat_toiture = (client_form.get('etat_toiture') or '').lower()

        if etat == 'bon' and fissures in ['Importantes']:
            confiance -= 15
            mismatches.append("[STRUCTURE] Incoherence : etat declare 'Bon' mais fissures 'Importantes'.")
        if etat == 'bon' and infiltrations in ['Oui', 'Majeures']:
            confiance -= 10
            mismatches.append("[STRUCTURE] Incoherence : etat declare 'Bon' mais infiltrations majeures.")
        if etat == 'bon' and etat_toiture == 'mauvais':
            confiance -= 10
            mismatches.append("[STRUCTURE] Incoherence : etat global 'Bon' mais toiture 'Mauvaise'.")

    if is_terrain and annee_declaree:
        confiance -= 10
        mismatches.append("[TERRAIN] Incoherence : annee de construction renseignee pour un terrain nu. Verifier le type de bien.")

    return {
        'indice': max(0, confiance),
        'incoherences_detectees': mismatches
    }


def evaluate_hard_stops(score_climatique: int, client_form: dict) -> list[str]:
    """Detecte les cas de refus automatique bancaire (Hard Stops).

    Args:
        score_climatique: Score climatique du bien (0-100)
        client_form: Formulaire de declaration du client

    Returns:
        list[str]: Liste des hard stops detectes (vide si aucun)
    """
    grille = get_actuarial_grid()
    hard_stops = []

    if score_climatique >= 90:
        hard_stops.append(
            f"Score climatique critique ({score_climatique}/100). "
            "Financement standard impossible."
        )
    if client_form.get('fissures', 'Non') == 'Importantes':
        hard_stops.append(
            "Fissures majeures declarees. "
            "Expertise de structure mandatee exigee avant tout octroi."
        )
    if client_form.get('infiltrations', 'Non') in ['Oui', 'Majeures']:
        hard_stops.append(
            "Infiltrations actives detectees. "
            "Risque structurel immediat - travaux prealables obligatoires."
        )

    # Alerte supplementaire basee sur la grille actuarielle
    if score_climatique > grille["seuil_critique"]:
        hard_stops.append(
            f"Score climatique au-dela du seuil critique ({grille['seuil_critique']}/100). "
            f"Decote maximale de {grille['decote_critique_pct']}% appliquee."
        )

    return hard_stops