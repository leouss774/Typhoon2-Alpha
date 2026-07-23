"""
Parsing robuste et fallback pour les réponses JSON de Mistral.
Gère les cas où Mistral envoie du JSON mal formé.
"""
import json
import re
import logging
from typing import Any, Optional, Dict, Tuple

logger = logging.getLogger(__name__)


# ─── Extraction JSON depuis texte brut ────────────────────────────────────────
def extraire_json(texte: str) -> Optional[str]:
    """
    Extrait le premier bloc JSON valide depuis un texte potentiellement pollué.
    Stratégies tentées dans l'ordre :
    1. Parsing direct
    2. Extraction entre ``` json ... ```
    3. Extraction entre la première { et la dernière }
    4. Regex agressive pour JSON imbriqué
    """
    texte = texte.strip()

    # Stratégie 1 : parsing direct
    try:
        json.loads(texte)
        return texte
    except json.JSONDecodeError:
        pass

    # Stratégie 2 : extraction code fence markdown
    patterns_fence = [
        r"```json\s*([\s\S]+?)\s*```",
        r"```\s*([\s\S]+?)\s*```",
        r"`([\s\S]+?)`"
    ]
    for pattern in patterns_fence:
        match = re.search(pattern, texte, re.DOTALL)
        if match:
            candidat = match.group(1).strip()
            try:
                json.loads(candidat)
                return candidat
            except json.JSONDecodeError:
                continue

    # Stratégie 3 : extraction entre { et }
    debut = texte.find('{')
    if debut != -1:
        # Chercher la fermeture correspondante
        profondeur = 0
        for i, char in enumerate(texte[debut:], debut):
            if char == '{':
                profondeur += 1
            elif char == '}':
                profondeur -= 1
                if profondeur == 0:
                    candidat = texte[debut:i+1]
                    try:
                        json.loads(candidat)
                        return candidat
                    except json.JSONDecodeError:
                        break

    # Stratégie 4 : nettoyage agressif
    candidat = nettoyer_json(texte)
    if candidat:
        try:
            json.loads(candidat)
            return candidat
        except json.JSONDecodeError:
            pass

    return None


def nettoyer_json(texte: str) -> Optional[str]:
    """Nettoyage agressif du JSON : supprime commentaires, virgules traînantes, etc."""
    # Extraire contenu entre { et }
    debut = texte.find('{')
    fin = texte.rfind('}')
    if debut == -1 or fin == -1:
        return None

    candidat = texte[debut:fin+1]

    # Supprimer commentaires // et /* */
    candidat = re.sub(r'//[^\n]*', '', candidat)
    candidat = re.sub(r'/\*[\s\S]*?\*/', '', candidat)

    # Supprimer virgules traînantes avant } ou ]
    candidat = re.sub(r',\s*([}\]])', r'\1', candidat)

    # Corriger les booléens Python → JSON
    candidat = candidat.replace('True', 'true').replace('False', 'false').replace('None', 'null')

    # Corriger les strings avec apostrophes simples → double quotes
    # (prudent : seulement pour les clés)
    candidat = re.sub(r"'([^']+)':", r'"\1":', candidat)

    return candidat


# ─── Parsing avec fallback complet ────────────────────────────────────────────
def parser_reponse_mistral(texte_brut: str, schema_defaut: Dict) -> Tuple[Dict, bool]:
    """
    Parse la réponse de Mistral et retourne (json_dict, est_valide).
    Si parsing impossible → retourne le JSON de fallback avec est_valide=False.
    """
    json_str = extraire_json(texte_brut)

    if json_str:
        try:
            resultat = json.loads(json_str)
            logger.info("✅ JSON parsé avec succès")
            return resultat, True
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️  Échec parsing JSON extrait : {e}")

    logger.error("❌ Impossible de parser le JSON Mistral → utilisation du fallback")
    return generer_fallback(schema_defaut, texte_brut), False


