"""
Construit l'index vectoriel (embeddings Mistral) a partir des fiches validees
de data/referentiel.json — copie adaptee de recommendation_travaux/build_index.py.

Usage (depuis backend/) :
    python -m app.recommandations.build_index

A relancer si data/referentiel.json change (nouvelles fiches). Necessite
MISTRAL_API_KEY dans backend/.env (consomme des appels d'embedding reels).
"""

from __future__ import annotations

import json

from . import config
from .mistral_client import embed_texts


def fiche_to_text(fiche: dict) -> str:
    parts = [
        f"Alea: {fiche.get('alea')}",
        f"Zone maison: {fiche.get('zone_maison')}",
        f"Territoire: {fiche.get('territoire')}",
        f"Conditions d'application: {fiche.get('conditions_application')}",
        f"Mesure: {fiche.get('mesure')}",
        f"Limites et prerequis: {fiche.get('limites_prerequis')}",
    ]
    return "\n".join(str(p) for p in parts if p and "None" not in str(p))


def main() -> None:
    with open(config.REFERENTIEL_PATH, encoding="utf-8") as f:
        data = json.load(f)

    fiches = [f for f in data["fiches"] if f.get("statut_validation") == "validated"]
    print(f"Indexation de {len(fiches)} fiches validees sur {len(data['fiches'])} au total...")

    if not fiches:
        print("Aucune fiche validee dans data/referentiel.json.")
        return

    texts = [fiche_to_text(f) for f in fiches]

    vectors = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        vectors.extend(embed_texts(batch))
        print(f"  -> {min(i + batch_size, len(texts))}/{len(texts)} embeddings calcules")

    index = [{"fiche": f, "vector": v} for f, v in zip(fiches, vectors)]

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    print(f"Index sauvegarde -> {config.INDEX_PATH}")


if __name__ == "__main__":
    main()
