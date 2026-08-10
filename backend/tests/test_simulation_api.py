"""
Tests du pipeline CZML (Sprint 2) :
  - unitaire : grid_timeseries_to_czml transforme une grille 2D par pas de
    temps en document CZML 1.0 (polygones au sol, couleur echantillonnee
    dans le temps, cellules nulles omises) ;
  - endpoint : POST /diagnostic/adresse/simulation/{aleas_code} → 202 + job,
    le job passe a "ready" en arriere-plan, GET czml renvoie le document ;
  - alea inconnu → 404.

A executer :
    cd backend && PYTHONPATH=. python -m pytest tests/test_simulation_api.py -q
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.services.simulation.czml_export import grid_timeseries_to_czml

EPOCH = datetime(2026, 8, 7, tzinfo=timezone.utc)


def asyncio_run(coro):
    """Exécute une coroutine hors du contexte TestClient (tests unitaires)."""
    return asyncio.run(coro)

# MNT plat artificiel (20x20) : le moteur doit produire des polygones sans
# toucher au reseau IGN (tests hermétiques).
def _flat_dem(value: float = 10.0):
    return [[value for _ in range(20)] for _ in range(20)]


def _ts(n: int) -> list[datetime]:
    return [EPOCH + timedelta(seconds=10 * t) for t in range(n)]


def _linear_color(value: float, t: int, row: int, col: int):
    return (10, 100, 200, 0.5)


# ---------------------------------------------------------------------------
# Unitaire — export CZML
# ---------------------------------------------------------------------------

def test_grid_timeseries_to_czml_structure():
    """Grille 2x2 sur 3 pas de temps → document CZML avec 4 polygones au
    sol, 3 echantillons rgba chacun, positions rectangle correctes."""
    grid = [
        [[0.0, 0.5], [0.2, 0.8]],
        [[0.0, 0.6], [0.4, 1.0]],
        [[0.0, 0.7], [0.6, 1.0]],
    ]
    czml = grid_timeseries_to_czml(
        grid,
        (7.0, 43.0, 7.1, 43.1),
        _ts(3),
        _linear_color,
        name="Test",
    )

    assert czml["id"] == "document"
    assert czml["version"] == "1.0"
    assert czml["name"] == "Test"
    assert czml["clock"]["range"] == "LOOP_STOP"
    assert czml["clock"]["multiplier"] == 2
    assert czml["availability"] == "2026-08-07T00:00:00Z/2026-08-07T00:00:20Z"

    packets = czml["packet"]
    # La cellule (0,0) reste a 0.0 : elle doit etre omise.
    assert len(packets) == 3
    for packet in packets:
        assert "r" in packet["id"] and "c" in packet["id"]
        poly = packet["polygon"]
        assert poly["heightReference"] == "CLAMP_TO_GROUND"
        assert len(poly["positions"]) == 12  # 4 sommets x (lon, lat, h)
        rgba = poly["material"]["solidColor"]["color"]["rgba"]
        assert len(rgba) == 3, "un echantillon par pas de temps"
        for sample in rgba:
            assert len(sample) == 5  # [time, r, g, b, a]
            assert sample[1] == 10 and sample[2] == 100 and sample[3] == 200


def test_grid_timeseries_to_czml_zero_grid_omits_cells():
    """Grille entierement nulle → aucun polygone (pas de bruit visuel)."""
    grid = [[[0.0, 0.0], [0.0, 0.0]], [[0.0, 0.0], [0.0, 0.0]]]
    czml = grid_timeseries_to_czml(grid, (0.0, 0.0, 0.1, 0.1), _ts(2), _linear_color)
    assert czml["packet"] == []


def test_grid_timeseries_to_czml_accepte_numpy():
    """Le pipeline accepte des arrays numpy (sortie type des vrais moteurs)."""
    import numpy as np

    grid = [np.array([[0.0, 1.0], [0.5, 0.0]]), np.array([[0.0, 0.9], [0.4, 0.0]])]
    czml = grid_timeseries_to_czml(grid, (0.0, 0.0, 0.1, 0.1), _ts(2), _linear_color)
    assert len(czml["packet"]) == 2


# ---------------------------------------------------------------------------
# Endpoint — job asynchrone + polling
# ---------------------------------------------------------------------------

def _wait_ready(client: TestClient, job_id: str, timeout_s: float = 10.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/diagnostic/adresse/simulation/jobs/{job_id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if body["status"] in ("ready", "error"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} toujours pas termine apres {timeout_s}s")


def test_simulation_job_flow_inondation():
    """POST inondation → 202 ; le job passe ready ; czml_url sert un
    document CZML avec des polygones et une clock jouable.

    Le MNT RGE ALTI est mocke (grille plate) : le test ne depend ni du
    reseau IGN ni du cache. Tout le flux vit dans UN SEUL contexte
    TestClient : le job tourne en arriere-plan sur la boucle du client —
    fermer le contexte (nouvelle boucle) annulerait la task asyncio avant
    sa fin."""
    from app.main import app

    with patch("app.services.simulation.jobs.fetch_dem_for_bbox", return_value=_flat_dem()):
        with TestClient(app) as client:
            resp = client.post(
                "/diagnostic/adresse/simulation/inondation",
                json={"lat": 43.695, "lon": 7.265, "code_insee": "06088", "niveau": "modere"},
            )
            assert resp.status_code == 202, resp.text
            job = resp.json()
            assert job["status"] == "queued"
            assert job["poll_url"].endswith(job["job_id"])

            done = _wait_ready(client, job["job_id"])
            assert done["status"] == "ready", done
            assert done["czml_url"].endswith("/czml")

            czml_resp = client.get(done["czml_url"])
            assert czml_resp.status_code == 200, czml_resp.text
            czml = czml_resp.json()
            assert czml["id"] == "document"
            assert "clock" in czml
            assert len(czml["packet"]) > 0, "au moins une cellule d'eau"
            # La plupart des cellules doivent finir actives (montee generalisee)
            assert czml["packet"][0]["polygon"]["heightReference"] == "CLAMP_TO_GROUND"


def test_simulation_inondation_fallback_sans_mnt():
    """MNT indisponible → repli procedural (fail-soft) : le job reste ready
    avec des polygones — jamais une erreur pour cause de relief manquant."""
    from app.main import app

    with patch("app.services.simulation.jobs.fetch_dem_for_bbox", return_value=None):
        with TestClient(app) as client:
            resp = client.post(
                "/diagnostic/adresse/simulation/inondation",
                json={"lat": 43.695, "lon": 7.265, "niveau": "eleve"},
            )
            assert resp.status_code == 202, resp.text
            done = _wait_ready(client, resp.json()["job_id"])
            assert done["status"] == "ready", done
            czml = client.get(done["czml_url"]).json()

    assert len(czml["packet"]) > 0


def test_inondation_dem_baignoire_topographique():
    """Avec un MNT en forme de vallée (altitude croissante hors de la
    vallée), l'eau submerge d'abord le fond de vallée et laisse les
    hauteurs sèches — c'est le relief qui dessine l'étendue d'eau."""
    from app.services.simulation.engine import _inondation, GRID_N

    # Vallée verticale le long de la colonne 10 : elev = 5 + 2*|col-10|.
    dem = [[5.0 + 2.0 * abs(col - 10) for col in range(GRID_N)] for _ in range(GRID_N)]
    grids, bbox, timestamps, color, interpolation, _ = _inondation(
        43.695, 7.265, "critique", dem
    )

    assert len(grids) == 25
    # t=0 : l'eau n'a pas encore monté (rien de submergé).
    assert all(v == 0.0 for row in grids[0] for v in row)

    last = grids[-1]
    # Fond de vallée : inondé, profondeur relative maximale.
    assert last[10][10] > 0.9
    # Hauteurs (colonnes 0 et 19, elev 25) : au-dessus du niveau d'eau.
    assert last[10][0] == 0.0
    assert last[10][19] == 0.0
    # Profondeur decroissante du fond de vallee vers les flancs.
    assert last[10][12] < last[10][11] < last[10][10]
    assert last[10][8] > last[10][5] > 0.0

    # Les couleurs suivent la profondeur : fond de vallee plus opaque/bleue.
    _, _, _, a_bottom = color(1.0, 24, 10, 10)
    _, _, _, a_dry = color(0.0, 24, 10, 0)
    assert a_bottom > a_dry