def generer_fallback(schema_defaut: Dict, texte_brut: str = "") -> Dict:
    """
    Génère un JSON de fallback minimal mais valide quand Mistral échoue.
    Inclut le texte brut dans un champ d'erreur pour diagnostic.
    """
    from datetime import datetime

    return {
        "_erreur": {
            "type": "PARSING_FAILED",
            "message": "Mistral a retourné un JSON mal formé. Fallback activé.",
            "texte_brut_tronque": texte_brut[:500] if texte_brut else "",
            "timestamp": datetime.now().isoformat()
        },
        "meta": {
            "version": "2.0-fallback",
            "date_analyse": datetime.now().isoformat(),
            "adresse": "Inconnue",
            "coordonnees": {"lat": 0.0, "lon": 0.0},
            "horizon_analyse": "2024-2050",
            "sources_donnees": []
        },
        "score_global": {
            "note": 50,
            "classe": "C",
            "interpretation": "Analyse non disponible - fallback activé",
            "score_resilience": 50,
            "score_exposition": 50,
            "score_vulnerabilite": 50
        },
        "risques_actuels": {
            risque: {
                "niveau": "modere",
                "score": 50,
                "present_zone_ppr": False,
                "explication": "Données non disponibles",
                "source": "Inconnue"
            }
            for risque in ["inondation", "seisme", "retrait_gonflement_argiles",
                           "incendie_foret", "mouvement_terrain", "radon",
                           "tempete", "chaleur_extreme", "pollution_sols", "submersion_marine"]
        },
        "recommandations": {
            "urgentes": [],
            "court_terme": [],
            "moyen_terme": [],
            "long_terme_2050": []
        }
    }


def valider_champs_obligatoires(json_dict: Dict) -> Tuple[bool, list]:
    """
    Vérifie que les champs obligatoires sont présents et cohérents.
    Retourne (est_valide, liste_erreurs).
    """
    erreurs = []
    champs_requis = ["meta", "bien", "risques_actuels", "risques_futurs_2050",
                     "score_global", "recommandations", "simulation_periode"]

    for champ in champs_requis:
        if champ not in json_dict:
            erreurs.append(f"Champ obligatoire manquant : {champ}")

    # Valider le score global
    if "score_global" in json_dict:
        sg = json_dict["score_global"]
        if "note" in sg:
            note = sg.get("note", 50)
            if not isinstance(note, (int, float)) or note < 0 or note > 100:
                erreurs.append(f"score_global.note invalide : {note}")
        if "classe" in sg:
            if sg["classe"] not in ["A", "B", "C", "D", "E", "F"]:
                erreurs.append(f"score_global.classe invalide : {sg['classe']}")

    # Valider les risques
    niveaux_valides = {"negligeable", "faible", "modere", "eleve", "tres_eleve"}
    if "risques_actuels" in json_dict:
        for nom_risque, risque in json_dict["risques_actuels"].items():
            if isinstance(risque, dict):
                niveau = risque.get("niveau", "")
                if niveau not in niveaux_valides:
                    erreurs.append(f"Niveau invalide pour {nom_risque} : {niveau}")

    return len(erreurs) == 0, erreurs


def enrichir_json(json_dict: Dict) -> Dict:
    """
    Enrichit le JSON avec des champs calculés manquants pour assurer la cohérence.
    """
    from datetime import datetime

    # Assurer la présence de meta
    if "meta" not in json_dict:
        json_dict["meta"] = {}
    if "date_analyse" not in json_dict["meta"]:
        json_dict["meta"]["date_analyse"] = datetime.now().isoformat()
    if "version" not in json_dict["meta"]:
        json_dict["meta"]["version"] = "2.0"

    # Calculer score global si absent
    if "score_global" not in json_dict and "risques_actuels" in json_dict:
        scores = [
            r.get("score", 0)
            for r in json_dict["risques_actuels"].values()
            if isinstance(r, dict)
        ]
        if scores:
            note_moyenne = sum(scores) / len(scores)
            json_dict["score_global"] = {
                "note": round(note_moyenne, 1),
                "classe": _note_vers_classe(note_moyenne),
                "interpretation": "Score calculé automatiquement",
                "score_resilience": max(0, 100 - note_moyenne),
                "score_exposition": note_moyenne,
                "score_vulnerabilite": note_moyenne
            }

    return json_dict


def _note_vers_classe(note: float) -> str:
    if note <= 20: return "A"
    if note <= 35: return "B"
    if note <= 50: return "C"
    if note <= 65: return "D"
    if note <= 80: return "E"
    return "F"
