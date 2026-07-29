from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PerilScoreDetail(BaseModel):
    score: float = 0.0
    facteurs: list[str] = Field(default_factory=list)
    amelioration: str = ""


class PerilScores(BaseModel):
    inondation: float = 0.0
    rga: float = 0.0
    tempete: float = 0.0
    incendie: float = 0.0
    seisme: float = 0.0


class RecommendationItem(BaseModel):
    priorite: str  # Haute | Moyenne | Basse
    action: str
    impact: str


class DetailedAnalysis(BaseModel):
    inondation: PerilScoreDetail = Field(default_factory=PerilScoreDetail)
    rga: PerilScoreDetail = Field(default_factory=PerilScoreDetail)
    tempete: PerilScoreDetail = Field(default_factory=PerilScoreDetail)
    incendie: PerilScoreDetail = Field(default_factory=PerilScoreDetail)
    seisme: PerilScoreDetail = Field(default_factory=PerilScoreDetail)


class FullLLMExportReport(BaseModel):
    assessmentSchemaVersion: str = "2.0-llm-export"
    niveauRisque: str  # faible | modere | eleve | critique
    scoreGlobal: float
    perilScores: PerilScores = Field(default_factory=PerilScores)
    resume: str = ""
    pointsVigilance: list[str] = Field(default_factory=list)  # exactly 3
    recommandations: list[RecommendationItem] = Field(default_factory=list)  # 3-5 items
    syntheseTexte: str = ""
    scoreJustification: str = ""
    analyseDetaillee: DetailedAnalysis = Field(default_factory=DetailedAnalysis)
    catnatSummary: dict[str, Any] = Field(default_factory=dict)
    valuation: dict[str, Any] = Field(default_factory=dict)
    climateProjection2050: dict[str, Any] = Field(default_factory=dict)
    proximityRisks: dict[str, Any] = Field(default_factory=dict)
    construction: dict[str, Any] = Field(default_factory=dict)
    dataSources: list[str] = Field(default_factory=list)
