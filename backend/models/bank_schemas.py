from pydantic import BaseModel, Field
from typing import Optional


class RisqueIdentifie(BaseModel):
    """Risque identifié sur le bien."""
    nom: str = Field(..., description="Nom du risque (ex: Inondation, RGA, Canicule)")
    score: int = Field(ge=0, le=100, description="Score de sévérité 0-100")
    niveau: str = Field(..., description="Niveau : faible, modere, eleve, critique")
    zone_impactee: str = Field(..., description="Zone du bâtiment impactée (ex: Sous-sol, Fondations, Toiture)")
    description: str = Field(default="", description="Description courte du risque")


class GarantieAssurance(BaseModel):
    """Garantie d'assurance recommandée."""
    type: str = Field(..., description="Type de garantie (ex: Multirisque habitation, CatNat)")
    obligatoire: bool = Field(default=True, description="Si la garantie est obligatoire ou optionnelle")
    detail: str = Field(default="", description="Description détaillée de la couverture")


class PreventionRecommandation(BaseModel):
    """Recommandation de prévention / travaux."""
    zone: str = Field(..., description="Zone concernée (fondations, toiture, sous-sol, murs)")
    travaux: str = Field(..., description="Description des travaux")
    cout_estime: str = Field(default="", description="Coût estimé")
    gain_resilience: int = Field(default=0, ge=0, le=100, description="Gain de résilience estimé (%)")
    priorite: int = Field(default=99, description="Priorité (1 = urgente)")
    aide_financiere: str = Field(default="", description="Aide financière mobilisable")


class ProjectionRisque(BaseModel):
    """Projection de l'évolution du risque à horizon 2050."""
    horizon: str = Field(default="2050", description="Horizon de projection")
    score_actuel: int = Field(ge=0, le=100, description="Score de risque actuel")
    score_projete: int = Field(ge=0, le=100, description="Score projeté en 2050")
    aggravation: int = Field(default=0, description="Écart en points entre score projeté et actuel")
    scenario: str = Field(default="", description="Scénario climatique utilisé")
    zones_projetees: dict = Field(default_factory=dict, description="Détail par zone (fondations, toiture, etc.)")


class BankDecision(BaseModel):
    """
    Décision complète d'analyse crédit bancaire.
    
    Structure en 7 sections :
    1. score_risque_bancaire / niveau_risque_global → 📊 Score de risque du bien
    2. risques_identifies → ⚠️ Principaux risques identifiés
    3. valeur_marche / valeur_ajustee → 💰 Valeur ajustée du bien
    4. garanties_assurance → 🛡️ Garanties d'assurance recommandées
    5. prevention_recommandations → 🏗️ Recommandations de prévention
    6. projection_risque → 📈 Projection de l'évolution du risque
    7. avis_analyste / rapport_synthetique → 📄 Rapport d'analyse synthétique
    """

    # ── Section 1 : 📊 Score de risque du bien ────────────────────────────────
    score_risque_bancaire: int = Field(default=0, ge=0, le=100, description="Score de risque global bancaire sur 100")
    score_climatique: int = Field(ge=0, le=100, description="Score de risque climatique global (Géorisques) 0-100")
    niveau_risque_global: str = Field(..., description="Niveau de risque évalué : Faible, Modéré, Élevé")
    impact_esg: str = Field(..., description="Impact environnemental du financement (ex: Passoire thermique, Éligible Prêt Vert)")

    # ── Section 2 : ⚠️ Principaux risques identifiés ──────────────────────────
    risques_identifies: list[RisqueIdentifie] = Field(
        default_factory=list,
        description="Liste des principaux risques identifiés par zone et par aléa"
    )

    # ── Section 3 : 💰 Valeur ajustée du bien ─────────────────────────────────
    valeur_marche: float = Field(..., description="Valeur estimée du bien sur le marché (en euros)")
    valeur_ajustee: float = Field(..., description="Valeur du bien après décote de risque (en euros)")
    decote_pct: int = Field(..., description="Pourcentage de décote appliqué")
    source_valorisation: str = Field(default="", description="Source de la valorisation (DVF, Fallback...)")

    # ── Section 4 : 🛡️ Garanties d'assurance recommandées ────────────────────
    garanties_assurance: list[GarantieAssurance] = Field(
        default_factory=list,
        description="Garanties d'assurance recommandées selon le profil de risque"
    )

    # ── Section 5 : 🏗️ Recommandations de prévention ─────────────────────────
    prevention_recommandations: list[PreventionRecommandation] = Field(
        default_factory=list,
        description="Recommandations de travaux de prévention par zone"
    )
    cout_total_prevention: str = Field(default="0€", description="Coût total estimé des travaux de prévention")

    # ── Section 6 : 📈 Projection de l'évolution du risque ────────────────────
    projection_risque: Optional[ProjectionRisque] = Field(
        default=None,
        description="Projection de l'évolution du risque à horizon 2050"
    )

    # ── Section 7 : 📄 Rapport d'analyse synthétique ─────────────────────────
    niveau_risque_bancaire: str = Field(
        default="",
        description="Niveau de risque global : Faible, Modéré, Élevé — indicateur d'aide à la décision"
    )
    indice_confiance: int = Field(ge=0, le=100, description="Niveau de confiance dans les données déclaratives (0-100)")
    avis_analyste: str = Field(..., description="Avis synthétique rédigé par l'IA pour le comité de crédit")
    rapport_synthetique: str = Field(
        default="",
        description="Rapport d'analyse complet formaté pour l'analyste bancaire"
    )
    synthese_points_cles: list[str] = Field(
        default_factory=list,
        description="Points clés à retenir pour l'analyse (max 5)"
    )
    analyse_complete_url: str = Field(default="", description="URL de téléchargement du rapport PDF complet")

    # ── Champs legacy conservés pour compatibilité ───────────────────────────
    taux_propose: float = Field(..., description="Taux d'intérêt proposé (%)")
    majoration_taux: float = Field(..., description="Majoration ou bonification du taux liée au risque (%)")
    exigences: list[str] = Field(default_factory=list, description="Conditions exigées par la banque")
    points_a_verifier: list[str] = Field(default_factory=list, description="Liste des points déclaratifs à vérifier")
    points_forts: list[str] = Field(default_factory=list, description="Arguments favorables au dossier")
    points_faibles: list[str] = Field(default_factory=list, description="Arguments défavorables au dossier")
    recommandation_garantie: str = Field(..., description="Type de garantie recommandée")
    conditions_suspensives: list[str] = Field(default_factory=list, description="Clauses à intégrer au contrat de prêt")
    hard_stops: list[str] = Field(default_factory=list, description="Points de vigilance bloquants détectés")
