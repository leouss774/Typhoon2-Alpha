"""
Construit l'index vectoriel (embeddings Mistral) a partir des fiches validees
du referentiel produit par agent1_extract.py.

Usage:
    python build_index.py
"""
import json

import config
from utils.mistral_client import embed_texts


def fiche_to_text(fiche: dict) -> str:
    """Represente une fiche en texte pour le calcul de l'embedding."""
    parts = [
        f"Alea: {fiche.get('alea')}",
        f"Zone maison: {fiche.get('zone_maison')}",
        f"Territoire: {fiche.get('territoire')}",
        f"Conditions d'application: {fiche.get('conditions_application')}",
        f"Mesure: {fiche.get('mesure')}",
        f"Limites et prerequis: {fiche.get('limites_prerequis')}",
    ]
    return "\n".join(str(p) for p in parts if p and "None" not in str(p))


def main():
    with open(config.REFERENTIEL_PATH, encoding="utf-8") as f:
        data = json.load(f)

    fiches = [f for f in data["fiches"] if f.get("statut_validation") == "validated"]
    print(f"Indexation de {len(fiches)} fiches validees sur {len(data['fiches'])} au total...")

    if not fiches:
        print("Aucune fiche validee. Lance d'abord agent1_extract.py.")
        return

    texts = [fiche_to_text(f) for f in fiches]

    vectors = []
    batch_size = 32
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        vectors.extend(embed_texts(batch))
        print(f"  -> {min(i + batch_size, len(texts))}/{len(texts)} embeddings calcules")

    index = [{"fiche": f, "vector": v} for f, v in zip(fiches, vectors)]

    with open(config.INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)

    print(f"Index sauvegarde -> {config.INDEX_PATH}")


if __name__ == "__main__":
    main()
