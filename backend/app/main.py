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

<<<<<<< HEAD
from app.api.routes import diagnostic, health
from app.core.logging import configure_logging, get_logger
=======
from app.api.routes import artisans, chat, diagnostic, health
from app.api.routes import diagnostic, health, property_id as property_id_router
from app.core.logging import configure_logging, get_logger
from app.property_id.service import init_service as init_property_id_service
from app.recommandations.service import load_index
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314

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
<<<<<<< HEAD
=======
app.include_router(chat.router)
app.include_router(artisans.router)
app.include_router(artisans.legacy_router)
app.include_router(property_id_router.router)
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314


@app.on_event("startup")
async def on_startup() -> None:
<<<<<<< HEAD
    logger.info("Typhoon API demarree — routes : POST /diagnostic, GET /health")
=======
    # Index de l'agent recommandations (~19 Mo, ~900 fiches) : charge une
    # seule fois ici plutot qu'a chaque requete /diagnostic, cf.
    # app/recommandations/service.py et PROMPT_INTEGRATION_ouss.md section 2.
    load_index()
    logger.info("Typhoon API demarree — routes : POST /diagnostic, GET /health, POST /api/v1/artisans/matching")
    init_property_id_service()
    # Index RAG : charge une seule fois au demarrage, pas a chaque requete
    try:
        load_index()
    except Exception as exc:
        logger.warning("Index RAG non charge : %s — les recommandations resteront vides", exc)
    logger.info("Typhoon API demarree — routes : POST /diagnostic, POST /property-id/generate, GET /property-id/{id}, GET /health")
>>>>>>> 565653094351f2bb74c354c73f4ff02443987314
