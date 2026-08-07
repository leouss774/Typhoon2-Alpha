"""
Moteur de simulation stylise (Sprint 2 du plan Cesium).

Cadre honnete : les vrais moteurs (SynxFlow, Cell2Fire, FlowPy) demandent
GPU CUDA et/ou des licences — voir §3-7 du plan. Ce module implemente les
replis proceduraux documentes (§3 « baignoire amelioree », §4 « automate »,
§5 « lobe gravitaire ») : des grilles 2D de valeurs par pas de temps,
calibrees sur la position et le niveau D03 du rapport. Le pipeline CZML
(Sprint 2) est cote `czml_export.grid_timeseries_to_czml` — independant du
moteur ; quand un vrai moteur sera branche, il suffira de remplacer la
fonction `build_grids_for_alea` par un appel au modele, la sortie (grille +
bbox + timestamps) etant identique.

Inondation : depuis l'integration RGE ALTI, la montee d'eau est contrainte
par le relief reel (MNT IGN — voir dem.py) quand il est disponible — les
vallees s'inondent en premier, les hauteurs restent seches — avec repli
sur le modele procedural si le MNT echoue (fail-soft). Les autres modeles
restent deterministes (bruit pseudo-aleatoire hache par cellule) et
hors-ligne.
"""

from __future__ import annotations

import hashlib
import heapq
import math
from datetime import datetime, timedelta, timezone
from typing import Callable, Sequence

from app.services.simulation.czml_export import grid_timeseries_to_czml

# ---------------------------------------------------------------------------
# Catalogue des aleas simulables — ce que le frontend affiche dans l'onglet
# « Vue terrain 3D », et ce que le endpoint POST /simulation/{aleas_code}
# accepte.
# ---------------------------------------------------------------------------

SIMULABLE_ALEAS: dict[str, dict] = {
    "inondation": {
        "libelle": "Inondation",
        "description": "Montée d'eau progressive contrainte par le relief réel RGE ALTI (IGN) — les zones basses s'inondent en premier (baignoire topographique, pas de vraie hydraulique).",
    },
    "feu_foret": {
        "libelle": "Feu de forêt",
        "description": "Propagation d'un front de flammes par automate cellulaire stylisé (vents dominants d'ouest).",
    },
    "mouvement_terrain": {
        "libelle": "Mouvement de terrain",
        "description": "Glissement d'une masse de sol le long de la pente (lobe gravitaire stylisé).",
    },
    "avalanche": {
        "libelle": "Avalanche",
        "description": "Coulée gravitaire rapide depuis le versant amont (même famille physique que le glissement).",
    },
    "vent_cyclonique": {
        "libelle": "Vent cyclonique",
        "description": "Champ de vent stylisé en spirale (visualisation, pas de CFD).",
    },
}

# ---------------------------------------------------------------------------
# Parametres communs de grille
# ---------------------------------------------------------------------------

GRID_N = 20              # 20x20 cellules (~1,8 km de cote a l'echelle du globe)
SPAN_DEG = 0.022         # largeur du raster en degres (~2,2 km en latitude)
N_STEPS = 25             # pas de temps
DURATION_S = 50.0        # duree de lecture de la simulation (secondes sim)

# Convention MNT (voir dem.py) : en dessous de ce seuil, un pixel est une
# valeur « no-data » (mer, hors couverture — RGE ALTI utilise -99999).
NO_DATA_THRESHOLD = -1000.0
# Hauteur d'eau max (m) pilotant l'étendue de crue : la montée est bornée
# à une profondeur de crue réaliste (quelques mètres → ~24 m) même quand
# l'emprise est montagneuse — sinon une fraction du relief total (p90−min
# ≈ 300 m en vallée alpine) produirait des crues de 150 m qui engloutissent
# tout le raster à n'importe quelle intensité.
MAX_RISE_SPAN_M = 24.0
# Dem.py remplace les pixels no-data par ce sentinelle (distinct du no-data
# brut) : le moteur sait ainsi quelles cellules sont « mer » — exclues des
# statistiques de relief mais submergees les premieres (elles jouent le
# niveau le plus bas).
SEA_SENTINEL = -9000.0

EPOCH = datetime(2026, 8, 7, tzinfo=timezone.utc)  # origine fixe (deterministe)

