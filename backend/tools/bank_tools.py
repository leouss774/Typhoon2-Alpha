"""Outils (Tools) fournis à l'Agent Analyste Crédit.
Ces fonctions appellent des API OpenData de l'État Français pour valider les déclarations clients.
"""

import datetime
import requests
import logging
import urllib.parse
from backend.config.settings import get_settings

logger = logging.getLogger(__name__)

# Timeout court pour les appels OpenData (évite les blocages réseau)
OPENDATA_TIMEOUT = 2


def get_property_market_value(adresse: str) -> dict:
    """Appel réel aux API OpenData (API Adresse + DVF) pour obtenir la valeur de marché d'un bien."""
    if not adresse or adresse == "Adresse inconnue":
        return {"valeur_estimee": 300000, "devise": "EUR", "indice_confiance": 0, "source": "Fallback (Adresse manquante)"}

    try:
        # 1. Géocodage (API Adresse Gouv)
        url_adresse = f"https://api-adresse.data.gouv.fr/search/?q={urllib.parse.quote(adresse)}&limit=1"
        res_adresse = requests.get(url_adresse, timeout=OPENDATA_TIMEOUT)
        res_adresse.raise_for_status()
        features = res_adresse.json().get("features", [])

        if not features:
            raise ValueError("Adresse introuvable")

        coords = features[0]["geometry"]["coordinates"]
        lon, lat = coords[0], coords[1]

        # 2. DVF (Demandes Valeurs Foncières - api.cquest.org)
        url_dvf = f"https://api.cquest.org/dvf?lat={lat}&lon={lon}&dist=250"
        res_dvf = requests.get(url_dvf, timeout=OPENDATA_TIMEOUT)
        res_dvf.raise_for_status()

        mutations = res_dvf.json().get("resultats", [])
        valeurs_foncieres = [
            m["valeur_fonciere"] for m in mutations
            if m.get("valeur_fonciere") and m.get("nature_mutation") == "Vente"
        ]

        if valeurs_foncieres:
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
        return {
            "valeur_estimee": 350000,
            "devise": "EUR",
            "indice_confiance": 40,
            "source": "Moyenne Nationale (Fallback)"
        }


def get_current_bank_rates() -> dict:
    """Taux directeurs bancaires du jour (source interne banque)."""
    return {
        "taux_base_15_ans": 3.10,
        "taux_base_20_ans": 3.45,
        "taux_base_25_ans": 3.65,
        "date_maj": "aujourd'hui"
    }


def calculate_risk_premium(score_climatique: int) -> dict:
    """Grille actuarielle : calcule la décote et la majoration de taux selon le score climatique."""
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
        majoration_taux = -0.10  # Bonification ESG
        exigences = ["Éligible au Prêt Vert"]

    return {
        "decote_valeur_garantie_pct": decote_pourcentage,
        "majoration_taux_interet": majoration_taux,
        "exigences_banque": exigences
    }


