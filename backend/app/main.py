"""Entrypoint FastAPI — expose le StateGraph LangGraph comme service de diagnostic.

Lancement :
    cd backend
    uvicorn app.main:app --reload

Routes :
    GET  /health                  → Health check
    POST /diagnostic              → Diagnostic complet (nouveau format)
    GET  /diagnostic/{session_id} → Récupérer un diagnostic
    POST /api/analyze             → Legacy : analyse complète
    POST /api/bank/analyze        → Legacy : analyse bancaire async
    GET  /api/analysis/{id}       → Legacy : récupérer analyse
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import diagnostic, health, legacy
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Typhoon — API diagnostic climatique", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes nouvelles (Typhoon2-Alpha style)
app.include_router(health.router)
app.include_router(diagnostic.router)

# Routes legacy (compatibilité frontend existant)
app.include_router(legacy.router, prefix="/api")


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Typhoon API v2 démarrée")
    logger.info("Routes: GET /health, POST /diagnostic, POST /api/analyze, POST /api/bank/analyze")
