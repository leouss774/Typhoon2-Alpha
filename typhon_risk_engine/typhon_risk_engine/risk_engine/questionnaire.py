"""
Questionnaire dynamique : ne presente que les questions utiles au bien et aux
perils reellement evaluables.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

QUESTIONNAIRE_PATH = Path(__file__).resolve().parent.parent / "rules" / "questionnaire.yaml"


def load_questionnaire(path: Optional[Path] = None) -> dict:
    with (path or QUESTIONNAIRE_PATH).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_questionnaire(assessment: dict, answers: Optional[dict] = None,
                        spec: Optional[dict] = None) -> dict:
    """Construit la liste ordonnee des questions a poser.

    Priorite 1 : questions qui debloquent une variable DOMINANTE manquante.
    Priorite 2 : questions qui augmentent la couverture d'un bloc.
    Priorite 3 : questions de contexte.
    """
    spec = spec or load_questionnaire()
    answers = answers or {}

    needed: dict[str, list[str]] = {}
    for pid, res in (assessment.get("perils") or {}).items():
        for key in res.get("required_user_questions", []):
            needed.setdefault(key, []).append(pid)

    typo = (assessment.get("building_typology") or {}).get("kind")

    sections_out = []
    for section in spec["sections"]:
        questions = []
        for q in section["questions"]:
            key = q["key"]
            if key in answers:
                continue
            if not _typology_relevant(q, section, typo):
                continue
            unlocks = needed.get(key, [])
            questions.append({
                **q,
                "unlocks_perils": sorted(unlocks),
                "priority": 1 if unlocks else (2 if q.get("used_by") else 3),
                "allow_unknown": True,
                "answer_basis_options": spec["answer_basis_options"],
            })
        if questions:
            questions.sort(key=lambda x: (x["priority"], x["key"]))
            sections_out.append({
                "id": section["id"], "label": section["label"], "questions": questions,
            })

    return {
        "questionnaire_version": spec["questionnaire_version"],
        "unknown_policy": spec["unknown_policy"],
        "free_text_policy": spec["free_text_policy"],
        "sections": sections_out,
        "n_questions": sum(len(s["questions"]) for s in sections_out),
        "blocking_keys": sorted(needed),
    }


def _typology_relevant(question: dict, section: dict, typo: Optional[str]) -> bool:
    """Filtre minimal : ne pas poser les questions de toiture a un appartement
    en etage courant, ni les questions de fondation en collectif."""
    if typo != "collective":
        return True
    key = question["key"]
    if section["id"] in ("sol_fondations",) and "foundation" in key:
        return False
    if section["id"] == "toiture" and "roof" in key:
        return False
    return True
