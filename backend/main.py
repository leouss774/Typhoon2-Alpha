from fastapi import FastAPI
from backend.api.jumeau_routes import router as jumeau_router

app = FastAPI(title="Typhoon API")

# On inclut les routes que tu as créées
app.include_router(jumeau_router)