# Intensite par bande D03 — echelle de la simulation (pas le risque reel).
_NIVEAU_SCALE = {
    "tres_faible": 0.40,
    "faible": 0.55,
    "modere": 0.70,
    "eleve": 0.85,
    "critique": 1.00,
}


def _hash01(*values: float) -> float:
    """Bruit deterministe par cellule (meme simulation a chaque lecture)."""
    key = "|".join(f"{v:.6f}" for v in values).encode("utf-8")
    return int.from_bytes(hashlib.md5(key).digest()[:4], "little") / 2**32


def _niveau_scale(niveau: str | None, intensite: float | None = None) -> float:
    """Echelle d'intensite de la simulation. Si `intensite` (0..1, source
    manuelle placee sur le globe) est fournie, elle prime sur la bande D03."""
    if intensite is not None:
        return max(0.05, min(1.0, float(intensite)))
    return _NIVEAU_SCALE.get(niveau or "", 0.70)


def _timestamps() -> list[datetime]:
    step = DURATION_S / (N_STEPS - 1)
    return [EPOCH + timedelta(seconds=step * t) for t in range(N_STEPS)]


def _bbox(lat: float, lon: float) -> tuple[float, float, float, float]:
    half = SPAN_DEG / 2
    return (lon - half, lat - half, lon + half, lat + half)


def _cell_center(
    row: int, col: int, bbox: tuple[float, float, float, float]
) -> tuple[float, float]:
    """(lat, lon) du centre de la cellule (ligne 0 = sud, colonne 0 = ouest)."""
    west, south, east, north = bbox
    d_lat = (north - south) / GRID_N
    d_lon = (east - west) / GRID_N
    lat = south + (GRID_N - 1 - row + 0.5) * d_lat
    lon = west + (col + 0.5) * d_lon
    return lat, lon


# ---------------------------------------------------------------------------
# Modeles par alea — chacun renvoie (grids, bbox, timestamps, color_fn,
# interpolation, cell_start) pour grid_timeseries_to_czml.
# ---------------------------------------------------------------------------

def _inondation(
    lat: float,
    lon: float,
    niveau: str | None,
    dem: Sequence[Sequence[float]] | None = None,
    *,
    source_lat: float | None = None,
    source_lon: float | None = None,
    intensite: float | None = None,
):
    """Montée d'eau contrainte par le relief réel (RGE ALTI).

    Deux variantes selon la présence d'une source manuelle (l'utilisateur
    clique un point sur le globe — cf. onglet « Vue terrain 3D ») :

    · `source_lat`/`source_lon` fournis + MNT → `_inondation_dem_source` :
      l'eau PART du point cliqué et se propage par le relief (priority
      flood) — les vallées accessibles s'inondent au fil de la montée, les
      crêtes la bloquent tant que le niveau n'a pas franchi le col.
    · MNT seul → « baignoire topographique » (`_inondation_dem`) : le
      niveau W(t) monte partout et une cellule est submergée quand son
      altitude passe sous W(t).

    Sans MNT (indisponible), repli sur l'ancien modèle procedural à
    proximité de rivière simulée (fail-soft — jamais de trou dans l'UI).
    """
    if dem is not None and source_lat is not None and source_lon is not None:
        return _inondation_dem_source(lat, lon, niveau, dem, source_lat, source_lon, intensite)
    if dem is not None:
        return _inondation_dem(lat, lon, niveau, dem)
    return _inondation_procedural(lat, lon, niveau)


