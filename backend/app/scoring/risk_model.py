"""
Scoring de risque climatique par aléa (Person 1 — Zone Orchestration & Scoring).

Calcule un score 0-100 pour 5 périls à partir des données collectées par
collector_agent. Le score global est une moyenne pondérée des 5 périls.

Pondérations (validées par l'équipe actuariat le 2026-03-14) :
  - Inondation : 30%
  - RGA (retrait-gonflement des argiles) : 25%
  - Tempête : 20%
  - Incendie : 15%
  - Séisme : 10%

Spécifications détaillées des formules disponibles dans
docs/SCORING_FORMULES.md (à rédiger — pour l'instant, la présente
implémentation sert de spécification exécutable).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# --- Pondérations officielles des 5 périls ---
POIDS_INONDATION = 0.30
POIDS_RGA = 0.25
POIDS_TEMPETE = 0.20
POIDS_INCENDIE = 0.15
POIDS_SEISME = 0.10

assert abs(POIDS_INONDATION + POIDS_RGA + POIDS_TEMPETE + POIDS_INCENDIE + POIDS_SEISME - 1.0) < 1e-9

# Seuils de changement de niveau
SEUIL_CRITIQUE = 70
SEUIL_ELEVE = 45
SEUIL_MONTH = 20


@dataclass
class ScorePeril:
    """Score 0-100 pour un péril donné, avec métadonnées de diagnostic."""
    score: float               # 0 = risque nul, 100 = risque maximal
    niveau: str                # "faible", "modere", "eleve", "critique"
    sources_utilisees: list[str]
    donnees_manquantes: list[str] = field(default_factory=list)
    justification: str = ""


@dataclass
class ScoresAdresse:
    """Ensemble des scores pour une adresse unique."""
    inondation: ScorePeril
    rga: ScorePeril
    tempete: ScorePeril
    incendie: ScorePeril
    seisme: ScorePeril
    score_global: float          # moyenne pondérée 0-100
    niveau_global: str           # "faible", "modere", "eleve", "critique"
    land_only: bool = False     # True si BDNB était absent

    def to_dict(self) -> dict:
        return {
            "score_global": round(self.score_global, 1),
            "niveau_global": self.niveau_global,
            "land_only": self.land_only,
            "perils": {
                "inondation": _score_peril_dict(self.inondation),
                "rga": _score_peril_dict(self.rga),
                "tempete": _score_peril_dict(self.tempete),
                "incendie": _score_peril_dict(self.incendie),
                "seisme": _score_peril_dict(self.seisme),
            },
        }


def _score_peril_dict(sp: ScorePeril) -> dict:
    return {
        "score": round(sp.score, 1),
        "niveau": sp.niveau,
        "sources_utilisees": sp.sources_utilisees,
        "donnees_manquantes": sp.donnees_manquantes,
        "justification": sp.justification,
    }


def _niveau(score: float) -> str:
    if score >= SEUIL_CRITIQUE:
        return "critique"
    if score >= SEUIL_ELEVE:
        return "eleve"
    if score >= SEUIL_MONTH:
        return "modere"
    return "faible"


# ---------------------------------------------------------------------------
#   Scores individuels par péril
# ---------------------------------------------------------------------------

def _score_inondation(building_data: dict, land_only: bool) -> ScorePeril:
    """
    Inondation (30%) — basé sur Géorisques gazella/inondation + altitude + CATNAT.

    Sources : georisques.risques_commune, georisques.catnat, altitude_m
    """
    sources: list[str] = []
    manquantes: list[str] = []
    score = 10.0  # score de base (risque faible par défaut)

    georisques = building_data.get("georisques") or {}
    altitude = building_data.get("altitude_m")

    # 1) Aléa inondation dans les risques de la commune
    risques = georisques.get("risques_commune") or {}
    gazella = None
    if isinstance(risques, dict):
        gazella = risques.get("gazella") or risques.get("inondation")
    elif isinstance(risques, list):
        for r in risques:
            if isinstance(r, dict) and "inondation" in str(r.get("libelle_risque_long", "")).lower():
                gazella = r
                break

    if gazella:
        sources.append("georisques.risques_commune")
        alerte = str(gazella.get("alerte", "")).lower() if isinstance(gazella, dict) else ""
        if "fort" in alerte or "élevé" in alerte:
            score += 45
        elif "moyen" in alerte or "modéré" in alerte:
            score += 25
        elif "faible" in alerte:
            score += 10
    else:
        manquantes.append("georisques.risques_commune.gazella")

    # 2) CATNAT inondation historique
    catnat = georisques.get("catnat") or {}
    catnat_list = []
    if isinstance(catnat, dict):
        catnat_list = catnat.get("data") or []
    elif isinstance(catnat, list):
        catnat_list = catnat

    inondation_catnat = [
        c for c in catnat_list
        if isinstance(c, dict) and "inondation" in str(c.get("libelle_catnat", "")).lower()
    ]
    if inondation_catnat:
        sources.append("georisques.catnat")
        score = min(score + 15, 100)

    # 3) Altitude basse -> risque inondation aggravé
    if altitude is not None:
        sources.append("ign_altitude")
        if altitude < 5:
            score += 15
        elif altitude < 15:
            score += 8
    else:
        manquantes.append("ign_altitude")

    # 4) BDNB : sous-sol -> vulnérabilité (si disponible)
    if not land_only:
        bdnb = building_data.get("bdnb") or {}
        batiment = bdnb.get("batiment") or {}
        if batiment.get("nb_niveau_sous_sol", 0) > 0:
            score += 5
            sources.append("bdnb")

    score = min(max(score, 0), 100)
    return ScorePeril(
        score=score,
        niveau=_niveau(score),
        sources_utilisees=sources,
        donnees_manquantes=manquantes,
        justification=_justifier_peril("Inondation", sources, manquantes, score),
    )


def _score_rga(building_data: dict, land_only: bool) -> ScorePeril:
    """
    RGA / Retrait-Gonflement des Argiles (25%).

    Sources : georisques.risques_commune (argiles), BDNB (fondations)
    """
    sources: list[str] = []
    manquantes: list[str] = []
    score = 8.0  # score de base aligné avec les autres périls

    georisques = building_data.get("georisques") or {}

    risques = georisques.get("risques_commune") or {}
    argiles = None
    if isinstance(risques, dict):
        argiles = risques.get("argiles")
    elif isinstance(risques, list):
        for r in risques:
            if isinstance(r, dict) and "argile" in str(r.get("libelle_risque_long", "")).lower():
                argiles = r
                break

    if argiles:
        sources.append("georisques.risques_commune.argiles")
        alerte = str(argiles.get("alerte", "")).lower() if isinstance(argiles, dict) else ""
        if "fort" in alerte or "élevé" in alerte:
            score += 52
        elif "moyen" in alerte or "modéré" in alerte:
            score += 30
        elif "faible" in alerte:
            score += 10
    else:
        manquantes.append("georisques.risques_commune.argiles")

    # BDNB : âge du bâtiment (avant 1980 = fondations potentiellement moins profondes)
    if not land_only:
        bdnb = building_data.get("bdnb") or {}
        batiment = bdnb.get("batiment") or {}
        annee = batiment.get("annee_construction")
        if annee and isinstance(annee, (int, float)) and annee < 1980:
            score += 8
            sources.append("bdnb.annee_construction")

    # Climat : sécheresse projetée -> RGA aggravé
    climat = building_data.get("climat_open_meteo") or {}
    if climat:
        proj = climat.get("projection_2041_2050") or {}
        jours_chaleur = proj.get("jours_chaleur_extreme_par_an")
        if jours_chaleur is not None and jours_chaleur > 60:
            score += 10
            sources.append("open_meteo.projection_2041_2050")

    score = min(max(score, 0), 100)
    return ScorePeril(
        score=score,
        niveau=_niveau(score),
        sources_utilisees=sources,
        donnees_manquantes=manquantes,
        justification=_justifier_peril("RGA", sources, manquantes, score),
    )


def _score_tempete(building_data: dict, land_only: bool) -> ScorePeril:
    """
    Tempête (20%) — basé sur CATNAT vent/tempête + altitude exposée.
    """
    sources: list[str] = []
    manquantes: list[str] = []
    score = 8.0

    georisques = building_data.get("georisques") or {}
    catnat = georisques.get("catnat") or {}
    catnat_list = []
    if isinstance(catnat, dict):
        catnat_list = catnat.get("data") or []
    elif isinstance(catnat, list):
        catnat_list = catnat

    tempete_catnat = [
        c for c in catnat_list
        if isinstance(c, dict) and any(
            mot in str(c.get("libelle_catnat", "")).lower()
            for mot in ("tempête", "vent", "cyclone", "ouragan")
        )
    ]
    if tempete_catnat:
        sources.append("georisques.catnat")
        score += 25 * min(len(tempete_catnat), 3)

    altitude = building_data.get("altitude_m")
    if altitude is not None:
        sources.append("ign_altitude")
        if altitude > 500:
            score += 15
        elif altitude > 200:
            score += 8

    climat = building_data.get("climat_open_meteo") or {}
    if climat:
        proj = climat.get("projection_2041_2050") or {}
        precip = proj.get("precipitation_annuelle_moyenne_mm")
        if precip is not None and precip > 900:
            score += 10
            sources.append("open_meteo.projection_2041_2050")

    score = min(max(score, 0), 100)
    return ScorePeril(
        score=score,
        niveau=_niveau(score),
        sources_utilisees=sources,
        donnees_manquantes=manquantes,
        justification=_justifier_peril("Tempête", sources, manquantes, score),
    )


def _score_incendie(building_data: dict, land_only: bool) -> ScorePeril:
    """
    Incendie (15%) — basé sur Géorisques feux de forêt + données climatiques.
    """
    sources: list[str] = []
    manquantes: list[str] = []
    score = 5.0

    georisques = building_data.get("georisques") or {}
    risques = georisques.get("risques_commune") or {}
    feu = None
    if isinstance(risques, dict):
        feu = risques.get("feu_foret") or risques.get("incendie")
    elif isinstance(risques, list):
        for r in risques:
            if isinstance(r, dict) and any(
                mot in str(r.get("libelle_risque_long", "")).lower()
                for mot in ("feu", "incendie", "forêt")
            ):
                feu = r
                break

    if feu:
        sources.append("georisques.risques_commune.feu_foret")
        alerte = str(feu.get("alerte", "")).lower() if isinstance(feu, dict) else ""
        if "fort" in alerte or "élevé" in alerte:
            score += 50
        elif "moyen" in alerte or "modéré" in alerte:
            score += 25
        elif "faible" in alerte:
            score += 10
    else:
        manquantes.append("georisques.risques_commune.feu_foret")

    climat = building_data.get("climat_open_meteo") or {}
    if climat:
        ref = climat.get("reference_2015_2024") or {}
        jours_chaleur = ref.get("jours_chaleur_extreme_par_an")
        if jours_chaleur is not None and jours_chaleur > 30:
            score += 15
            sources.append("open_meteo.climat")

    score = min(max(score, 0), 100)
    return ScorePeril(
        score=score,
        niveau=_niveau(score),
        sources_utilisees=sources,
        donnees_manquantes=manquantes,
        justification=_justifier_peril("Incendie", sources, manquantes, score),
    )


def _score_seisme(building_data: dict, land_only: bool) -> ScorePeril:
    """
    Séisme (10%) — basé sur Géorisques zonage sismique + BDNB structure.
    """
    sources: list[str] = []
    manquantes: list[str] = []
    score = 5.0

    georisques = building_data.get("georisques") or {}
    zonage = georisques.get("zonage_sismique") or {}

    if isinstance(zonage, dict) and zonage.get("zone_sismique"):
        sources.append("georisques.zonage_sismique")
        zone = str(zonage.get("zone_sismique", "")).lower()
        if "5" in zone or "très fort" in zone:
            score += 70
        elif "4" in zone or "fort" in zone:
            score += 50
        elif "3" in zone or "modéré" in zone:
            score += 30
        elif "2" in zone or "moyen" in zone:
            score += 15
        elif "1" in zone or "faible" in zone:
            score += 5
    else:
        manquantes.append("georisques.zonage_sismique")

    if not land_only:
        bdnb = building_data.get("bdnb") or {}
        batiment = bdnb.get("batiment") or {}
        structure = str(batiment.get("materiau_structure", "")).lower()
        if structure:
            sources.append("bdnb.materiau_structure")
            if "beton" in structure or "béton" in structure:
                score = max(score - 10, 0)
            elif "bois" in structure or "pan de bois" in structure:
                score += 10

    score = min(max(score, 0), 100)
    return ScorePeril(
        score=score,
        niveau=_niveau(score),
        sources_utilisees=sources,
        donnees_manquantes=manquantes,
        justification=_justifier_peril("Séisme", sources, manquantes, score),
    )


def _justifier_peril(nom: str, sources: list[str], manquantes: list[str], score: float) -> str:
    """Génère une justification lisible pour un score de péril."""
    parties = []
    if sources:
        parties.append(f"{len(sources)} source(s) utilisée(s)")
    if manquantes:
        parties.append(f"{len(manquantes)} source(s) manquante(s)")
    if not sources and not manquantes:
        parties.append("aucune donnée disponible — score par défaut")
    return f"Score {nom} : {score:.0f}/100 — basé sur {', '.join(parties)}."


# ---------------------------------------------------------------------------
#   Point d'entrée unique
# ---------------------------------------------------------------------------

def score_address(building_data: dict, land_only: bool = False) -> ScoresAdresse:
    """Calcule les 5 scores de péril + score global pour une adresse.

    Parameters
    ----------
    building_data : dict
        Données collectées par collector_agent.collect(), structurées
        comme défini dans le TypedDict BuildingData.
    land_only : bool
        Si True, ignore les données BDNB (pour les parcelles nues).

    Returns
    -------
    ScoresAdresse avec les 5 périls et le score global pondéré.
    """
    inondation = _score_inondation(building_data, land_only)
    rga = _score_rga(building_data, land_only)
    tempete = _score_tempete(building_data, land_only)
    incendie = _score_incendie(building_data, land_only)
    seisme = _score_seisme(building_data, land_only)

    score_global = (
        inondation.score * POIDS_INONDATION
        + rga.score * POIDS_RGA
        + tempete.score * POIDS_TEMPETE
        + incendie.score * POIDS_INCENDIE
        + seisme.score * POIDS_SEISME
    )

    return ScoresAdresse(
        inondation=inondation,
        rga=rga,
        tempete=tempete,
        incendie=incendie,
        seisme=seisme,
        score_global=score_global,
        niveau_global=_niveau(score_global),
        land_only=land_only,
    )
