"""
Connecteur Mistral Vision pour l'analyse de plans d'usine.

Utilise l'API vision de Mistral pour détecter automatiquement les zones
et équipements à partir d'images de plans industriels.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

from mistralai.client import Mistral
from mistralai.client.models.imageurl import ImageURL

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

VISION_MODEL = "pixtral-12b-2409"  # Modèle vision de Mistral
REQUEST_TIMEOUT_MS = 120_000  # 2 minutes pour les images
THROTTLE_SECONDS = 0.3

_client: Mistral | None = None


def get_vision_client() -> Mistral:
    """Retourne le client Mistral configuré pour la vision."""
    global _client
    if _client is None:
        if not settings.mistral_api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY manquant. Configurez-le dans backend/.env"
            )
        _client = Mistral(api_key=settings.mistral_api_key, timeout_ms=REQUEST_TIMEOUT_MS)
    return _client


def _encode_image_to_base64(image_path: str | Path) -> str:
    """Encode une image en base64 pour l'API Mistral."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _encode_image_bytes(image_bytes: bytes) -> str:
    """Encode des bytes d'image en base64."""
    return base64.b64encode(image_bytes).decode("utf-8")


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "rate_limited" in msg or "rate limit" in msg


def _backoff_seconds(e: Exception, attempt: int) -> float:
    if _is_rate_limit_error(e):
        return min(60, 20 * (attempt + 1))
    return 5 * (attempt + 1)