def _inondation_dem_source(
    lat: float,
    lon: float,
    niveau: str | None,
    dem: Sequence[Sequence[float]],
    source_lat: float,
    source_lon: float,
    intensite: float | None = None,
):
    """Inondation pilotée par une SOURCE MANUELLE (point cliqué sur le globe).

    Le raster est recentré sur la source. On calcule pour chaque cellule son
    « niveau de débordement » (spill) : la plus petite cote d'eau à laquelle
    la source peut l'atteindre — l'altitude maximale le long du chemin de
    moindre coût (priority flood / Dijkstra sur l'altitude). Le niveau d'eau
    monte dans le temps : une cellule s'inonde quand W(t) ≥ spill, ce qui
    produit un écoulement réaliste — l'eau suit les vallées accessibles,
    stagne contre une crête, puis la franchit quand la cote atteint le col.

    `intensite` (0..1) pilote la hauteur finale d'eau au-dessus de la source
    (repli sur la bande D03 si None).
    """
    bbox = _bbox(source_lat, source_lon)
    west, south, east, north = bbox
    d_lat = (north - south) / GRID_N
    d_lon = (east - west) / GRID_N

    # Cellule du raster la plus proche de la source cliquée.
    row = GRID_N - 1 - int(round((source_lat - south) / d_lat))
    col = int(round((source_lon - west) / d_lon))
    row = max(0, min(GRID_N - 1, row))
    col = max(0, min(GRID_N - 1, col))
    scale = _niveau_scale(niveau, intensite)

    # Statistiques de relief sur la terre ferme (la mer est exclue, cf. dem.py).
    land = [float(v) for r in dem for v in r if v >= NO_DATA_THRESHOLD]
    if not land:
        return _inondation_procedural(lat, lon, niveau)
    dem_min = min(land)
    dem_p90 = sorted(land)[int(len(land) * 0.90)]

    # Cote de départ : la source (ou le fond du terrain si la source est en
    # mer) ; l'eau monte de `rise_span` au-dessus — une profondeur de crue
    # realiste (MAX_RISE_SPAN_M max), modulee par l'intensite choisie, pas
    # une fraction du relief total de l'emprise.
    src_elev = float(dem[row][col])
    if src_elev < NO_DATA_THRESHOLD:
        src_elev = dem_min
    rise_span = min(max(dem_p90 - dem_min, 2.0), MAX_RISE_SPAN_M) * scale
    max_depth = max(rise_span, 0.5)

    # Priority flood depuis la source : spill[r][c] = cote minimale à laquelle
    # la source atteint la cellule. La mer (sentinelle) est toujours franchissable.
    spill: list[list[float]] = [[float("inf")] * GRID_N for _ in range(GRID_N)]
    heap: list[tuple[float, int, int]] = [(src_elev, row, col)]
    spill[row][col] = src_elev
    while heap:
        level, r, c = heapq.heappop(heap)
        if level > spill[r][c]:
            continue
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = r + dr, c + dc
            if 0 <= nr < GRID_N and 0 <= nc < GRID_N:
                elev = float(dem[nr][nc])
                if elev < NO_DATA_THRESHOLD:
                    elev = -9999.0  # mer : submergée dès que connectée
                nlevel = max(level, elev)
                if nlevel < spill[nr][nc]:
                    spill[nr][nc] = nlevel
                    heapq.heappush(heap, (nlevel, nr, nc))

    def water_level(t: int) -> float:
        # Courbe d'ease-out qui atteint EXACTEMENT le niveau cible au dernier
        # pas (rise = 1.0 a t = N_STEPS-1) : le front termine sa propagation.
        delay = N_STEPS * 0.08
        rise = max(0.0, (t - delay) / ((N_STEPS - 1) - delay))
        return src_elev + rise_span * (rise**1.3)

    grids: list[list[list[float]]] = []
    cell_start: list[list[int | None]] = [[None] * GRID_N for _ in range(GRID_N)]
    for t in range(N_STEPS):
        w = water_level(t)
        grid: list[list[float]] = []
        for r in range(GRID_N):
            line: list[float] = []
            for c in range(GRID_N):
                if w >= spill[r][c]:
                    elev = float(dem[r][c])
                    ground = SEA_SENTINEL if elev < NO_DATA_THRESHOLD else elev
                    depth = w - ground
                    line.append(max(0.0, min(1.0, depth / max_depth)))
                    if cell_start[r][c] is None:
                        cell_start[r][c] = t
                else:
                    line.append(0.0)
            grid.append(line)
        grids.append(grid)

    def color(v: float, t: int, row: int, col: int):
        r = int(18 + 95 * v)
        g = int(60 + 120 * v)
        b = int(150 + 85 * v)
        return (r, g, b, 0.45 + 0.5 * v)

    return grids, bbox, _timestamps(), color, "LINEAR", cell_start


