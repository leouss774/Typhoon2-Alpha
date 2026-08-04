"""
Typhoon Partner API — entrypoint FastAPI dedie aux projets tiers.

Service separe de `app.main:app` (le backend interne, consomme par le
front jumeau numerique) : meme moteur (agents/connecteurs sous `app.`),
mais un contrat de reponse different (score de risque + recommandations,
pas de geometrie 3D) et un cycle de vie independant (un changement sur
/diagnostic ne doit pas casser cette API, et inversement).

Lancement (depuis backend/, meme racine que l'API interne pour que
`import app.*` et `import partner_api.*` resolvent tous les deux) :
    cd backend
    uvicorn partner_api.main:app --reload --port 8001

Authentification par cle API (header X-API-Key, une cle par partenaire) —
voir partner_api/auth.py et PARTNER_API_KEYS dans backend/.env.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.logging import configure_logging, get_logger
from app.recommandations.service import load_index
from partner_api.routes import router

configure_logging()
logger = get_logger(__name__)

app = FastAPI(
    title="Typhoon Partner API",
    description="Analyse climatique d'une adresse : score de risque par zone/alea et recommandations de travaux.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "typhoon-partner-api"}


@app.on_event("startup")
async def on_startup() -> None:
    try:
        load_index()
    except Exception as exc:
        logger.warning("Index RAG non charge : %s -- les recommandations resteront vides", exc)
    logger.info("Typhoon Partner API demarree -- route : POST /v1/analyze")
