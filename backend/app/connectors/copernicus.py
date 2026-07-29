"""
Projections/indicateurs climatiques via le Copernicus Climate Data Store
(CDS) - remplace le lookup local DRIAS (compte + telechargement 100 %
manuel, sans aucune API).

Dataset : "Climate indicators for Europe from 1940 to 2100 derived from
reanalysis and climate projections" (sis-ecde-climate-indicators).
Page : https://cds.climate.copernicus.eu/datasets/sis-ecde-climate-indicators

La requete ci-dessous (_REQUEST) est celle generee par le formulaire
officiel du dataset (bouton "Show API request code"), fournie telle
quelle : aucun parametre n'est invente ici. Elle porte sur des projections
(GCM IPSL-CM5A-MR / RCM WRF381P, membre r1i1p1, scenarios RCP4.5 et
RCP8.5), agregees mensuellement/saisonnierement/annuellement, sur des
indicateurs directement utiles au scoring de risque Typhoon : jours
chauds, jours de canicule, jours de gel, precipitations extremes,
frequence des precipitations extremes, duree et magnitude des secheresses
meteorologiques (SPI-3).

=== Compte et cle CDS - sans rien ecrire sur C: ===
cdsapi lit sa config par ordre de priorite : d'abord les variables
d'environnement CDSAPI_URL / CDSAPI_KEY, puis a defaut le fichier
$HOME/.cdsapirc (sous le profil utilisateur, donc sur C: sous Windows).
Pour eviter d'ecrire quoi que ce soit sur C: (contrainte d'espace disque), ce projet
utilise les variables d'environnement plutot que ce fichier - voir
backend/activate_d_drive_session.ps1, qui les definit avant chaque usage
du CLI :

    $env:CDSAPI_URL = "https://cds.climate.copernicus.eu/api"
    $env:CDSAPI_KEY = "VOTRE_TOKEN"

Il reste necessaire d'accepter une fois les conditions d'utilisation du
dataset sur le site (onglet "Download" de la page ci-dessus, bas du
formulaire) - ca ne telecharge rien sur C:, c'est juste un clic sur le
site CDS lie a votre compte.

=== Limite reseau constatee dans cet environnement ===
Le bac a sable dans lequel ce code est ecrit bloque l'acces reseau sortant
vers cds.climate.copernicus.eu (comme vers toutes les autres API de ce
projet - verifie avec curl -v : "403 blocked-by-allowlist"). Pire, la
simple creation d'un cdsapi.Client() tente de contacter le serveur CDS des
l'instanciation (verification de version/messages) : dans cet
environnement, cet appel reste bloque en boucle de nouvelle tentative
(jusqu'a 500 tentatives, 120 secondes d'attente entre chacune) au lieu
d'echouer immediatement. Ce module n'a donc pas pu etre teste en conditions
reelles depuis cet environnement - a executer sur une machine avec un
acces internet normal.

=== Nature asynchrone de l'API CDS ===
Contrairement a Open-Meteo (reponse JSON instantanee), CDS met chaque
demande en file d'attente et prepare un ou plusieurs fichiers a
telecharger (NetCDF, parfois regroupes dans une archive .zip) : de
quelques secondes a plusieurs dizaines de minutes selon la charge du
service. Pour ne pas payer ce cout a chaque adresse testee, ce module
telecharge le jeu de donnees UNE SEULE FOIS, le met en cache dans
COPERNICUS_CACHE_DIR, puis chaque lecture "point" (une adresse) est une
simple lecture locale via xarray - jamais une valeur recalculee ou
approximee, uniquement les valeurs du fichier officiel telecharge.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path
from typing import Any

from app.core.config import settings

DATASET_ID = "sis-ecde-climate-indicators"

# Requete exacte fournie via le formulaire CDS ("Show API request code").
# Ne pas modifier sans repasser par le formulaire officiel du dataset.
_REQUEST: dict[str, Any] = {
    "origin": "projections",
    "gcm": ["ipsl_cm5a_mr"],
    "rcm": ["wrf381p"],
    "experiment": ["rcp4_5", "rcp8_5"],
    "ensemble_member": ["r1i1p1"],
    "temporal_aggregation": ["monthly", "seasonal", "yearly"],
    "spatial_aggregation": "gridded",
    "version": "v2_0",
    "variable": [
        "hot_days",
        "heatwave_days",
        "frost_days",
        "extreme_precipitation_total",
        "frequency_of_extreme_precipitation",
        "duration_of_meteorological_droughts",
        "magnitude_of_meteorological_droughts",
    ],
    "other_parameters": ["30_c", "35_c", "40_c"],
}


class CopernicusNotConfigured(RuntimeError):
    pass


class CopernicusDataMissing(RuntimeError):
    pass


def _cache_dir() -> Path:
    return Path(settings.copernicus_cache_dir)


def _download_marker() -> Path:
    return _cache_dir() / ".download_complete"


def ensure_dataset_downloaded(force: bool = False) -> Path:
    """Telecharge (une seule fois, puis mis en cache) le jeu de donnees
    Copernicus defini par _REQUEST, et retourne le repertoire de cache.

    Le fichier recu de CDS peut etre un NetCDF unique ou une archive .zip
    regroupant plusieurs NetCDF (un par combinaison variable/scenario) :
    les deux cas sont geres, sans hypothese sur le contenu exact tant que
    le telechargement n'a pas ete effectivement observe.
    """
    cache_dir = _cache_dir()
    marker = _download_marker()
    if marker.exists() and not force:
        return cache_dir

    if not _REQUEST:
        raise CopernicusNotConfigured(
            "_REQUEST est vide dans app/connectors/copernicus.py : "
            "completez-le depuis le formulaire CDS ('Show API request code')."
        )

    import cdsapi  # import tardif : evite la dependance dure si non utilise

    cache_dir.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    result = client.retrieve(DATASET_ID, dict(_REQUEST))
    downloaded_path = Path(result.download())

    if downloaded_path.suffix == ".zip":
        with zipfile.ZipFile(downloaded_path) as archive:
            archive.extractall(cache_dir)
        downloaded_path.unlink(missing_ok=True)
    else:
        shutil.move(str(downloaded_path), cache_dir / downloaded_path.name)

    marker.write_text("ok", encoding="utf-8")
    return cache_dir


def read_indicators_at_point(lat: float, lon: float) -> dict[str, Any]:
    """Lit, pour chaque fichier NetCDF telecharge, les indicateurs
    climatiques Copernicus au point le plus proche.

    Fonction synchrone et potentiellement longue au tout premier appel
    (telechargement CDS) : a lancer via asyncio.to_thread depuis
    collector_agent. Les appels suivants sont quasi instantanes (lecture
    du cache local uniquement).

    Cle de retour : "{nom_du_fichier}__{variable}" pour eviter toute
    collision entre scenarios/agregations differents regroupes dans des
    fichiers distincts.
    """
    import xarray as xr

    cache_dir = ensure_dataset_downloaded()
    nc_files = sorted(cache_dir.glob("*.nc"))
    if not nc_files:
        raise CopernicusDataMissing(
            f"Aucun fichier NetCDF trouve dans {cache_dir} apres telechargement. "
            "Verifiez le contenu recu de CDS (format inattendu ?)."
        )

    resultats: dict[str, Any] = {}
    for path in nc_files:
        with xr.open_dataset(path) as dataset:
            lat_name = "latitude" if "latitude" in dataset.coords else "lat"
            lon_name = "longitude" if "longitude" in dataset.coords else "lon"
            point = dataset.sel({lat_name: lat, lon_name: lon}, method="nearest")
            for var in dataset.data_vars:
                resultats[f"{path.stem}__{var}"] = point[var].values.tolist()

    return resultats