def _inondation_dem(
    lat: float, lon: float, niveau: str | None, dem: Sequence[Sequence[float]]
):
    bbox = _bbox(lat, lon)
    scale = _niveau_scale(niveau)

    # Statistiques de relief sur la TERRE FERME uniquement : les cellules
    # « mer » (sentinelle SEA_SENTINEL, cf. dem.py) sont exclues — sinon un
    # bbox cotier majoritairement en mer ecraserait le p90 et la montee
    # d'eau serait independante du niveau D03.
    land = [float(v) for row in dem for v in row if v >= NO_DATA_THRESHOLD]
    if not land:
        return _inondation_procedural(lat, lon, niveau)
    dem_min = min(land)
    dem_p90 = sorted(land)[int(len(land) * 0.90)]
    spread = max(min(dem_p90 - dem_min, MAX_RISE_SPAN_M), 1.0)

    # Niveau d'eau cible : montee bornee a une profondeur de crue realiste
    # (MAX_RISE_SPAN_M), modulee par l'intensite D03 (scale 0.4 → 40 %).
    target = dem_min + spread * scale
    max_depth = max(target - dem_min, 1.0)

    def water_level(t: int) -> float:
        # Debut differe (l'eau monte apres ~10 % de la duree), montee assouplie.
        rise = max(0.0, (t - N_STEPS * 0.10) / (N_STEPS * 0.90))
        return dem_min + (target - dem_min) * (rise**1.4)

    grids: list[list[list[float]]] = []
    for t in range(N_STEPS):
        w = water_level(t)
        grid: list[list[float]] = []
        for row in range(GRID_N):
            line: list[float] = []
            for col in range(GRID_N):
                # La mer joue le niveau le plus bas : submergee des la montee.
                elev = SEA_SENTINEL if dem[row][col] < NO_DATA_THRESHOLD else dem[row][col]
                depth = w - elev
                # Valeur normalisee 0..1 : profondeur relative a la profondeur
                # max (0 = cellule seche, 1 = fond de vallee / mer).
                line.append(max(0.0, min(1.0, depth / max_depth)))
            grid.append(line)
        grids.append(grid)

    def color(v: float, t: int, row: int, col: int):
        r = int(18 + 95 * v)
        g = int(60 + 120 * v)
        b = int(150 + 85 * v)
        return (r, g, b, 0.45 + 0.5 * v)

    return grids, bbox, _timestamps(), color, "LINEAR", None


def _inondation_procedural(lat: float, lon: float, niveau: str | None):
    """Repli procedural (MNT indisponible) : « baignoire » amelioree —
    l'eau monte depuis une riviere sinueuse (et le point bas de l'adresse),
    contrainte par une proximite spatiale, sans relief reel."""
    bbox = _bbox(lat, lon)
    west, south, east, north = bbox
    scale = _niveau_scale(niveau)

    grids: list[list[list[float]]] = []
    for t in range(N_STEPS):
        rise = max(0.0, (t - N_STEPS * 0.15) / (N_STEPS * 0.85))  # debut differe
        grid: list[list[float]] = []
        for row in range(GRID_N):
            line: list[float] = []
            for col in range(GRID_N):
                c_lat, c_lon = _cell_center(row, col, bbox)
                # Riviere sinueuse traversant le raster d'ouest en est.
                x_norm = (c_lon - west) / (east - west)
                river_lat = south + (north - south) * (
                    0.5 + 0.38 * math.sin(2 * math.pi * x_norm * 1.6 + 0.8)
                )
                d_river_deg = abs(c_lat - river_lat)
                proximity = math.exp(-((d_river_deg / (SPAN_DEG * 0.16)) ** 2))
                # Le point d'adresse est aussi une zone basse (remontee locale).
                d_addr_deg = math.hypot(c_lat - lat, c_lon - lon)
                local = math.exp(-((d_addr_deg / (SPAN_DEG * 0.18)) ** 2))
                depth = (
                    (proximity * 0.85 + local * 0.45)
                    * rise**1.4
                    * (0.65 + 0.6 * _hash01(row, col))
                    * scale
                )
                line.append(max(0.0, min(1.0, depth)))
            grid.append(line)
        grids.append(grid)

    def color(v: float, t: int, row: int, col: int):
        r = int(18 + 95 * v)
        g = int(60 + 120 * v)
        b = int(150 + 85 * v)
        return (r, g, b, 0.45 + 0.5 * v)

    return grids, bbox, _timestamps(), color, "LINEAR", None