def calculate_data_confidence(client_form: dict, georisques_data: dict) -> dict:
    """
    Validation multi-sources des inputs pour TOUS les types de biens.
    
    Sources officielles utilisées :
    - BAN  : Base Adresse Nationale (api-adresse.data.gouv.fr) — validation adresse
    - ADEME: DPE France — vérification surface & année pour bâtiments
    - Logique structurelle — cohérence des champs entre eux (ex: état=Bon + fissures=Importantes)
    """
    confiance = 100
    mismatches = []

    annee_declaree = client_form.get('annee_construction')
    surface_declaree = client_form.get('surface')
    adresse = client_form.get('adresse', '') or ''
    type_bien = client_form.get('type_bien', '').lower()
    is_terrain = 'terrain' in type_bien

    # ── SOURCE 1 : BAN — Base Adresse Nationale (tous types de biens) ──────
    if adresse and adresse != "Adresse inconnue":
        try:
            url_ban = f"https://api-adresse.data.gouv.fr/search/?q={urllib.parse.quote(adresse)}&limit=1"
            res = requests.get(url_ban, timeout=OPENDATA_TIMEOUT)
            res.raise_for_status()
            features = res.json().get("features", [])
            if features:
                score_ban = features[0]["properties"].get("score", 0)
                label_officiel = features[0]["properties"].get("label", "")
                if score_ban < 0.5:
                    confiance -= 25
                    mismatches.append(f"[BAN] Adresse très ambiguë (score={score_ban:.2f}). Adresse officielle suggérée : « {label_officiel} ».")
                elif score_ban < 0.7:
                    confiance -= 10
                    mismatches.append(f"[BAN] Adresse partiellement reconnue. Vérifier : « {label_officiel} ».")
                # score >= 0.7 : adresse valide, aucune pénalité
            else:
                confiance -= 30
                mismatches.append("[BAN] Adresse introuvable dans la Base Adresse Nationale. Risque de dossier fictif.")
        except Exception as e:
            logger.error(f"Erreur API BAN : {e}")
            confiance -= 10
            mismatches.append("[BAN] Service BAN indisponible, localisation non vérifiée.")
    else:
        confiance -= 30
        mismatches.append("[FORMULAIRE] Adresse manquante. Champ obligatoire pour toute analyse bancaire.")

    # ── SOURCE 2 : Code INSEE — format de base (tous types) ─────────────────
    code_insee = str(client_form.get('code_insee', '') or '')
    if code_insee:
        if not (code_insee.isdigit() and len(code_insee) == 5):
            confiance -= 10
            mismatches.append(f"[INSEE] Code INSEE invalide : '{code_insee}'. Format attendu : 5 chiffres (ex: 75056).")
    else:
        confiance -= 5
        mismatches.append("[FORMULAIRE] Code INSEE absent. Recommandé pour la géolocalisation précise.")

    # ── SOURCE 3 : Cohérence Numérique (tous types) ──────────────────────────
    if surface_declaree is not None:
        try:
            s = float(surface_declaree)
            if s <= 0:
                confiance -= 20
                mismatches.append("[FORMULAIRE] Surface nulle ou négative : impossible.")
            elif not is_terrain and s > 50000:
                confiance -= 15
                mismatches.append(f"[FORMULAIRE] Surface bâtie ({s} m²) exceptionnellement grande. Vérification requise.")
            elif is_terrain and s > 1_000_000:
                confiance -= 10
                mismatches.append(f"[FORMULAIRE] Surface terrain ({s} m²) extraordinairement grande. À documenter.")
        except (ValueError, TypeError):
            confiance -= 15
            mismatches.append("[FORMULAIRE] Surface non numérique. Valeur illisible.")

    if not is_terrain and annee_declaree is not None:
        try:
            annee = int(annee_declaree)
            annee_courante = datetime.date.today().year
            if annee < 1500 or annee > annee_courante:
                confiance -= 20
                mismatches.append(f"[FORMULAIRE] Année de construction incohérente ({annee}). Plage valide : 1500–{annee_courante}.")
        except (ValueError, TypeError):
            confiance -= 10
            mismatches.append("[FORMULAIRE] Année de construction non numérique.")

    # ── SOURCE 4 : ADEME DPE — uniquement pour bâtis résidentiels/tertiaires ─
    types_avec_dpe = ['maison', 'appartement', 'immeuble', 'commerce']
    if any(t in type_bien for t in types_avec_dpe) and adresse and adresse != "Adresse inconnue":
        try:
            url_ademe = f"https://data.ademe.fr/data-fair/api/v1/datasets/dpe-france/lines?q={urllib.parse.quote(adresse)}&size=1"
            res_ademe = requests.get(url_ademe, timeout=OPENDATA_TIMEOUT)
            res_ademe.raise_for_status()
            results = res_ademe.json().get("results", [])
            if results:
                bat = results[0]
                annee_dpe = bat.get("annee_construction")
                surface_dpe = bat.get("surface_thermique_lot")
                classe_dpe = bat.get("classe_consommation_energie", "?")

                # Vérification croisée année
                if annee_declaree and annee_dpe:
                    try:
                        if abs(int(annee_declaree) - int(annee_dpe)) > 5:
                            confiance -= 20
                            mismatches.append(f"[ADEME] Année déclarée ({annee_declaree}) vs DPE officiel ({annee_dpe}) : écart > 5 ans.")
                    except (ValueError, TypeError):
                        pass

                # Vérification croisée surface
                if surface_declaree and surface_dpe:
                    try:
                        if float(surface_declaree) > float(surface_dpe) * 1.20:
                            confiance -= 15
                            mismatches.append(f"[ADEME] Surface déclarée ({surface_declaree} m²) supérieure de >20% au DPE ({surface_dpe} m²). Suspicion de surestimation.")
                    except (ValueError, TypeError):
                        pass

                # Classe DPE dégradée
                if classe_dpe in ['F', 'G']:
                    confiance -= 5
                    mismatches.append(f"[ADEME] DPE classe {classe_dpe} (passoire thermique). Fort impact ESG et valeur résiduelle dégradée.")
            else:
                confiance -= 5
                mismatches.append("[ADEME] Aucun DPE enregistré pour cette adresse. Données thermiques non vérifiables.")
        except Exception as e:
            logger.error(f"Erreur ADEME : {e}")
            confiance -= 5
            mismatches.append("[ADEME] API DPE indisponible. Vérification énergétique impossible.")

    # ── SOURCE 5 : Cohérence structurelle bâtiments ──────────────────────────
    if not is_terrain:
        etat = (client_form.get('etat_structure') or '').lower()
        fissures = client_form.get('fissures', 'Non')
        infiltrations = client_form.get('infiltrations', 'Non')
        etat_toiture = (client_form.get('etat_toiture') or '').lower()

        if etat == 'bon' and fissures in ['Importantes']:
            confiance -= 15
            mismatches.append("[STRUCTURE] Incohérence : état déclaré 'Bon' mais fissures 'Importantes'.")
        if etat == 'bon' and infiltrations in ['Oui', 'Majeures']:
            confiance -= 10
            mismatches.append("[STRUCTURE] Incohérence : état déclaré 'Bon' mais infiltrations majeures.")
        if etat == 'bon' and etat_toiture == 'mauvais':
            confiance -= 10
            mismatches.append("[STRUCTURE] Incohérence : état global 'Bon' mais toiture 'Mauvaise'.")

    # ── LOGIQUE TERRAIN ───────────────────────────────────────────────────────
    if is_terrain and annee_declaree:
        confiance -= 10
        mismatches.append("[TERRAIN] Incohérence : année de construction renseignée pour un terrain nu. Vérifier le type de bien.")

    return {
        'indice': max(0, confiance),
        'incoherences_detectees': mismatches
    }


def evaluate_hard_stops(score_climatique: int, client_form: dict) -> list[str]:
    """Détecte les cas de refus automatique bancaire (Hard Stops)."""
    hard_stops = []
    if score_climatique >= 90:
        hard_stops.append('Score climatique critique (≥ 90/100). Financement standard impossible.')
    if client_form.get('fissures', 'Non') == 'Importantes':
        hard_stops.append('Fissures majeures déclarées. Expertise de structure mandatée exigée avant tout octroi.')
    if client_form.get('infiltrations', 'Non') in ['Oui', 'Majeures']:
        hard_stops.append('Infiltrations actives détectées. Risque structurel immédiat — travaux préalables obligatoires.')
    return hard_stops
