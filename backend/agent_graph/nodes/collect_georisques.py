"""Noeud 1 : Collecte des donnees Georisques.

Appelle risk_score_pipeline.analyser_adresse() pour obtenir
les donnees georisques, IGN, Hub'Eau, OSM, etc.
Stocke le resultat dans state.georisques_data.

Note : le sys.path est deja configure par graph.py et orchestrator.py
"""

from __future__ import annotations

import logging
import signal
from contextlib import contextmanager

from agent_graph.state import TyphoonState

logger = logging.getLogger(__name__)

# Import conditionnel du pipeline de collecte
try:
    from agents.recommandation.risk_score_pipeline import analyser_adresse
    HAS_PIPELINE = True
    logger.info("Pipeline Georisques disponible")
except ImportError:
    HAS_PIPELINE = False
    logger.warning("Pipeline Georisques non disponible - utilisation de donnees simulees")


@contextmanager
def timeout(seconds: int):
    """Context manager pour timeout (Unix uniquement)."""
    if hasattr(signal, "SIGALRM"):
        def handler(signum, frame):
            raise TimeoutError(f"Operation timeout apres {seconds}s")
        signal.signal(signal.SIGALRM, handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
    else:
        # Windows : pas de SIGALRM, on execute sans timeout
        yield


def collect_georisques_node(state: TyphoonState) -> dict:
    """Collecte les donnees Georisques a partir de l'adresse dans le formulaire.

    Entree :  state.client_form["adresse"]
    Sortie :  state.georisques_data (dict)
              state.collect_error (str ou None)
    """
    adresse = state.client_form.get("adresse", "")

    if not adresse:
        return {
            "georisques_data": {},
            "collect_error": "Aucune adresse fournie dans le formulaire",
            "next_node": "generate_recommandations",
        }

    if HAS_PIPELINE:
        try:
            logger.info(f"Collecte Georisques pour : {adresse}")
            data = analyser_adresse(adresse)
            logger.info("Donnees collectees avec succes")

            georisques = data.get("georisques", {})
            ign = data.get("ign", {})
            osm = data.get("osm", {})

            return {
                "georisques_data": {
                    "brut": data,
                    "georisques": georisques,
                    "coordonnees": data.get("coordonnees", {}),
                    "code_insee": data.get("code_insee", ""),
                    "altitude": ign.get("altitude", {}),
                    "osm_proximite": osm.get("elements_naturels_proches", {}),
                },
                "next_node": "generate_recommandations",
            }
        except Exception as e:
            logger.error(f"Erreur collecte Georisques : {e}")
            return {
                "georisques_data": {},
                "collect_error": str(e),
                "next_node": "generate_recommandations",
            }
    else:
        logger.info("Mode simulation - pas de pipeline Georisques disponible")
        return {
            "georisques_data": {
                "brut": {}, "georisques": {},
                "coordonnees": {"latitude": 0, "longitude": 0},
                "code_insee": "", "altitude": {}, "osm_proximite": {},
            },
            "collect_error": None,
            "next_node": "generate_recommandations",
        }