def _feu_foret(lat: float, lon: float, niveau: str | None):
    """Automate stylise : temps d'allumage par cellule = distance a
    l'ignition (l'adresse), accelere dans la direction du vent dominant
    (ouest → est) + bruit. STEP en interpolation : un front net."""
    bbox = _bbox(lat, lon)
    west, south, east, north = bbox
    scale = _niveau_scale(niveau)

    burn_time: list[list[int]] = []
    for row in range(GRID_N):
        line: list[int] = []
        for col in range(GRID_N):
            c_lat, c_lon = _cell_center(row, col, bbox)
            d_deg = math.hypot(c_lat - lat, c_lon - lon)
            # Vent d'ouest : les cellules a l'est de l'ignition brulent plus vite.
            wind = 1.0 - 0.45 * max(0.0, (c_lon - lon) / SPAN_DEG)
            base = (d_deg / SPAN_DEG) * N_STEPS * 0.9 * wind
            line.append(int(round(max(0, base + _hash01(row, col, 7) * 3 - 1))))
        burn_time.append(line)

    grids: list[list[list[float]]] = []
    for t in range(N_STEPS):
        grid: list[list[float]] = []
        for row in range(GRID_N):
            line: list[float] = []
            for col in range(GRID_N):
                delta = t - burn_time[row][col]
                # Ramp 0.3→1.0 sur ~4 pas apres l'allumage (STEP garde le front).
                line.append(max(0.0, min(1.0, (0.35 + 0.65 * min(delta / 4, 1.0)) * scale)))
            grid.append(line)
        grids.append(grid)

    def color(v: float, t: int, row: int, col: int):
        r = int(140 + 115 * v)
        g = int(60 - 40 * v)
        b = int(20 - 10 * v)
        return (r, g, b, 0.35 + 0.55 * v)

    return grids, bbox, _timestamps(), color, "STEP", burn_time


def _lobe(
    lat: float,
    lon: float,
    niveau: str | None,
    *,
    dlat_step: float,
    dlon_step: float,
    radius: float,
    colors: tuple[tuple[int, int, int], tuple[int, int, int]],
    name: str,
):
    """Familie gravitaire commune (mouvement de terrain / avalanche) : un
    lobe de densite gaussienne qui se deplace le long de la pente."""
    bbox = _bbox(lat, lon)
    scale = _niveau_scale(niveau)

    grids: list[list[list[float]]] = []
    for t in range(N_STEPS):
        # Le lobe part en amont et glisse vers le point d'adresse.
        f = t / (N_STEPS - 1)
        center_lat = lat + dlat_step * (1.0 - f)
        center_lon = lon + dlon_step * (1.0 - f)
        grid: list[list[float]] = []
        for row in range(GRID_N):
            line: list[float] = []
            for col in range(GRID_N):
                c_lat, c_lon = _cell_center(row, col, bbox)
                d_deg = math.hypot(c_lat - center_lat, c_lon - center_lon)
                v = math.exp(-((d_deg / radius) ** 2)) * scale
                line.append(max(0.0, min(1.0, v)))
            grid.append(line)
        grids.append(grid)

    c0, c1 = colors

    def color(v: float, t: int, row: int, col: int):
        r = int(c0[0] + (c1[0] - c0[0]) * v)
        g = int(c0[1] + (c1[1] - c0[1]) * v)
        b = int(c0[2] + (c1[2] - c0[2]) * v)
        return (r, g, b, 0.55 + 0.4 * v)

    return grids, bbox, _timestamps(), color, "LINEAR", None


def _mouvement_terrain(lat: float, lon: float, niveau: str | None):
    return _lobe(
        lat, lon, niveau,
        dlat_step=-0.0035,   # lobe part au sud de l'adresse, remonte vers elle
        dlon_step=-0.0035,   # (idem en longitude : le lobe converge sur le bien)
        radius=SPAN_DEG * 0.16,
        colors=((160, 110, 60), (120, 60, 25)),
        name="Mouvement de terrain",
    )


def _avalanche(lat: float, lon: float, niveau: str | None):
    return _lobe(
        lat, lon, niveau,
        dlat_step=0.0045,    # part du versant amont (nord)
        dlon_step=-0.0040,   # descend vers le sud-ouest
        radius=SPAN_DEG * 0.11,
        colors=((210, 225, 245), (150, 175, 215)),  # blanc/bleu glace
        name="Avalanche",
    )


