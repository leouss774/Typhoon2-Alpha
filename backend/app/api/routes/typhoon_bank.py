"""FastAPI routes for the independent Typhoon Bank module."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.bank.config import typhoon_bank_enabled
from app.bank.service import TyphoonBankService
from app.schemas.typhoon_bank import EXAMPLE_INPUT, TyphoonBankInput, TyphoonBankOutput

router = APIRouter(tags=["Typhoon Bank"])
service = TyphoonBankService()


@router.get("/typhoon-bank")
@router.get("/api/typhoon-bank")
async def typhoon_bank_dashboard():
    if not typhoon_bank_enabled():
        raise HTTPException(status_code=503, detail="Typhoon Bank module is disabled.")

    frontend_path = Path(__file__).resolve().parents[4] / "frontend" / "typhoon-bank" / "index.html"
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {
        "module": "Typhoon Bank",
        "enabled": True,
        "analyze_endpoint": "POST /typhoon-bank",
        "example_input": EXAMPLE_INPUT,
    }


@router.post("/typhoon-bank", response_model=TyphoonBankOutput)
@router.post("/api/typhoon-bank", response_model=TyphoonBankOutput)
async def analyze_typhoon_bank(payload: TyphoonBankInput) -> TyphoonBankOutput:
    if not typhoon_bank_enabled():
        raise HTTPException(status_code=503, detail="Typhoon Bank module is disabled.")
    return await service.analyze(payload)
