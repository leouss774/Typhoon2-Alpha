"""Interface ChromaDB pour l'agent RAG de recommandation.

Gère la connexion, l'indexation et la recherche dans la base
vectorielle des connaissances techniques de travaux de rénovation.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings

from backend.config.settings import get_settings

logger = logging.getLogger(__name__)


class RecommandationVectorDB:
    """Interface vers ChromaDB pour les recommandations de travaux."""

    def __init__(self):
        settings = get_settings()
        self.client = chromadb.PersistentClient(
            path=settings.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection_name = settings.CHROMA_COLLECTION_NAME
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            try:
                self._collection = self.client.get_collection(self.collection_name)
            except Exception:
                self._collection = self.client.create_collection(
                    name=self.collection_name,
                    metadata={"description": "Fiches techniques de travaux de rénovation"},
                )
        return self._collection

    def indexer_fiches(self, fiches: list[dict]) -> int:
        """Indexe des fiches techniques dans ChromaDB.

        Args:
            fiches: Liste de dicts avec 'id', 'titre', 'description',
                    'aleas_cibles', 'cout_bas', 'cout_haut', 'gain_resilience'.

        Returns:
            Nombre de fiches indexées.
        """
        ids = [f["id"] for f in fiches]
        metadatas = [
            {
                "titre": f["titre"],
                "aleas_cibles": ",".join(f.get("aleas_cibles", [])),
                "cout_bas": f.get("cout_bas", 0),
                "cout_haut": f.get("cout_haut", 0),
                "gain_resilience": f.get("gain_resilience", 0),
            }
            for f in fiches
        ]
        documents = [f"{f['titre']}. {f['description']}" for f in fiches]

        self.collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )
        logger.info(f"Indexé {len(fiches)} fiches techniques dans ChromaDB")
        return len(fiches)

    def rechercher(self, query: str, aleas_cibles: list[str] | None = None, k: int = 5) -> list[dict]:
        """Recherche les fiches techniques pertinentes.

        Args:
            query: Texte de recherche (ex: "renforcement fondations argile").
            aleas_cibles: Filtrer par aléas cibles.
            k: Nombre de résultats.

        Returns:
            Liste des fiches les plus pertinentes.
        """
        where = None
        if aleas_cibles:
            where = {"aleas_cibles": {"$in": aleas_cibles}}

        results = self.collection.query(
            query_texts=[query],
            n_results=k,
            where=where,
        )

        fiches = []
        if results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                fiches.append({
                    "id": results["ids"][0][i],
                    "titre": results["metadatas"][0][i].get("titre", ""),
                    "description": doc,
                    "cout_bas": results["metadatas"][0][i].get("cout_bas", 0),
                    "cout_haut": results["metadatas"][0][i].get("cout_haut", 0),
                    "gain_resilience": results["metadatas"][0][i].get("gain_resilience", 0),
                    "aleas_cibles": results["metadatas"][0][i].get("aleas_cibles", "").split(","),
                    "score": results["distances"][0][i] if results.get("distances") else 0,
                })
        return fiches