def _vent_cyclonique(lat: float, lon: float, niveau: str | None):
    """Champ de vent stylise : spirale tournante autour du point d'adresse,
    intensite pulsante — visualisation, pas un modele CFD (cf. §8 du plan)."""
    bbox = _bbox(lat, lon)
    scale = _niveau_scale(niveau)

    grids: list[list[list[float]]] = []
    for t in range(N_STEPS):
        phase = t / (N_STEPS - 1) * 2 * math.pi * 2.2
        grid: list[list[float]] = []
        for row in range(GRID_N):
            line: list[float] = []
            for col in range(GRID_N):
                c_lat, c_lon = _cell_center(row, col, bbox)
                d_deg = math.hypot(c_lat - lat, c_lon - lon)
                ang = math.atan2(c_lat - lat, c_lon - lon)
                falloff = math.exp(-((d_deg / (SPAN_DEG * 0.4)) ** 2))
                swirl = 0.5 + 0.5 * math.sin(ang * 3.0 + phase + d_deg * 220)
                line.append(max(0.0, min(1.0, swirl * falloff * scale)))
            grid.append(line)
        grids.append(grid)

    def color(v: float, t: int, row: int, col: int):
        r = int(60 + 90 * v)
        g = int(170 + 40 * v)
        b = int(200 - 60 * v)
        return (r, g, b, 0.2 + 0.45 * v)

    return grids, bbox, _timestamps(), color, "LINEAR", None


# ---------------------------------------------------------------------------
# Point d'entree unique du pipeline
# ---------------------------------------------------------------------------

def build_czml_for_alea(
    aleas_code: str,
    lat: float,
    lon: float,
    niveau: str | None,
    dem: Sequence[Sequence[float]] | None = None,
    *,
    source_lat: float | None = None,
    source_lon: float | None = None,
    intensite: float | None = None,
) -> dict:
    """
    Construit le document CZML complet de la simulation pour un alea donne.

    `dem` : grille d'altitudes RGE ALTI (alignee sur le raster du moteur) —
    consommee uniquement par l'inondation (baignoire topographique, ou
    propagation depuis une source manuelle si `source_lat`/`source_lon`
    sont fournis) ; les autres aleas l'ignorent. None → repli procedural.

    `intensite` (0..1) : pour l'inondation pilotee par une source manuelle,
    la hauteur finale d'eau au-dessus de la source (primes sur la bande D03).

    Leve ValueError si l'alea n'est pas simulable (le routeur retourne alors
    un 404/422). Hors-ligne hors MNT optionnel.
    """
    if aleas_code not in SIMULABLE_ALEAS:
        raise ValueError(
            f"alea non simulable: {aleas_code} (simulables: {', '.join(sorted(SIMULABLE_ALEAS))})"
        )

    builders: dict[str, Callable[..., tuple]] = {
        "feu_foret": _feu_foret,
        "mouvement_terrain": _mouvement_terrain,
        "avalanche": _avalanche,
        "vent_cyclonique": _vent_cyclonique,
    }
    if aleas_code == "inondation":
        grids, bbox, timestamps, color, interpolation, cell_start = _inondation(
            lat, lon, niveau, dem,
            source_lat=source_lat, source_lon=source_lon, intensite=intensite,
        )
    else:
        grids, bbox, timestamps, color, interpolation, cell_start = builders[aleas_code](
            lat, lon, niveau
        )
    meta = SIMULABLE_ALEAS[aleas_code]

    description = meta["description"]
    # La note « source manuelle » n'a de sens que pour l'inondation : les
    # autres aleas ignorent la source (le routeur accepte les champs mais le
    # moteur ne les consomme pas) — ne pas mentir dans les métadonnées CZML.
    if aleas_code == "inondation" and source_lat is not None and source_lon is not None:
        description += (
            " Source placée manuellement sur le globe — l'eau part du point "
            "cliqué et se propage par le relief (priority flood sur le MNT RGE ALTI)."
        )

    return grid_timeseries_to_czml(
        grids,
        bbox,
        timestamps,
        color,
        name=meta["libelle"],
        description=description,
        interpolation=interpolation,
        cell_start=cell_start,
    )
