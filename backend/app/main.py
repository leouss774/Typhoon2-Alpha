"""FastAPI entrypoint for Typhoon modules."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.routes.typhoon_bank import router as typhoon_bank_router

app = FastAPI(title="Typhoon API", version="2.0-alpha")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(typhoon_bank_router)


@app.get("/")
async def root():
    return RedirectResponse(url="/typhoon-bank")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