def analyze_plan_image(
    image_path: str | Path | None = None,
    image_base64: str | None = None,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Analyse un plan d'usine via Mistral Vision et extrait les zones et équipements.

    Parameters
    ----------
    image_path : str | Path | None
        Chemin vers le fichier image (JPG, PNG, etc.)
    image_base64 : str | None
        Image encodée en base64 (alternative à image_path)
    max_retries : int
        Nombre de tentatives en cas d'erreur

    Returns
    -------
    dict
        {
            "zones": [...],
            "equipements": [...],
            "nom_usine": str,
            "confiance_globale": float
        }
    """
    if not image_path and not image_base64:
        raise ValueError("image_path ou image_base64 requis")

    # Préparer l'image
    if image_path:
        base64_image = _encode_image_to_base64(image_path)
        image_url = f"data:image/jpeg;base64,{base64_image}"
    else:
        image_url = f"data:image/jpeg;base64,{image_base64}"

    # Prompt pour l'analyse du plan
    system_prompt = """Tu es un expert en analyse de plans d'usines industrielles.
Ta mission est d'analyser l'image d'un plan d'usine et d'extraire toutes les informations structurées.

Règles strictes :
1. Identifie TOUTES les zones visibles (production, stockage, bureaux, cuves, expédition, etc.)
2. Identifie TOUS les équipements industriels visibles (machines, fours, réservoirs, pompes, etc.)
3. Estime les surfaces des zones en m² si l'échelle est visible
4. Estime la valeur de remplacement des équipements en EUR
5. Identifie les équipements critiques pour la production
6. Identifie les équipements contenant des matières dangereuses

Retourne UNIQUEMENT un JSON valide (pas de markdown, pas de texte avant/après) avec cette structure :
{
  "nom_usine": "Nom détecté ou 'Usine'",
  "confiance_globale": 0.85,
  "zones": [
    {
      "nom": "Zone de production",
      "type": "production",
      "surface_m2": 2500,
      "confiance": 0.95
    }
  ],
  "equipements": [
    {
      "nom": "Ligne de production 1",
      "type": "ligne_production",
      "zone": "Zone de production",
      "valeur_remplacement_eur": 800000,
      "matieres_dangereuses": false,
      "critique_production": true,
      "confiance": 0.92
    }
  ]
}

Types de zones possibles : production, stockage, bureaux, cuves, expedition, laboratoire, maintenance
Types d'équipements possibles : machine_outil, ligne_production, four, compresseur, groupe_froid, pompe, chaudiere, reservoir, cuve, silo, pont_roulant, robot, automate, serveur, laboratoire, autre

Sois précis et conservateur : si tu n'es pas sûr, mets une confiance basse (< 0.5)."""

    user_prompt = """Analyse ce plan d'usine et extrait toutes les zones et équipements industriels visibles.
Retourne un JSON valide avec la structure demandée."""

    client = get_vision_client()
    last_err: Exception | None = None

    for attempt in range(max_retries):
        try:
            logger.info(
                "mistral_vision -- analyse du plan (tentative %d/%d)",
                attempt + 1,
                max_retries,
            )

            response = client.chat.complete(
                model=VISION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": ImageURL(url=image_url),
                            },
                        ],
                    },
                ],
                temperature=0.2,
                max_tokens=2000,
            )

            content = response.choices[0].message.content
            time.sleep(THROTTLE_SECONDS)

            # Extraire le JSON de la réponse
            if isinstance(content, list):
                text_parts = []
                for chunk in content:
                    text = getattr(chunk, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
                    elif hasattr(text, "text"):
                        text_parts.append(str(text.text))
                content = "".join(text_parts)

            # Nettoyer le contenu (enlever markdown si présent)
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            result = json.loads(content)

            # Validation et normalisation
            result = _normalize_result(result)

            logger.info(
                "mistral_vision -- analyse réussie: %d zones, %d équipements",
                len(result.get("zones", [])),
                len(result.get("equipements", [])),
            )

            return result

        except Exception as e:
            last_err = e
            wait = _backoff_seconds(e, attempt)
            logger.warning(
                "mistral_vision -- erreur tentative %d/%d: %s (attente %.0fs)",
                attempt + 1,
                max_retries,
                e,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Échec analyse Mistral Vision après {max_retries} tentatives: {last_err}"
    )


def _normalize_result(result: dict[str, Any]) -> dict[str, Any]:
    """Normalise et valide le résultat de l'analyse."""
    # Valeurs par défaut
    normalized = {
        "nom_usine": result.get("nom_usine", "Usine"),
        "confiance_globale": float(result.get("confiance_globale", 0.7)),
        "zones": [],
        "equipements": [],
    }

    # Normaliser les zones
    zones_raw = result.get("zones", [])
    if isinstance(zones_raw, list):
        for i, zone in enumerate(zones_raw):
            if not isinstance(zone, dict):
                continue
            normalized_zone = {
                "id": zone.get("id", f"z_vision_{i}"),
                "nom": zone.get("nom", f"Zone {i + 1}"),
                "type": zone.get("type", "production"),
                "surface_m2": zone.get("surface_m2"),
                "confiance": float(zone.get("confiance", 0.7)),
            }
            # Valider le type
            valid_types = {
                "production",
                "stockage",
                "bureaux",
                "cuves",
                "expedition",
                "laboratoire",
                "maintenance",
            }
            if normalized_zone["type"] not in valid_types:
                normalized_zone["type"] = "production"
            normalized["zones"].append(normalized_zone)

    # Normaliser les équipements
    equipements_raw = result.get("equipements", [])
    if isinstance(equipements_raw, list):
        for i, equip in enumerate(equipements_raw):
            if not isinstance(equip, dict):
                continue
            normalized_equip = {
                "id": equip.get("id", f"e_vision_{i}"),
                "nom": equip.get("nom", f"Équipement {i + 1}"),
                "type": equip.get("type", "autre"),
                "zone": equip.get("zone", normalized["zones"][0]["nom"] if normalized["zones"] else "Zone 1"),
                "valeur_remplacement_eur": equip.get("valeur_remplacement_eur"),
                "matieres_dangereuses": bool(equip.get("matieres_dangereuses", False)),
                "critique_production": bool(equip.get("critique_production", False)),
                "confiance": float(equip.get("confiance", 0.7)),
            }
            # Valider le type
            valid_types = {
                "machine_outil",
                "ligne_production",
                "four",
                "compresseur",
                "groupe_froid",
                "pompe",
                "chaudiere",
                "reservoir",
                "cuve",
                "silo",
                "pont_roulant",
                "robot",
                "automate",
                "serveur",
                "laboratoire",
                "autre",
            }
            if normalized_equip["type"] not in valid_types:
                normalized_equip["type"] = "autre"
            normalized["equipements"].append(normalized_equip)

    return normalized