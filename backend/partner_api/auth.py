"""
Authentification par cle API de la Typhoon Partner API.

Une cle par partenaire (PARTNER_API_KEYS="groupA:xxx,groupB:yyy" dans
`.env`), envoyee dans le header `X-API-Key`. Verification simple par
egalite de chaine (pas de hachage/rotation pour l'instant : le volume de
cles et le contexte -- quelques groupes partenaires internes -- ne le
justifient pas encore).
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.core.logging import get_logger
from partner_api.config import partner_settings

logger = get_logger(__name__)


def _parse_keys(raw: str) -> dict[str, str]:
    """"nom1:cle1,nom2:cle2" -> {"cle1": "nom1", "cle2": "nom2"}."""
    keys: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        name, _, key = entry.partition(":")
        name, key = name.strip(), key.strip()
        if name and key:
            keys[key] = name
    return keys


_KEYS_BY_VALUE = _parse_keys(partner_settings.partner_api_keys)

if not _KEYS_BY_VALUE:
    logger.warning(
        "partner_api.auth -- PARTNER_API_KEYS vide : toutes les requetes seront refusees (401/503). "
        "Ajoutez PARTNER_API_KEYS=nom:cle dans backend/.env."
    )
else:
    logger.info("partner_api.auth -- %d cle(s) partenaire chargee(s) : %s", len(_KEYS_BY_VALUE), sorted(_KEYS_BY_VALUE.values()))


async def require_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Dependance FastAPI : valide le header X-API-Key, retourne le nom du partenaire.

    Leve 401 si la cle est absente/invalide, 503 si aucune cle n'est
    configuree cote serveur (erreur de deploiement, pas une erreur client).
    """
    if not _KEYS_BY_VALUE:
        raise HTTPException(status_code=503, detail="Aucune cle API partenaire configuree cote serveur.")
    if not x_api_key or x_api_key not in _KEYS_BY_VALUE:
        raise HTTPException(status_code=401, detail="Cle API invalide ou manquante (header X-API-Key requis).")
    return _KEYS_BY_VALUE[x_api_key]
