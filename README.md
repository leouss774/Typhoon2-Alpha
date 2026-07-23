# Typhoon 🌪️

Système multi-agents d'évaluation des risques climatiques pour l'habitat individuel.

## Architecture

```
typhoon/
├── backend/          # API FastAPI + agents LangGraph
│   ├── agent_graph/  # 🕸️ Orchestration LangGraph (StateGraph)
│   ├── agents/       # 🧠 Logique des 3 agents métier
│   ├── api/          # 🚪 Routes REST FastAPI
│   ├── services/     # 🧮 Scoring, DRIAS, cartographie
│   └── models/       # 📐 Schémas Pydantic partagés
├── frontend/         # 🎨 React + Vite + TypeScript
└── scripts/          # 📜 Scripts utilitaires
```

## Agents

| Agent | Technologie | Rôle |
|-------|-------------|------|
| **Analyste Risque** | LLM (Claude) + prompt système | Analyse qualitative des risques |
| **Recommandation** | RAG (ChromaDB + LLM) | Propositions de travaux priorisés |
| **Conversationnel** | LLM + contexte rapport | Chat client sur l'analyse |

## Prérequis

- Python ≥ 3.11
- Node.js ≥ 20
- Docker Desktop (optionnel)

## Installation

```bash
# Backend
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sur Windows
pip install -e ".[dev]"

# Frontend
cd frontend
npm install
```

## Configuration

Copier `.env.example` vers `.env` et renseigner les clés :

```bash
cp .env.example .env
# Éditer .env avec votre clé ANTHROPIC_API_KEY
```

## Lancement

```bash
# Backend seul
uvicorn backend.api.main:app --reload

# Frontend seul
cd frontend && npm run dev

# Tout avec Docker
docker-compose up
```

## Utilisation

1. `POST /api/analyze` — Lancer une analyse complète (formulaire client + données brutes)
2. `GET /api/dashboard/{session_id}` — Récupérer les données du dashboard
3. `POST /api/chat/{session_id}` — Poser une question à l'agent conversationnel
