"""
Agent Digital Twin — Cerveau de l'analyse IA.

genererAnalyse(donneesRiskEngine, formulaire) → JSON du contrat
testVulnerabilite(lat, lon, adresse, donneesZone) → verdict rapide
projection2050(analyseActuelle, donneesDrias, scenario) → JSON projeté
"""
import json
import time
import logging
import requests
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .prompts import (
        SYSTEM_PROMPT_ANALYSE, USER_PROMPT_ANALYSE_TEMPLATE,
        SYSTEM_PROMPT_VULNERABILITY, USER_PROMPT_VULNERABILITY_TEMPLATE,
        SYSTEM_PROMPT_PROJECTION_2050, USER_PROMPT_PROJECTION_2050_TEMPLATE
    )
    from .fallback import (
        parser_reponse_mistral, valider_champs_obligatoires,
        enrichir_json, generer_fallback
    )
    from .schema import CONTRACT_JSON_SCHEMA, VULNERABILITY_TEST_SCHEMA
except ImportError:
    from prompts import (
        SYSTEM_PROMPT_ANALYSE, USER_PROMPT_ANALYSE_TEMPLATE,
        SYSTEM_PROMPT_VULNERABILITY, USER_PROMPT_VULNERABILITY_TEMPLATE,
        SYSTEM_PROMPT_PROJECTION_2050, USER_PROMPT_PROJECTION_2050_TEMPLATE
    )
    from fallback import (
        parser_reponse_mistral, valider_champs_obligatoires,
        enrichir_json, generer_fallback
    )
    from schema import CONTRACT_JSON_SCHEMA, VULNERABILITY_TEST_SCHEMA

from config import (
    MISTRAL_API_KEY, MISTRAL_API_URL,
    MISTRAL_MODEL_ANALYSE, MISTRAL_MODEL_VULN, MISTRAL_MODEL_PROJECTION,
    TEMPERATURE_ANALYSE, TEMPERATURE_VULN, TEMPERATURE_PROJECTION,
    TIMEOUT_ANALYSE, TIMEOUT_VULN, TIMEOUT_PROJECTION
)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("DigitalTwinAgent")