def test_inondation_dem_cotier_mer_exclue_des_stats():
    """Un bbox cotier avec des cellules « mer » (sentinelle SEA_SENTINEL) :
    la mer est submergee a pleine profondeur, mais les statistiques de
    relief (p90 → niveau d'eau cible) se calculent sur la terre ferme —
    sinon une mer majoritaire ecraserait la montee."""
    from app.services.simulation.engine import (
        _inondation,
        GRID_N,
        NO_DATA_THRESHOLD,
        SEA_SENTINEL,
    )

    # Vallee (comme le test precedent) + moitie basse (lignes 0-9) remplie
    # de « mer » (sentinelle) : 50 % du raster, comme une vraie cote.
    dem = [[5.0 + 2.0 * abs(col - 10) for col in range(GRID_N)] for _ in range(GRID_N)]
    for row in range(0, GRID_N // 2):
        dem[row] = [SEA_SENTINEL] * GRID_N

    grids, _, _, _, _, _ = _inondation(43.695, 7.265, "critique", dem)
    last = grids[-1]
    # La mer : submergee a profondeur maximale des le depart.
    assert last[0][0] == 1.0
    assert last[5][10] == 1.0
    # La terre ferme reste pilotee par le relief : fond de vallee inonde,
    # hauteurs seches (le p90 n'est pas ecrase par les 50 % de mer).
    assert last[15][10] > 0.9
    assert last[15][0] == 0.0
    assert SEA_SENTINEL < NO_DATA_THRESHOLD < 0  # sentinelle sous le seuil no-data


def test_inondation_dem_source_priority_flood():
    """Source manuelle : l'eau part du point cliqué et se propage par le
    relief (priority flood). Un bassin (10 m) séparé d'une vallée basse
    (10 m) par une crête de 12 m : à faible intensité la crête bloque,
    à pleine intensité le niveau franchit le col et la vallée s'inonde
    (et elle s'inonde APRÈS le bassin — le front se propage)."""
    from app.services.simulation.engine import _inondation, GRID_N

    # Lignes 0-9 : bassin à 10 m ; ligne 10 : crête à 11,5 m ; lignes 11-19 :
    # vallée au-delà de la crête, à 10 m (le p90 du raster reste à 10 m :
    # la crête n'écrase pas la cote cible).
    dem = []
    for row in range(GRID_N):
        dem.append([10.0 if row < 10 else (11.5 if row == 10 else 10.0)] * GRID_N)

    # La source est cliquée au centre du bassin (cellule 9,10 avec le bbox
    # centré sur la source — la colonne 10 est l'axe central du raster).
    lat = lon = 43.6

    # -- Faible intensité : la crête (11,5 m) reste au-dessus du niveau final. --
    grids_low, bbox, _, _, _, cell_start_low = _inondation(
        lat, lon, None, dem, source_lat=lat, source_lon=lon, intensite=0.3
    )
    last_low = grids_low[-1]
    assert last_low[3][3] > 0.0, "le bassin (côté source) doit s'inonder"
    assert last_low[10][10] == 0.0, "la crête bloque à faible intensité"
    assert last_low[15][10] == 0.0, "la vallée derrière la crête reste sèche"

    # -- Pleine intensité : le niveau atteint le col (12 m) et franchit. --
    grids, bbox, _, _, _, cell_start = _inondation(
        lat, lon, None, dem, source_lat=lat, source_lon=lon, intensite=1.0
    )
    last = grids[-1]
    assert last[3][3] > 0.0
    assert last[10][10] > 0.0, "la crête est franchie à pleine intensité"
    assert last[15][10] > 0.0, "la vallée au-delà de la crête s'inonde"

    # Le front se propage : la source est submergée dès t=0, la vallée
    # au-delà de la crête seulement après que le niveau a franchi le col.
    assert cell_start[3][3] == 0
    assert cell_start[15][10] > 0, "la vallée doit s'inonder après le bassin"
    assert cell_start[15][10] >= cell_start[10][10], "la crête avant la vallée"

    # À un instant intermédiaire : bassin déjà sous l'eau, vallée pas encore.
    grids_mid = grids[10]
    assert grids_mid[3][3] > 0.0 and grids_mid[15][10] == 0.0

    # Le raster est recentré sur la source (bbox centré sur elle).
    west, south, east, north = bbox
    assert abs((west + east) / 2 - lon) < 1e-6
    assert abs((south + north) / 2 - lat) < 1e-6


def test_simulation_source_api_flow():
    """POST inondation avec source manuelle + intensité → job ready, CZML
    avec polygones, description mentionnant la source. Une source partielle
    (lat sans lon) → 422."""
    from app.main import app

    with patch("app.services.simulation.jobs.fetch_dem_for_bbox", return_value=_flat_dem()):
        with TestClient(app) as client:
            resp = client.post(
                "/diagnostic/adresse/simulation/inondation",
                json={
                    "lat": 43.695, "lon": 7.265,
                    "source_lat": 43.700, "source_lon": 7.260,
                    "intensite": 0.8,
                },
            )
            assert resp.status_code == 202, resp.text
            done = _wait_ready(client, resp.json()["job_id"])
            assert done["status"] == "ready", done

            czml = client.get(done["czml_url"]).json()
            assert len(czml["packet"]) > 0
            assert "source" in czml["description"].lower()

            # Source partielle (lat sans lon) → 422 explicite.
            bad = client.post(
                "/diagnostic/adresse/simulation/inondation",
                json={"lat": 43.695, "lon": 7.265, "source_lat": 43.7},
            )
            assert bad.status_code == 422, bad.text
            assert bad.json()["detail"]["error"] == "source_incomplete"


def _build_float_tiff(width: int, height: int, values, bits: int = 32, sample_format: int = 3) -> bytes:
    """GeoTIFF minimal : bande unique non compressée, little-endian.
    Ligne 0 du TIFF = nord (convention TIFF) — le parseur doit la retourner
    en derniere ligne (moteur : lignes[0] = sud). Par défaut Float32 ;
    bits=16 + sample_format=1 → Int16 non signé."""
    import struct as s

    fmt = "<%df" % (width * height) if bits == 32 else "<%dH" % (width * height)
    strip = s.pack(fmt, *values)
    entries = [
        (256, 4, 1, width),            # ImageWidth
        (257, 4, 1, height),           # ImageLength
        (258, 3, 1, bits),             # BitsPerSample
        (259, 3, 1, 1),                # Compression = 1 (aucune)
        (262, 3, 1, 1),                # Photometric = BlackIsZero
        (273, 4, 1, 0),                # StripOffsets (corrige ci-dessous)
        (277, 3, 1, 1),                # SamplesPerPixel
        (278, 4, 1, height),           # RowsPerStrip
        (279, 4, 1, len(strip)),       # StripByteCounts
        (339, 3, 1, sample_format),    # SampleFormat
    ]
    ifd_size = 2 + 12 * len(entries) + 4
    strip_offset = 8 + ifd_size
    ifd_entries = b""
    for tag, typ, count, val in entries:
        raw = s.pack("<I", strip_offset) if typ == 4 and tag == 273 else (
            s.pack("<H", val) + b"\x00\x00" if typ == 3 else s.pack("<I", val)
        )
        ifd_entries += s.pack("<HHI", tag, typ, count) + raw
    ifd = s.pack("<H", len(entries)) + ifd_entries + s.pack("<I", 0)
    return b"II*\x00" + s.pack("<I", 8) + ifd + strip


def test_dem_parse_tiff_sud_premier():
    """Le parseur GeoTIFF renvoie la grille avec lignes[0] = SUD (le TIFF
    stocke du nord au sud) — aligne sur le raster du moteur. Float32 comme
    Int16 sont supportes."""
    from app.services.simulation.dem import _parse_tiff

    tiff = _build_float_tiff(2, 2, [1.0, 2.0, 3.0, 4.0])  # nord: [1,2], sud: [3,4]
    grid = _parse_tiff(tiff, 2, 2)
    assert grid == [[3.0, 4.0], [1.0, 2.0]]

    # Int16 non signe (format courant des MNT) : valeurs correctes.
    tiff16 = _build_float_tiff(2, 2, [10, 20, 30, 40], bits=16, sample_format=1)
    assert _parse_tiff(tiff16, 2, 2) == [[30.0, 40.0], [10.0, 20.0]]

    # Format inexploitable (pas un TIFF, taille inattendue, compression) → None
    assert _parse_tiff(b"<html>erreur</html>", 2, 2) is None
    assert _parse_tiff(_build_float_tiff(4, 4, [0.0] * 16), 2, 2) is None


def test_dem_fetch_tiff_et_echec():
    """fetch_dem_for_bbox : une seule requete GetMap GeoTIFF → grille
    d'altitudes ; reponse non-TIFF → None (repli procedural)."""
    import app.services.simulation.dem as dem_mod
    from app.services.simulation.engine import GRID_N

    dem_mod._DEM_CACHE.clear()
    n = GRID_N * GRID_N
    tiff = _build_float_tiff(GRID_N, GRID_N, [10.0 + i % 7 for i in range(n)])
    calls = {"n": 0}

    class FakeResp:
        def __init__(self, content):
            self.content = content
            self.status_code = 200

        def raise_for_status(self):
            pass

    class FakeClient:
        def __init__(self, content):
            self.content = content

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **k):
            calls["n"] += 1
            return FakeResp(self.content)

    with patch(
        "app.services.simulation.dem.httpx.AsyncClient", lambda *a, **k: FakeClient(tiff)
    ):
        grid = asyncio_run(dem_mod.fetch_dem_for_bbox(43.695, 7.265))
        # Deuxieme appel : servi par le cache (une seule requete au total).
        grid2 = asyncio_run(dem_mod.fetch_dem_for_bbox(43.695, 7.265))
    assert grid is not None
    assert grid == grid2
    assert len(grid) == GRID_N
    assert all(len(row) == GRID_N for row in grid)
    assert calls["n"] == 1, "le cache par adresse doit eviter une 2e requete"

    # Pixels no-data (mer, -99999) → remplaces par le sentinelle SEA_SENTINEL.
    dem_mod._DEM_CACHE.clear()
    vals = [10.0 + i % 5 for i in range(n)]
    vals[0] = -99999.0  # une cellule « mer »
    tiff_sea = _build_float_tiff(GRID_N, GRID_N, vals)
    with patch(
        "app.services.simulation.dem.httpx.AsyncClient",
        lambda *a, **k: FakeClient(tiff_sea),
    ):
        grid = asyncio_run(dem_mod.fetch_dem_for_bbox(43.697, 7.267))
    assert grid is not None
    flat = [v for row in grid for v in row]
    assert dem_mod.SEA_SENTINEL in flat, "la mer doit porter le sentinelle"
    assert all(v == dem_mod.SEA_SENTINEL or v >= 10.0 for v in flat)

    # Reponse non-TIFF (ServiceException XML) → None, jamais une exception.
    dem_mod._DEM_CACHE.clear()
    with patch(
        "app.services.simulation.dem.httpx.AsyncClient",
        lambda *a, **k: FakeClient(b"<ServiceExceptionReport>...</ServiceExceptionReport>"),
    ):
        grid = asyncio_run(dem_mod.fetch_dem_for_bbox(43.696, 7.266))
    assert grid is None


