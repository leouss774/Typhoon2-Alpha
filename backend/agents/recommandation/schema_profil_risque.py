"""
Schema for the Condensed Risk Profile (Profil de Risque Condensé)

This is an intermediate representation between the raw Collecteur output JSON
and the rule-based scoring engine. It normalizes and extracts key risk indicators
while gracefully handling missing/empty data from the Collecteur.

Purpose:
  - Absorb noise and structural variations in the raw JSON
  - Provide clean, normalized input for deterministic rule evaluation
  - Enable clear traceability: each field has a documented source and derivation
  - Support future enhancement (climate data, building data) without breaking changes
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class RisqueNaturel:
    """Single natural risk assessment"""
    code: str  # e.g., "inondation", "rga", "seisme", "remonteeNappe", "radon", etc.
    present: bool  # Is the risk present at this address (from rapport_risque.risquesNaturels.present)?
    libelle_source: Optional[str] = None  # Original source key from the Collecteur, e.g. "remonteeNappe"
    statut_adresse: Optional[str] = None  # e.g., "Risque Existant", "Risque Existant - faible", "Risque Inconnu"
    statut_commune: Optional[str] = None  # For reference/context
    disponible: bool = True  # Is the risk data available from Collecteur? (True unless field was missing)
    notes: Optional[str] = None  # Additional context


@dataclass
class ExpositionArgiles:
    """Retrait-Gonflement des Argiles (RGA)"""
    present: bool
    exposition: Optional[str] = None  # "Exposition faible", "Exposition modéré", "Exposition fort"
    code_exposition: Optional[str] = None  # "1", "2", "3", etc.
    libelle_source: Optional[str] = None
    disponible: bool = True


@dataclass
class ZoneSismique:
    """Seismic zone"""
    present: bool
    zone_code: Optional[str] = None  # e.g., "1", "2", "3", "4", "5"
    zone_libelle: Optional[str] = None  # e.g., "3 - MODEREE"
    libelle_source: Optional[str] = None
    disponible: bool = True


@dataclass
class RadonPotentiel:
    """Radon potential"""
    present: bool
    classe_potentiel: Optional[str] = None  # "1", "2", "3", "4" (higher = more potentiel)
    libelle_source: Optional[str] = None
    disponible: bool = True


@dataclass
class CavitesPotentielles:
    """Cavities summary extracted from Georisques."""
    present: bool = False
    count: int = 0
    libelle_source: Optional[str] = None
    disponible: bool = True


@dataclass
class EvenementHistorique:
    """Single historical disaster (CatNat)"""
    code_national: str
    type_risque: str  # e.g., "Inondations et/ou Coulées de Boue", "Mouvement de Terrain"
    date_debut: datetime
    date_fin: datetime
    date_publication_jo: datetime
    # Derived:
    jours_depuis_evt: Optional[int] = None  # Days since event (for recency weighting)
    jours_depuis_publi: Optional[int] = None  # Days since publication


@dataclass
class HistoriqueEvts:
    """Aggregated historical disaster data (CatNat)"""
    total_evts: int
    evts_par_type: dict = field(default_factory=dict)  # e.g., {"Inondations": 8, "Mouvement de Terrain": 1}
    evts: List[EvenementHistorique] = field(default_factory=list)  # Sorted by date desc (most recent first)
    disponible: bool = True
    # Derived:
    evt_le_plus_recent: Optional[EvenementHistorique] = None
    nb_evt_10ans: int = 0  # Count of events in last 10 years


@dataclass
class FacilitesProches:
    """Nearby facilities and pollution sources"""
    icpe_count: int = 0  # Number of ICPE facilities (may be high noise, use cautiously)
    icpe_present: bool = False
    sites_sols_pollues_count: int = 0
    sites_sols_pollues_present: bool = False
    canalisation_matieres_dangereuses: Optional[str] = None  # "present" / "non concerne" / "inconnu"
    disponible: bool = True


@dataclass
class DonneesTopo:
    """Topographical data"""
    altitude_m: Optional[float] = None  # Point elevation in meters (from IGN)
    disponible: bool = True


@dataclass
class ProxyClimatique:
    """Deterministic climate proxy derived from the geocoded address."""
    code: Optional[str] = None  # e.g. "froid", "intermediaire", "chaud", "tres_chaud"
    source: Optional[str] = None  # e.g. "latitude_band_v1"
    libelle_source: Optional[str] = None
    latitude: Optional[float] = None
    seuils: dict = field(default_factory=dict)
    disponible: bool = True


@dataclass
class EauxSouterraines:
    """Groundwater context (summarized from Hubeau, not raw analyses)"""
    stations_piezometriques_count: int = 0  # Nearby monitoring stations
    presente: bool = False
    disponible: bool = True
    # Summary note: detailed water quality analyses are NOT imported; only station proximity


@dataclass
class ProfilRisqueCondense:
    """
    Condensed risk profile: normalized, clean input for rule-based scoring.
    
    This represents all risk/hazard information extracted and normalized from
    the Collecteur's raw JSON output. It is deterministically derived (no LLM here).
    
    Null/missing fields are handled with defaults and 'disponible' flags.
    Downstream scoring rules reference these fields by name.
    """

    # Basic address context
    adresse: str
    code_insee: str
    coordonnees_lat: float
    coordonnees_lon: float
    geocodage_score: float  # Quality of geocoding

    # Natural risks (primary source: rapport_risque.risquesNaturels)
    risques_naturels: dict = field(default_factory=dict)  # {code: RisqueNaturel}
    
    # Specific hazard profiles
    rga: ExpositionArgiles = field(default_factory=lambda: ExpositionArgiles(present=False, disponible=False))
    zone_sismique: ZoneSismique = field(default_factory=lambda: ZoneSismique(present=False, disponible=False))
    radon: RadonPotentiel = field(default_factory=lambda: RadonPotentiel(present=False, disponible=False))
    cavites: CavitesPotentielles = field(default_factory=lambda: CavitesPotentielles(present=False, disponible=False))
    
    # Historical context
    historique_evts: HistoriqueEvts = field(default_factory=lambda: HistoriqueEvts(total_evts=0, disponible=False))
    
    # Proximity risks
    facilites_proches: FacilitesProches = field(default_factory=FacilitesProches)
    
    # Environmental data
    donnees_topo: DonneesTopo = field(default_factory=DonneesTopo)
    proxy_climatique: ProxyClimatique = field(default_factory=ProxyClimatique)
    eaux_souterraines: EauxSouterraines = field(default_factory=EauxSouterraines)
    
    # Data availability summary
    donnees_manquantes: List[str] = field(default_factory=list)  # List of blocks that were empty/unavailable
    
    # Metadata
    date_extraction: datetime = field(default_factory=datetime.now)
    version_schema: str = "1.0"  # For versioning as schema evolves

    def __post_init__(self):
        """Derived fields and validation"""
        pass  # Can add validation here if needed

    def list_risques_disponibles(self) -> List[str]:
        """List all risk codes with data available"""
        return [code for code, risk in self.risques_naturels.items() if risk.disponible]

    def list_risques_presents(self) -> List[str]:
        """List all risk codes marked as present"""
        return [code for code, risk in self.risques_naturels.items() if risk.present]


# Example usage patterns (for reference):
if __name__ == "__main__":
    # This would be populated by extraction logic:
    profil = ProfilRisqueCondense(
        adresse="8 Allée du Port Maillard 44000 Nantes",
        code_insee="44109",
        coordonnees_lat=47.214972,
        coordonnees_lon=-1.551503,
        geocodage_score=0.55,
    )
    
    print(f"Profil for {profil.adresse}")
    print(f"Risques disponibles: {profil.list_risques_disponibles()}")
    print(f"Risques présents: {profil.list_risques_presents()}")
