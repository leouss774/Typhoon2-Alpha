"""
Test bout-en-bout du graphe complet a partir d'une adresse :

    collector_agent -> scoring_agent -> rag_agent

Contrairement a app/cli.py (qui ne teste que collector_agent seul), ce script
lance le graphe LangGraph entier (voir app/agents/graph.py) : geocodage + appels
API paralleles, puis derivation des zones/risques (scoring_agent), puis
recommandations sourcees via l'agent RAG de la collegue (rag_agent, qui appelle
Mistral - necessite MISTRAL_API_KEY dans backend/.env, voir .env.example).

Usage :
    python -m app.cli_pipeline "10 Promenade des Anglais, 06000 Nice"
    python -m app.cli_pipeline "10 Promenade des Anglais, 06000 Nice" --out out/nice.json

Le resultat complet (building_data + risk_scores + recommendations) est affiche
et sauvegarde. Comme pour app/cli.py, aucune donnee n'est simulee : chaque champ
provient d'un appel reel (BDNB, Georisques, IGN, Open-Meteo, Copernicus, Mistral)
ou reste null/vide avec l'erreur consignee si une source echoue.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.agents.graph import get_graph


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Teste le graphe complet Typhoon (collecte + scoring + recommandations) sur une adresse."
    )
    parser.add_argument("adresse", help="Adresse a diagnostiquer")
    parser.add_argument("--out", help="Chemin du fichier JSON de sortie (defaut: out/pipeline_<citycode>.json)")
    return parser.parse_args()


async def _run(adresse: str, out_override: str | None) -> dict:
    print(f"\nLancement du graphe complet pour : {adresse}", file=sys.stderr)
    graph = get_graph()
    final_state = await graph.ainvoke({"adresse": adresse})

    building_data = final_state.get("building_data", {})
    nb_erreurs = len(building_data.get("erreurs", []))
    print(f"  -> collector_agent : {nb_erreurs} source(s) en erreur", file=sys.stderr)
    for erreur in building_data.get("erreurs", []):
        print(f"     - {erreur['source']}: {erreur['erreur']}", file=sys.stderr)

    risk_scores = final_state.get("risk_scores", {})
    nb_zones = len(risk_scores.get("zones", []))
    print(f"  -> scoring_agent : {nb_zones} zone(s) a risque detectee(s)", file=sys.stderr)
    for zone in risk_scores.get("zones", []):
        print(f"     - {zone['zone']}: {', '.join(zone['risques'])}", file=sys.stderr)

    recommendations = final_state.get("recommendations", {})
    nb_reco = sum(len(z.get("recommandations", [])) for z in recommendations.get("zones", []))
    print(f"  -> rag_agent : {nb_reco} recommandation(s) generee(s)", file=sys.stderr)

    citycode = (building_data.get("adresse") or {}).get("citycode", "inconnu")
    out_path = Path(out_override) if out_override else Path("out") / f"pipeline_{citycode}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(final_state, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    print(f"  -> resultat complet sauvegarde dans {out_path}", file=sys.stderr)

    return final_state


def main() -> None:
    args = _parse_args()
    final_state = asyncio.run(_run(args.adresse, args.out))
    print(json.dumps(final_state, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
