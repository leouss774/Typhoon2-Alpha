"""
Entrypoint FastAPI — expose le StateGraph LangGraph comme un service de
diagnostic (cf. README racine, section "Backend — communication
inter-agents").

Lancement :
    cd backend
    uvicorn app.main:app --reload

CORS ouvert (`allow_origins=["*"]`) : le front de test
(`frontend/jumeau_numerique/index.html`) est ouvert directement en
`file://` depuis le navigateur (pas de serveur web devant), dont l'origine
est "null" - un allow_origins restrictif casserait cet usage. A resserrer
si un vrai front est deploye derriere un domaine.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import artisans, diagnostic, health
from app.core.logging import configure_logging, get_logger
from app.recommandations.service import load_index

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Typhoon — API diagnostic climatique", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(diagnostic.router)
app.include_router(artisans.router)


@app.on_event("startup")
async def on_startup() -> None:
    # Index de l'agent recommandations (~19 Mo, ~900 fiches) : charge une
    # seule fois ici plutot qu'a chaque requete /diagnostic, cf.
    # app/recommandations/service.py et PROMPT_INTEGRATION_ouss.md section 2.
    load_index()
    logger.info("Typhoon API demarree — routes : POST /diagnostic, GET /health, POST /api/v1/artisans/matching")
