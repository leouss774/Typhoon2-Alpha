"""
Export CZML — pipeline commun des simulations (Sprint 2 du plan
IMPLEMENTATION_cesium_hazards_sprint.md).

Brique partagee : prend la sortie d'un modele (grille 2D de valeurs par
pas de temps) et la transforme en document CZML 1.0 que CesiumJS anime
via Cesium.CzmlDataSource — meme mecanique pour l'inondation, le feu et
les mouvements de terrain, construite une fois, reutilisee trois fois.

   grid_timeseries_to_czml(grid, bbox, timestamps, value_to_color_fn)
       -> dict (document CZML complet)

Chaque cellule de la grille devient un polygone au sol (heightReference
CLAMP_TO_GROUND) dont la couleur de remplissage est echantillonnee dans le
temps (propriete `rgba` interpolee en LINEAR ou STEP selon l'alea). Les
cellules a valeur nulle sur toute la duree sont omises du document.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Sequence

# (r, g, b) en 0-255, a en 0-1 — signature imposee par le pipeline.
ValueToColorFn = Callable[[float, int, int, int], tuple[int, int, int, float]]


def _as_rows(grid: Sequence[Sequence[Sequence[float]]]) -> list[list[list[float]]]:
    """Normalise la grille en listes Python (accepte des arrays numpy)."""
    rows = []
    for t in grid:
        try:
            rows.append([list(r) for r in t.tolist()])  # numpy.ndarray
        except AttributeError:
            rows.append([list(r) for r in t])
    return rows


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cell_polygon_positions(
    west: float, south: float, east: float, north: float
) -> list[float]:
    """Rectangle WGS84 de la cellule → positions CZML (lon, lat, hauteur)."""
    return [
        west, south, 0,
        east, south, 0,
        east, north, 0,
        west, north, 0,
    ]


def grid_timeseries_to_czml(
    grid: Sequence[Sequence[Sequence[float]]],
    bbox: tuple[float, float, float, float],
    timestamps: Sequence[datetime],
    value_to_color_fn: ValueToColorFn,
    *,
    name: str = "Simulation",
    description: str = "",
    interpolation: str = "LINEAR",
    cell_start: Sequence[Sequence[int | None]] | None = None,
) -> dict:
    """
    Convertit une grille 2D par pas de temps en document CZML.

    Arguments
    ---------
    grid : grids[t][row][col] — valeur de l'alea a chaque pas de temps.
           La ligne 0 est au sud, la colonne 0 a l'ouest (bbox croissant).
    bbox : (ouest, sud, est, nord) en degres decimaux.
    timestamps : un instant ISO par pas de temps (len == len(grid)).
    value_to_color_fn(value, t, row, col) -> (r, g, b, a) — couleur RGBA
           (r,g,b en 0-255, a en 0-1) de la cellule a ce pas.
    interpolation : "LINEAR" (eau, glissement) ou "STEP" (front de feu).
    cell_start : par cellule, index du premier pas ou elle est visible
           (None = toute la duree). Sert a borner l'`availability` des
           cellules de feu pour ne pas animer 400 polygones des le depart.

    Retour : document CZML 1.0 pret pour Cesium.CzmlDataSource.load().
    """
    rows_2d = _as_rows(grid)
    n_steps = len(rows_2d)
    if n_steps == 0:
        raise ValueError("grille vide — aucun pas de temps")

    west, south, east, north = bbox
    n_rows = len(rows_2d[0])
    n_cols = len(rows_2d[0][0]) if n_rows else 0
    if n_rows == 0 or n_cols == 0:
        raise ValueError("grille degeneree — aucune cellule a exporter")

    t0 = _iso(timestamps[0])
    t1 = _iso(timestamps[-1])

    # Raster regulier : chaque cellule couvre (east-west)/n_cols x
    # (north-south)/n_rows degres.
    d_lon = (east - west) / n_cols
    d_lat = (north - south) / n_rows

    packets: list[dict] = []
    for row in range(n_rows):
        for col in range(n_cols):
            cell_w = west + col * d_lon
            cell_e = cell_w + d_lon
            cell_s = south + (n_rows - 1 - row) * d_lat
            cell_n = cell_s + d_lat

            samples: list[list] = []
            first_active: int | None = None
            for t in range(n_steps):
                value = float(rows_2d[t][row][col])
                if value <= 0.0:
                    continue
                r, g, b, a = value_to_color_fn(value, t, row, col)
                samples.append([_iso(timestamps[t]), r, g, b, a])
                if first_active is None:
                    first_active = t

            if not samples:
                continue  # cellule toujours nulle → pas de polygone

            start_idx = cell_start[row][col] if cell_start else None
            start = (
                _iso(timestamps[start_idx])
                if start_idx is not None and 0 <= start_idx < n_steps
                else t0
            )

            packets.append(
                {
                    "id": f"cell_r{row}_c{col}",
                    "availability": f"{start}/{t1}",
                    "polygon": {
                        "positions": _cell_polygon_positions(
                            cell_w, cell_s, cell_e, cell_n
                        ),
                        "height": 0,
                        "heightReference": "CLAMP_TO_GROUND",
                        "material": {
                            "solidColor": {
                                "color": {
                                    "rgba": samples,
                                    "interpolationAlgorithm": interpolation,
                                }
                            }
                        },
                    },
                }
            )

    return {
        "id": "document",
        "name": name,
        "version": "1.0",
        "description": description,
        "availability": f"{t0}/{t1}",
        "clock": {
            "interval": f"{t0}/{t1}",
            "currentTime": t0,
            "multiplier": 2,
            "range": "LOOP_STOP",
        },
        "packet": packets,
    }
