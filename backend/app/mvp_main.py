"""
Entrypoint FastAPI — version MVP uniquement (sans LangGraph).

Ne charge que les routes /mvp/assess + /health, évite la dépendance
langgraph nécessaire aux routes /diagnostic et /zone/jobs.

Lancement :
    cd backend
    uvicorn app.mvp_main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, mvp
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Typhoon — MVP diagnostic climatique", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(mvp.router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Typhoon MVP API demarree — routes : POST /mvp/assess, GET /health")