def test_simulation_unknown_alea_404():
    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/diagnostic/adresse/simulation/rga",
            json={"lat": 43.695, "lon": 7.265},
        )
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "alea_non_simulable"


def test_simulation_feu_foret_step_interpolation():
    """Le feu utilise STEP : les echantillons doivent porter l'algorithme
    STEP (front net, pas d'interpolation douce)."""
    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/diagnostic/adresse/simulation/feu_foret",
            json={"lat": 43.695, "lon": 7.265, "niveau": "critique"},
        )
        done = _wait_ready(client, resp.json()["job_id"])
        czml = client.get(done["czml_url"]).json()

    assert len(czml["packet"]) > 0
    color = czml["packet"][0]["polygon"]["material"]["solidColor"]["color"]
    assert color["interpolationAlgorithm"] == "STEP"


def test_simulation_job_inconnu_404():
    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/diagnostic/adresse/simulation/jobs/nawak")
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "job_inconnu"


if __name__ == "__main__":
    test_grid_timeseries_to_czml_structure()
    test_grid_timeseries_to_czml_zero_grid_omits_cells()
    test_grid_timeseries_to_czml_accepte_numpy()
    test_simulation_job_flow_inondation()
    test_simulation_unknown_alea_404()
    test_simulation_feu_foret_step_interpolation()
    test_simulation_job_inconnu_404()
    test_simulation_inondation_fallback_sans_mnt()
    test_inondation_dem_baignoire_topographique()
    test_inondation_dem_cotier_mer_exclue_des_stats()
    test_dem_parse_tiff_sud_premier()
    test_dem_fetch_tiff_et_echec()
    test_inondation_dem_source_priority_flood()
    test_simulation_source_api_flow()
    print("\nTOUS LES TESTS test_simulation_api PASSENT")
