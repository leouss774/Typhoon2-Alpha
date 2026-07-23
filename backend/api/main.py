"""Point d'entrée de l'API FastAPI Typhoon.

Configure l'application, les middleware CORS, et enregistre les routeurs.
L'application expose les endpoints pour l'analyse, le dashboard et le chat.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gère le cycle de vie de l'application."""
    settings = get_settings()
    # Initialisation au démarrage
    yield
    # Nettoyage à l'arrêt


def create_app() -> FastAPI:
    """Crée et configure l'application FastAPI."""
    settings = get_settings()

    app = FastAPI(
        title="Typhoon API",
        description="Multi-agent system for climate risk assessment on residential buildings",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes
    from backend.api.routes.analysis import router as analysis_router
    from backend.api.routes.dashboard import router as dashboard_router
    from backend.api.routes.chat import router as chat_router
    from backend.api.routes.recommendations import router as recommendations_router

    app.include_router(analysis_router, prefix="/api", tags=["Analyse"])
    app.include_router(dashboard_router, prefix="/api", tags=["Dashboard"])
    app.include_router(chat_router, prefix="/api", tags=["Chat"])
    app.include_router(recommendations_router, prefix="/api", tags=["Recommandations"])

    @app.get("/api/health")
    async def health_check():
        return {"status": "ok", "service": "typhoon"}

    return app


app = create_app()
