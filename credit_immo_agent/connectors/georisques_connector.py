"""
Connecteur Géorisques (BRGM / Ministère de la Transition écologique).

API officielle : https://www.georisques.gouv.fr/doc-api

Endpoints réels utilisés (vérifiés par recherche, exemples publiés par
l'équipe Géorisques et des utilisateurs sur le forum data.gouv.fr) :
    https://georisques.gouv.fr/api/v1/rga?latlon={lon},{lat}
    https://georisques.gouv.fr/api/v1/gaspar/catnat/?longitude={lon}&latitude={lat}&rayon={metres}
    https://georisques.gouv.fr/api/v1/resultats_rapport_risque?latlon={lon},{lat}

ATTENTION - à savoir avant d'utiliser ce connecteur en production :
- Un dispositif anti-robots a déjà bloqué certains clients non-navigateur par
  le passé (rapporté par des utilisateurs sur le forum officiel data.gouv.fr,
  fin 2024). Si vous recevez des erreurs 403/blocage, contactez l'équipe
  Géorisques via data.gouv.fr pour une autorisation d'accès automatisé.
- L'endpoint resultats_rapport_risque peut être lent (plusieurs secondes).
- Toujours vérifier la doc à jour sur georisques.gouv.fr/doc-api avant un
  déploiement, ce connecteur peut nécessiter des ajustements si l'API évolue.
"""

import json
import urllib.request
import urllib.parse
from typing import Optional, List, Dict

BASE_URL = "https://georisques.gouv.fr/api/v1"
TIMEOUT_SECONDES = 15


class GeorisquesIndisponible(Exception):
    """Levée quand l'API Géorisques ne répond pas ou renvoie une erreur."""


def _appeler_api(chemin: str, params: Dict[str, str]) -> dict:
    url = f"{BASE_URL}/{chemin}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "agent-suivi-credit-immo/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDES) as reponse:
            return json.loads(reponse.read().decode("utf-8"))
    except Exception as e:
        raise GeorisquesIndisponible(f"Échec de l'appel à l'API Géorisques ({url}) : {e}") from e


def exposition_rga(lat: float, lon: float) -> dict:
    """
    Retourne l'exposition au retrait-gonflement des argiles (RGA) pour un point donné.
    Exemple de réponse réelle observée : {"codeExposition": "2", "exposition": "Exposition moyenne"}
    """
    data = _appeler_api("rga", {"latlon": f"{lon},{lat}"})
    return {
        "code_exposition": data.get("codeExposition"),
        "exposition": data.get("exposition"),
    }


def evenements_catnat(lat: float, lon: float, rayon_metres: int = 1000) -> List[dict]:
    """
    Retourne la liste des arrêtés de catastrophe naturelle (CatNat) historiques
    dans un rayon donné autour du point (inondation, mouvement de terrain, etc.).
    """
    data = _appeler_api(
        "gaspar/catnat/",
        {"longitude": str(lon), "latitude": str(lat), "rayon": str(rayon_metres)},
    )
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    return []


def rapport_risque_complet(lat: float, lon: float) -> dict:
    """
    Retourne le rapport de risque complet (tous aléas confondus) pour un point.
    Peut être lent (plusieurs secondes) selon la documentation Géorisques.
    """
    return _appeler_api("resultats_rapport_risque", {"latlon": f"{lon},{lat}"})


def detecter_nouvelle_alerte(
    lat: float,
    lon: float,
    code_exposition_rga_reference: Optional[str] = None,
    nb_catnat_reference: Optional[int] = None,
) -> dict:
    """
    Compare l'état actuel du risque à un état de référence (par exemple celui
    capturé à l'octroi du crédit) et signale toute dégradation détectée.
    """
    alertes = []

    rga = exposition_rga(lat, lon)
    if code_exposition_rga_reference is not None and rga["code_exposition"] != code_exposition_rga_reference:
        alertes.append(
            f"Exposition RGA modifiée : {code_exposition_rga_reference} -> {rga['code_exposition']} ({rga['exposition']})"
        )

    catnat = evenements_catnat(lat, lon)
    if nb_catnat_reference is not None and len(catnat) > nb_catnat_reference:
        alertes.append(
            f"Nouveaux arrêtés CatNat détectés : {nb_catnat_reference} -> {len(catnat)}"
        )

    return {
        "exposition_rga_actuelle": rga,
        "nb_catnat_actuel": len(catnat),
        "alertes": alertes,
    }
