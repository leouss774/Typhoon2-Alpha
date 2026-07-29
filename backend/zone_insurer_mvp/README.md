# Zone Insurer MVP Backend (Risk Map)

Standalone FastAPI service for the Typhoon **risk map** feature (MVP).

Location: `backend/zone_insurer_mvp/` — lives alongside the main orchestrator but
is self-contained and deployable independently.

## Quick start

```bash
cd backend/zone_insurer_mvp
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Uses the shared root `.env` (single source of truth). Copy
`.env.example` to the root `.env` if it does not exist yet.

Frontend expects `API_BASE = http://localhost:8001` in `frontend/zone_insurer/app.js`.

## API

- `POST /zone/assess` — see `docs/MVP_CONTRACT.md` (Epic 1) and `docs/IMPLEMENTATION_PLAN.md`.

## Documentation

| Doc | Description |
|-----|-------------|
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Full execution plan (epics, schema, scoring, Mistral, prompts) |
| MVP_CONTRACT.md | API examples (Epic 1) |
| SCORING.md | Scoring formulas (Epic 2) |
| AI_AGENT_PROMPT.md | LLM prompts for narrative (Epic 3) |
