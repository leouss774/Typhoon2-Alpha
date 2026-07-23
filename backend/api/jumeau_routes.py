from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.models.jumeau_schemas import JumeauPayload, ProjectionDataset, VulnerabilityTestResult
from backend.services.geometry_service import compute_house_footprint, GeometryError
from backend.services.risk_mapper import map_step7_to_zones, build_score_global
from backend.services.mistral_client import call_mistral_and_validate
from backend.services.projection_2050_prompt import SYSTEM_PROMPT_PROJECTION_2050, build_projection_2050_user_prompt
from backend.services.vulnerability_prompt import SYSTEM_PROMPT_VULNERABILITY_TEST, build_vulnerability_user_prompt

router = APIRouter(prefix="/api/jumeau", tags=["Jumeau Numérique"])

class InitJumeauRequest(BaseModel):
    version: str
    generated_at: str
    user_data: dict
    agent_data: dict
    step7: dict

@router.post("/initialize", response_model=JumeauPayload)
async def initialize_jumeau(payload: InitJumeauRequest):
    """Génère l'état initial 2025 du jumeau à partir des données déterministes."""
    try:
        geom_groupe = payload.agent_data.get("bdnb", {}).get("geometry")
        if not geom_groupe:
            geom_groupe = {
                'type': 'MultiPolygon',
                'coordinates': [[[[880673.1, 6543035.3], [880669.1, 6543024.3], 
                                  [880678.7, 6543020.9], [880682.5, 6543031.9], 
                                  [880673.1, 6543035.3]]]]
            }
        
        geo_metrics = compute_house_footprint(geom_groupe)
    except GeometryError as e:
        raise HTTPException(status_code=420, detail=f"Erreur géométrique : {str(e)}")

    step7_data = payload.step7
    zones_2025 = map_step7_to_zones(step7_data)
    score_global_2025 = build_score_global(step7_data)

    return JumeauPayload(
        score_global=score_global_2025,
        zones=zones_2025,
        adresse=payload.user_data.get("adresse"),
        geometrie=geo_metrics
    )

@router.post("/projection-2050", response_model=ProjectionDataset)
async def get_projection_2050(zones_2025: dict, score_global_2025: int):
    """Appelle Mistral pour générer la projection climatique 2050 aggravée."""
    system_prompt = SYSTEM_PROMPT_PROJECTION_2050
    user_prompt = build_projection_2050_user_prompt(zones_2025, score_global_2025)
    
    try:
        result = call_mistral_and_validate(system_prompt, user_prompt, ProjectionDataset)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Mistral : {str(e)}")

@router.post("/vulnerability-test", response_model=VulnerabilityTestResult)
async def run_vulnerability_test(zone_name: str, zone_data: dict, adresse: str | None = None):
    """Déclenche le test de vulnérabilité au clic sur une zone."""
    system_prompt = SYSTEM_PROMPT_VULNERABILITY_TEST
    user_prompt = build_vulnerability_user_prompt(zone_name, zone_data, adresse)
    
    try:
        result = call_mistral_and_validate(system_prompt, user_prompt, VulnerabilityTestResult)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur Mistral : {str(e)}")
