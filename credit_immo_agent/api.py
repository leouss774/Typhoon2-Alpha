from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from orchestrator import executer
from typhoon_bridge import collect_from_address

app = FastAPI(title="Typhoon — Diagnostic crédit immobilier", version="2.0.0")
HERE = Path(__file__).parent


class HouseFeatures(BaseModel):
    annee_construction: int | None = None
    dpe: str | None = None          # A/B/C/D/E/F/G
    chauffage_type: str | None = None  # electrique/gaz/fioul/bois/pac/reseau
    chauffage_age: str | None = None   # recent/moyen/vieux
    electricite: str | None = None     # recent/bon/moyen/vetuste/dangereux
    plomberie: str | None = None       # recent/bon/moyen/vetuste
    menuiseries: str | None = None     # double_vitrage_recent/double_vitrage/simple_bois/simple_metal
    isolation_combles: str | None = None  # excellente/bonne/moyenne/insuffisante/absente
    isolation_murs: str | None = None
    amiante: str | None = None        # non/non_recherche/present
    plomb: str | None = None          # non/non_recherche/present
    termites: str | None = None       # non/non_recherche/present
    assainissement: str | None = None # collecte/autonome_conforme/autonome_non_conforme
    copropriete: str | None = None    # faibles/normales/elevees/tres_elevees
    stationnement: str | None = None  # aucun/exterieur/garage_simple/garage_double


class AddressInput(BaseModel):
    address: str
    montant_emprunte: float = 300000
    duree_annees: int = 20
    taux_annuel: float = 3.4
    features: HouseFeatures | None = None


@app.post("/diagnostic_by_address")
async def diagnostic_by_address(input: AddressInput):
    try:
        features_dict = input.features.model_dump() if input.features else {}
        data = await collect_from_address(
            input.address,
            montant_emprunte=input.montant_emprunte,
            duree_annees=input.duree_annees,
            taux_annuel=input.taux_annuel,
            house_features=features_dict,
        )
        result = executer(data["risque"], data["recommandations"], data["dossier"])
        return {
            "collector_ok": data["collector_ok"],
            "adresse": input.address,
            "resultat": result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "static" / "index.html").read_text(encoding="utf-8")


app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