class DigitalTwinAgent:
    """
    Agent principal du jumeau numérique.
    Orchestre les appels Mistral pour générer les analyses de risques.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or MISTRAL_API_KEY
        if not self.api_key or self.api_key == "VOTRE_CLE_API_MISTRAL_ICI":
            logger.warning("⚠️  Clé API Mistral non configurée !")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
        logger.info("✅ DigitalTwinAgent initialisé")

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTHODE PRINCIPALE : genererAnalyse
    # ──────────────────────────────────────────────────────────────────────────
    def genererAnalyse(
        self,
        donneesRiskEngine: Dict[str, Any],
        formulaire: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fonction principale : prend les données brutes du risk engine + formulaire client
        et retourne le JSON complet du contrat Digital Twin.

        Args:
            donneesRiskEngine: Données consolidées de BDNB/Géorisques/IGN/Open-Meteo/CATNAT/DVF/DRIAS
            formulaire: Formulaire client (adresse, type de bien, surface, etc.)

        Returns:
            Dict: JSON du contrat Digital Twin
        """
        logger.info(f"🚀 Démarrage analyse pour : {formulaire.get('adresse', 'adresse inconnue')}")
        debut = time.time()

        # 1. Préparer le prompt utilisateur
        user_prompt = USER_PROMPT_ANALYSE_TEMPLATE.format(
            donnees_risk_engine=json.dumps(donneesRiskEngine, ensure_ascii=False, indent=2),
            formulaire_client=json.dumps(formulaire, ensure_ascii=False, indent=2)
        )

        # 2. Appel Mistral
        texte_brut = self._appeler_mistral(
            system_prompt=SYSTEM_PROMPT_ANALYSE,
            user_prompt=user_prompt,
            model=MISTRAL_MODEL_ANALYSE,
            temperature=TEMPERATURE_ANALYSE,
            timeout=TIMEOUT_ANALYSE
        )

        if texte_brut is None:
            logger.error("❌ Échec appel Mistral")
            return generer_fallback(CONTRACT_JSON_SCHEMA)

        # 3. Parser le JSON
        json_dict, est_valide = parser_reponse_mistral(texte_brut, CONTRACT_JSON_SCHEMA)

        # 4. Enrichir et valider
        json_dict = enrichir_json(json_dict)
        est_coherent, erreurs = valider_champs_obligatoires(json_dict)

        if not est_coherent:
            logger.warning(f"⚠️  JSON invalide ({len(erreurs)} erreurs) : {erreurs[:3]}")
            json_dict["_validations_warnings"] = erreurs

        # 5. Ajouter les métadonnées de performance
        duree = round(time.time() - debut, 2)
        json_dict.setdefault("_performance", {})
        json_dict["_performance"]["duree_analyse_s"] = duree
        json_dict["_performance"]["json_valide"] = est_valide and est_coherent
        json_dict["_performance"]["model_utilise"] = MISTRAL_MODEL_ANALYSE

        logger.info(f"✅ Analyse terminée en {duree}s (valide={est_valide and est_coherent})")
        return json_dict

    # ──────────────────────────────────────────────────────────────────────────────
    # MÉTHODE UNIFIÉE : genererDepuisJSON (nouveau format d'entrée)
    # ──────────────────────────────────────────────────────────────────────────────
    def genererDepuisJSON(
        self,
        input_json: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Point d'entrée principal pour le nouveau format unifigé.
        Accepte directement le JSON avec user_data + agent_data + step7.

        Args:
            input_json: JSON unifié du risk engine
              {
                "user_data": {...},   # Données déclaratives du bien
                "agent_data": {...},  # Données géocodées + scores BDNB/Géorisques
                "step7": {...}        # Scores déterministes par péril + règles
              }

        Returns:
            Dict: JSON complet avec risques_actuels + risques_futurs_2050
        """
        try:
            from .input_adapter import adapter_input
        except ImportError:
            from input_adapter import adapter_input

        logger.info("=" * 60)
        logger.info("[DigitalTwinAgent] genererDepuisJSON()")
        logger.info(f"  Adresse : {input_json.get('user_data', {}).get('adresse', '?')}")
        logger.info("=" * 60)

        # Adapter le format d'entrée
        donnees_risk_engine, formulaire = adapter_input(input_json)

        # Lancer l'analyse
        resultat = self.genererAnalyse(donnees_risk_engine, formulaire)

        # Ajouter les métadonnées d'entrée pour traçabilité
        resultat["_input_meta"] = {
            "version_input"    : input_json.get("version", "1.0"),
            "generated_at"     : input_json.get("generated_at", ""),
            "format"           : "unified_v1 (user_data+agent_data+step7)",
            "score_engine_base": donnees_risk_engine.get("scores_risk_engine", {})
        }

        return resultat

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTHODE RAPIDE : testVulnerabilite (pour clic sur la carte)
    # ──────────────────────────────────────────────────────────────────────────
    def testVulnerabilite(
        self,
        lat: float,
        lon: float,
        adresse: str = "",
        donneesZone: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Test de vulnérabilité rapide déclenché au clic sur une zone.
        Retourne un verdict + explication en quelques secondes.

        Args:
            lat: Latitude
            lon: Longitude
            adresse: Adresse approximative
            donneesZone: Données de contexte disponibles pour la zone

        Returns:
            Dict: Verdict de vulnérabilité
        """
        logger.info(f"⚡ Test vulnérabilité : ({lat}, {lon})")
        debut = time.time()

        user_prompt = USER_PROMPT_VULNERABILITY_TEMPLATE.format(
            lat=lat, lon=lon,
            adresse=adresse or "Non renseignée",
            donnees_zone=json.dumps(donneesZone or {}, ensure_ascii=False, indent=2)
        )

        texte_brut = self._appeler_mistral(
            system_prompt=SYSTEM_PROMPT_VULNERABILITY,
            user_prompt=user_prompt,
            model=MISTRAL_MODEL_VULN,
            temperature=TEMPERATURE_VULN,
            timeout=TIMEOUT_VULN
        )

        if texte_brut is None:
            return {
                "verdict": "VIGILANCE",
                "score_risque": 50,
                "risques_identifies": [],
                "explication": "Service temporairement indisponible.",
                "action_immediate": "Relancer l'analyse.",
                "_erreur": "Appel Mistral échoué"
            }

        json_dict, _ = parser_reponse_mistral(texte_brut, VULNERABILITY_TEST_SCHEMA)
        json_dict["delai_reponse_ms"] = round((time.time() - debut) * 1000)

        logger.info(f"⚡ Vulnérabilité : {json_dict.get('verdict', '?')} en {json_dict['delai_reponse_ms']}ms")
        return json_dict

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTHODE 2050 : projection climatique
    # ──────────────────────────────────────────────────────────────────────────
    def projection2050(
        self,
        analyseActuelle: Dict[str, Any],
        donneesDrias: Optional[Dict] = None,
        scenario: str = "rcp85"
    ) -> Dict[str, Any]:
        """
        Génère la version projetée 2050 du JSON avec risques aggravés.

        Args:
            analyseActuelle: JSON de l'analyse actuelle (retour de genererAnalyse)
            donneesDrias: Données climatiques DRIAS (températures, précipitations projetées)
            scenario: "rcp45" (modéré) ou "rcp85" (pessimiste)

        Returns:
            Dict: JSON projeté 2050
        """
        logger.info(f"🌡️  Projection 2050 (scénario {scenario.upper()})")
        debut = time.time()

        user_prompt = USER_PROMPT_PROJECTION_2050_TEMPLATE.format(
            analyse_actuelle=json.dumps(analyseActuelle, ensure_ascii=False, indent=2),
            donnees_drias=json.dumps(donneesDrias or {}, ensure_ascii=False, indent=2),
            scenario=scenario.upper()
        )

        texte_brut = self._appeler_mistral(
            system_prompt=SYSTEM_PROMPT_PROJECTION_2050,
            user_prompt=user_prompt,
            model=MISTRAL_MODEL_PROJECTION,
            temperature=TEMPERATURE_PROJECTION,
            timeout=TIMEOUT_PROJECTION
        )

        if texte_brut is None:
            logger.error("❌ Projection 2050 : appel Mistral échoué")
            return {**analyseActuelle, "_projection_2050": "ECHEC", "_scenario": scenario}

        json_dict, est_valide = parser_reponse_mistral(texte_brut, CONTRACT_JSON_SCHEMA)
        json_dict = enrichir_json(json_dict)

        # Marqueurs de projection
        json_dict.setdefault("meta", {})["horizon_analyse"] = "2050"
        json_dict.setdefault("meta", {})["scenario_climatique"] = scenario
        json_dict["_performance"] = {
            "duree_projection_s": round(time.time() - debut, 2),
            "json_valide": est_valide,
            "scenario": scenario
        }

        logger.info(f"✅ Projection 2050 générée (valide={est_valide})")
        return json_dict

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTHODE INTERNE : appel API Mistral
    # ──────────────────────────────────────────────────────────────────────────
    def _appeler_mistral(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        timeout: int
    ) -> Optional[str]:
        """
        Appel à l'API Mistral avec retry automatique.
        Retourne le texte brut de la réponse ou None en cas d'échec.
        """
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "max_tokens": 8192,
            "response_format": {"type": "json_object"}  # Force JSON mode
        }

        max_retries = 3
        for tentative in range(1, max_retries + 1):
            try:
                logger.info(f"📡 Appel Mistral ({model}) - tentative {tentative}/{max_retries}")
                response = self.session.post(
                    MISTRAL_API_URL,
                    json=payload,
                    timeout=timeout
                )

                if response.status_code == 200:
                    data = response.json()
                    contenu = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {})
                    logger.info(
                        f"✅ Réponse reçue | tokens: {tokens.get('total_tokens', '?')} | "
                        f"prompt: {tokens.get('prompt_tokens', '?')} | "
                        f"completion: {tokens.get('completion_tokens', '?')}"
                    )
                    return contenu

                elif response.status_code == 429:
                    # Rate limit
                    wait = 2 ** tentative
                    logger.warning(f"⏳ Rate limit - attente {wait}s")
                    time.sleep(wait)
                    continue

                elif response.status_code in [500, 502, 503, 504]:
                    # Erreur serveur temporaire
                    wait = 2 ** tentative
                    logger.warning(f"🔄 Erreur serveur {response.status_code} - retry dans {wait}s")
                    time.sleep(wait)
                    continue

                else:
                    logger.error(
                        f"❌ Erreur API Mistral {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    return None

            except requests.exceptions.Timeout:
                logger.error(f"⏰ Timeout après {timeout}s (tentative {tentative})")
                if tentative < max_retries:
                    time.sleep(2)
                    continue

            except requests.exceptions.ConnectionError as e:
                logger.error(f"🌐 Erreur connexion : {e}")
                return None

            except Exception as e:
                logger.error(f"💥 Erreur inattendue : {e}")
                return None

        logger.error(f"❌ Toutes les tentatives échouées ({max_retries})")
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # MÉTHODE UTILITAIRE : analyse complète (main + 2050)
    # ──────────────────────────────────────────────────────────────────────────
    def analyseComplete(
        self,
        donneesRiskEngine: Dict[str, Any],
        formulaire: Dict[str, Any],
        donneesDrias: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Lance l'analyse principale + projection 2050 (RCP 4.5 et RCP 8.5).
        Retourne un dict avec les 3 versions.
        """
        logger.info("🔬 Lancement analyse complète (présent + 2050)")

        # Analyse principale
        analyse = self.genererAnalyse(donneesRiskEngine, formulaire)

        # Projections 2050
        projection_rcp45 = self.projection2050(analyse, donneesDrias, scenario="rcp45")
        projection_rcp85 = self.projection2050(analyse, donneesDrias, scenario="rcp85")

        return {
            "analyse_actuelle": analyse,
            "projection_2050_rcp45": projection_rcp45,
            "projection_2050_rcp85": projection_rcp85,
            "_meta_complete": {
                "timestamp": datetime.now().isoformat(),
                "adresse": formulaire.get("adresse", "Inconnue"),
                "nb_risques_evalues": len(analyse.get("risques_actuels", {}))
            }
        }
