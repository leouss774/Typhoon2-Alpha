"""
Lookup local DVF (Demandes de Valeurs Foncieres) : transactions immobilieres
reelles, utilisees pour le contexte de marche (prix/m2) et pour les
marqueurs "annonces" de la carte de zone (cf. app/scoring/zone_scoring.py
et app/connectors/annonces_lookup.py) - DVF recense des ventes deja
realisees, pas des biens actuellement en vente.

DVF n'est pas une API : ce sont des fichiers a telecharger une bonne fois
pour toutes puis a interroger en local (voir data/lookup/dvf/README.md).
Deux formats sont acceptes dans DVF_LOOKUP_DIR :

  1. Format brut DGFiP national : "ValeursFoncieres-{annee}.txt", un seul
     fichier pour toute la France, separateur "|", colonnes en francais,
     decimales a la virgule, PAS de coordonnees GPS. C'est le format
     telecharge depuis data.gouv.fr ("Demandes de valeurs foncieres").
     -> normalise ici, puis filtre/mis en cache par departement.
  2. Format geolocalise par departement (legacy) : "{departement}.csv",
     issu du projet geo-dvf (colonnes deja normalisees en snake_case,
     avec latitude/longitude) :
     https://files.data.gouv.fr/geo-dvf/latest/csv/{annee}/departements/{dept}.csv.gz
     -> charge tel quel si present (prioritaire sur le format brut).

Le format brut n'ayant pas de coordonnees, le positionnement sur la carte
(real_transactions_for_zone) geocode a la demande un echantillon d'adresses
via l'API BAN bulk CSV (gratuite, sans cle - meme fournisseur que
l'autocomplete de ville du frontend), et met le resultat en cache par
commune pour ne le faire qu'une fois.
"""

from __future__ import annotations

import glob
import io
from pathlib import Path

import httpx
import pandas as pd

from app.core.config import settings
from app.core.paca import department_code_from_citycode
# zone_scoring removed — climate scores for DVF markers are no longer computed here

_cache: dict[str, pd.DataFrame] = {}
_national_cache: pd.DataFrame | None = None
_geocode_cache: dict[str, pd.DataFrame] = {}

# Nombre max de transactions geocodees par commune (mises en cache) - assez
# large pour couvrir un arrondissement/une petite ville, mais borne pour ne
# pas envoyer des milliers d'adresses a l'API BAN a chaque premiere requete.
_MAX_GEOCODE_PAR_COMMUNE = 300


class DvfLookupUnavailable(RuntimeError):
    pass


# ---------------------------------------------------------------------------
#   Chargement + normalisation du format brut DGFiP national
# ---------------------------------------------------------------------------

_RAW_USECOLS = [
    "Date mutation", "Nature mutation", "Valeur fonciere",
    "No voie", "B/T/Q", "Type de voie", "Voie", "Code postal", "Commune",
    "Code departement", "Code commune",
    "Type local", "Surface reelle bati", "Nombre pieces principales",
]


def _normalize_raw_national(df: pd.DataFrame) -> pd.DataFrame:
    """Convertit le format brut DGFiP (colonnes FR, decimales virgule, pas de
    geoloc) vers le schema interne unifie utilise par ce module."""
    out = pd.DataFrame()
    out["date_mutation"] = pd.to_datetime(
        df["Date mutation"], format="%d/%m/%Y", errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    out["nature_mutation"] = df["Nature mutation"]
    out["valeur_fonciere"] = pd.to_numeric(
        df["Valeur fonciere"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    out["surface_reelle_bati"] = pd.to_numeric(df["Surface reelle bati"], errors="coerce")
    out["nombre_pieces_principales"] = pd.to_numeric(df["Nombre pieces principales"], errors="coerce")
    out["type_local"] = df["Type local"]

    # Code commune INSEE (5 caracteres) : "Code commune" brut n'est PAS
    # zero-pad (ex. Nice = "88", pas "088") - reconstruction necessaire pour
    # matcher le citycode BAN (ex. "06088") utilise cote frontend.
    dept = df["Code departement"].astype(str).str.strip()
    commune_num = df["Code commune"].astype(str).str.strip()
    out["code_departement"] = dept
    out["code_commune"] = dept + commune_num.str.zfill(3)
    out["nom_commune"] = df["Commune"]
    out["code_postal"] = df["Code postal"].astype(str).str.strip().str.zfill(5)

    # Adresse reconstituee pour geocodage + affichage (ex. "19 RUE DE ROQUEBILLIERE")
    numero = df["No voie"].fillna("").astype(str).str.replace(r"\.0$", "", regex=True)
    suffixe = df["B/T/Q"].fillna("")
    type_voie = df["Type de voie"].fillna("")
    voie = df["Voie"].fillna("")
    adresse = (numero + suffixe + " " + type_voie + " " + voie).str.strip()
    adresse = adresse.str.replace(r"\s+", " ", regex=True)
    out["adresse"] = adresse.where(adresse.str.len() > 0, out["nom_commune"])

    # Pas de coordonnees dans le format brut : colonnes presentes mais vides,
    # pour que le reste du code (zone_price_stats...) puisse detecter
    # uniformement l'absence de geoloc via .notna().any().
    out["latitude"] = pd.NA
    out["longitude"] = pd.NA

    return out


def _load_national_raw_df() -> pd.DataFrame:
    global _national_cache
    if _national_cache is not None:
        return _national_cache

    pattern = str(Path(settings.dvf_lookup_dir) / "ValeursFoncieres-*.txt")
    files = sorted(glob.glob(pattern))
    if not files:
        raise DvfLookupUnavailable(
            f"Aucun fichier DVF brut trouve ({pattern}) et aucun CSV par departement non plus. "
            "Voir data/lookup/dvf/README.md."
        )

    frames = []
    for f in files:
        raw = pd.read_csv(f, sep="|", usecols=_RAW_USECOLS, dtype=str, encoding="utf-8", low_memory=False)
        frames.append(_normalize_raw_national(raw))
    _national_cache = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    return _national_cache


def _load_department_file(department_code: str) -> pd.DataFrame:
    if department_code in _cache:
        return _cache[department_code]

    # 1. Format legacy geolocalise par departement (prioritaire s'il existe :
    # deja les vraies coordonnees, pas besoin de geocoder).
    legacy_path = Path(settings.dvf_lookup_dir) / f"{department_code}.csv"
    if legacy_path.exists():
        df = pd.read_csv(legacy_path, low_memory=False)
        _cache[department_code] = df
        return df

    # 2. Sinon, fichier brut national : filtre + cache le sous-ensemble du
    # departement (evite de refiltrer les ~3.7M lignes a chaque appel).
    national = _load_national_raw_df()
    subset = national[national["code_departement"] == str(department_code)].copy()
    if subset.empty:
        raise DvfLookupUnavailable(
            f"Aucune transaction DVF trouvee pour le departement {department_code} "
            "(ni CSV departemental, ni donnees dans le fichier brut national). "
            "Voir data/lookup/dvf/README.md."
        )
    _cache[department_code] = subset
    return subset


def lookup_dvf(citycode: str, max_rows: int = 20) -> list[dict]:
    """Retourne les dernieres transactions DVF connues pour la commune.

    Filtre les ventes Maison/Appartement uniquement (les dependances et
    locaux industriels n'ont pas de surface_reelle_bati exploitable pour
    un prix au m2) et les ventes valides (nature_mutation == "Vente",
    prix > 0, surface >= 9 m2) — c'est ce que le valuateur economique
    (app/economie/valuateur.py) attend pour calculer un prix au m2 median.
    """
    department_code = department_code_from_citycode(citycode)
    df = _load_department_file(department_code)

    commune_col = next((c for c in ("code_commune", "codecommune", "insee") if c in df.columns), None)
    if commune_col is None:
        raise DvfLookupUnavailable(
            "Colonne de code commune introuvable dans le fichier DVF local. "
            f"Colonnes disponibles : {list(df.columns)[:15]}..."
        )

    # Le code_commune dans le CSV geo-dvf est parfois sans zéro padding
    # (ex. "6088" pour Nice au lieu de "06088") : on normalise les deux
    # côtés à 5 caractères pour un matching fiable avec le citycode BAN.
    citycode_norm = str(citycode).zfill(5)
    subset = df[df[commune_col].astype(str).str.zfill(5) == citycode_norm]
    valides = _filtrer_ventes_valides(subset, _TYPES_PRIX_M2)
    return valides.head(max_rows).to_dict(orient="records")


# Types de biens retenus pour un prix au m2 comparable (on exclut
# dependances/locaux industriels et terrains nus, qui n'ont pas de
# surface_reelle_bati exploitable).
_TYPES_PRIX_M2 = {"Maison", "Appartement"}


def _has_geoloc(df: pd.DataFrame, lat_col: str | None, lon_col: str | None) -> bool:
    if lat_col is None or lon_col is None:
        return False
    return df[lat_col].notna().any() and df[lon_col].notna().any()


def _filtrer_ventes_valides(df: pd.DataFrame, types: set[str] | None) -> pd.DataFrame:
    """Ventes uniquement (exclut echanges/adjudications...), types de biens
    filtres, prix/surface exploitables, prix/m2 ecrete des aberrations."""
    types = types or _TYPES_PRIX_M2
    subset = df
    if "nature_mutation" in subset.columns:
        subset = subset[subset["nature_mutation"] == "Vente"]
    if "type_local" in subset.columns and types:
        subset = subset[subset["type_local"].isin(types)]

    valeur_col = "valeur_fonciere" if "valeur_fonciere" in subset.columns else None
    surface_col = "surface_reelle_bati" if "surface_reelle_bati" in subset.columns else None
    if valeur_col is None or surface_col is None:
        raise DvfLookupUnavailable(
            "Colonnes valeur_fonciere/surface_reelle_bati introuvables dans les donnees DVF locales. "
            f"Colonnes disponibles : {list(subset.columns)[:15]}..."
        )

    # Surface plancher a 9 m2 (studio minimal legal) pour eviter les
    # divisions par une surface quasi nulle qui explosent le prix/m2.
    valides = subset[(subset[valeur_col] > 0) & (subset[surface_col] >= 9)].copy()
    if valides.empty:
        return valides

    valides["prix_m2"] = valides[valeur_col] / valides[surface_col]
    return valides[(valides["prix_m2"] >= 200) & (valides["prix_m2"] <= 30000)]


def zone_price_stats(
    department_code: str,
    bounds: tuple[float, float, float, float],
    commune_code: str | None = None,
    types: set[str] | None = None,
) -> dict:
    """Statistiques de prix au m2 (ventes DVF) sur une zone.

    Filtre par bounding box quand les donnees locales sont geolocalisees
    (format geo-dvf legacy). Le format brut DGFiP n'a pas de coordonnees :
    dans ce cas, filtre par commune_code (code INSEE) a la place - moins
    precis qu'un bbox, mais c'est la granularite la plus fine disponible
    sans geocoder l'integralite du departement.

    Leve DvfLookupUnavailable si aucune donnee DVF locale n'est disponible
    pour ce departement, ou si le format brut est utilise sans commune_code
    fourni (impossible de circonscrire la zone sans coordonnees).
    """
    df = _load_department_file(department_code)

    lat_col = next((c for c in ("latitude", "lat") if c in df.columns), None)
    lon_col = next((c for c in ("longitude", "lon", "long") if c in df.columns), None)

    if _has_geoloc(df, lat_col, lon_col):
        lat_min, lon_min, lat_max, lon_max = bounds
        subset = df[df[lat_col].between(lat_min, lat_max) & df[lon_col].between(lon_min, lon_max)]
    elif commune_code:
        subset = df[df["code_commune"].astype(str) == str(commune_code)]
    else:
        raise DvfLookupUnavailable(
            "Donnees DVF locales sans coordonnees (fichier brut DGFiP) : commune_code requis "
            "pour circonscrire la zone (aucun bbox possible sans geocodage)."
        )

    valides = _filtrer_ventes_valides(subset, types)
    if valides.empty:
        return {"nb_ventes": 0, "prix_m2_median": None, "prix_m2_moyen": None, "par_type": {}}

    par_type: dict[str, dict] = {}
    if "type_local" in valides.columns:
        for type_local, grp in valides.groupby("type_local"):
            par_type[str(type_local)] = {
                "nb_ventes": int(len(grp)),
                "prix_m2_median": round(float(grp["prix_m2"].median()), 0),
            }

    return {
        "nb_ventes": int(len(valides)),
        "prix_m2_median": round(float(valides["prix_m2"].median()), 0),
        "prix_m2_moyen": round(float(valides["prix_m2"].mean()), 0),
        "par_type": par_type,
    }


# ---------------------------------------------------------------------------
#   Geocodage BAN bulk (pour positionner les ventes du format brut, qui n'a
#   pas de coordonnees) - meme fournisseur que l'autocomplete de ville du
#   frontend (api-adresse.data.gouv.fr), gratuit, sans cle.
# ---------------------------------------------------------------------------

def _geocode_ban_bulk(rows: pd.DataFrame) -> pd.DataFrame:
    """Geocode en un seul appel un lot d'adresses via l'API BAN bulk CSV.

    rows doit contenir au moins les colonnes 'adresse' et 'code_postal'.
    Retourne rows enrichi de 'latitude'/'longitude'/'result_score' (NaN pour
    les lignes non geocodees). Leve DvfLookupUnavailable si l'appel echoue
    (reseau, service indisponible...) - a l'appelant de retomber sur un
    fallback plutot que de faire planter la requete.
    """
    buf = io.StringIO()
    rows[["_id", "adresse", "code_postal"]].to_csv(buf, index=False)
    csv_bytes = buf.getvalue().encode("utf-8")

    try:
        resp = httpx.post(
            "https://api-adresse.data.gouv.fr/search/csv/",
            files={"data": ("adresses.csv", csv_bytes, "text/csv")},
            data={"columns": "adresse", "postcode": "code_postal"},
            timeout=settings.http_timeout_seconds,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise DvfLookupUnavailable(f"Geocodage BAN bulk indisponible : {exc}") from exc

    geocoded = pd.read_csv(io.StringIO(resp.text))
    lat_col = next((c for c in geocoded.columns if "latitude" in c.lower()), None)
    lon_col = next((c for c in geocoded.columns if "longitude" in c.lower()), None)
    if lat_col is None or lon_col is None:
        raise DvfLookupUnavailable(
            f"Reponse BAN bulk inattendue (pas de colonne latitude/longitude) : {list(geocoded.columns)}"
        )

    geocoded = geocoded.rename(columns={lat_col: "latitude", lon_col: "longitude"})

    # Les lignes du format brut portent deja des colonnes latitude/longitude
    # placeholder (NaN, cf. _normalize_raw_national) : sans ce drop, le merge
    # les renommerait en latitude_x/latitude_y au lieu d'ecraser proprement.
    rows = rows.drop(columns=[c for c in ("latitude", "longitude") if c in rows.columns])
    return rows.merge(geocoded[["_id", "latitude", "longitude"]], on="_id", how="left")


def _geocoded_transactions_for_commune(department_code: str, commune_code: str) -> pd.DataFrame:
    """Ventes Maison/Appartement de la commune, geocodees et mises en cache
    (une seule fois par commune, cf. _MAX_GEOCODE_PAR_COMMUNE)."""
    if commune_code in _geocode_cache:
        return _geocode_cache[commune_code]

    df = _load_department_file(department_code)
    lat_col = next((c for c in ("latitude", "lat") if c in df.columns), None)
    lon_col = next((c for c in ("longitude", "lon", "long") if c in df.columns), None)

    subset = df[df["code_commune"].astype(str) == str(commune_code)]
    valides = _filtrer_ventes_valides(subset, _TYPES_PRIX_M2)

    if _has_geoloc(df, lat_col, lon_col):
        # Deja geolocalise (format legacy) : rien a geocoder.
        _geocode_cache[commune_code] = valides
        return valides

    if valides.empty:
        _geocode_cache[commune_code] = valides
        return valides

    # Les ventes les plus recentes d'abord (plus pertinentes pour une carte
    # "annonces"), plafonnees pour ne pas envoyer un lot enorme a la BAN.
    if "date_mutation" in valides.columns:
        valides = valides.sort_values("date_mutation", ascending=False)
    a_geocoder = valides.head(_MAX_GEOCODE_PAR_COMMUNE).copy()
    a_geocoder["_id"] = range(len(a_geocoder))

    geocoded = _geocode_ban_bulk(a_geocoder)
    geocoded = geocoded[geocoded["latitude"].notna() & geocoded["longitude"].notna()]
    geocoded["latitude"] = pd.to_numeric(geocoded["latitude"], errors="coerce")
    geocoded["longitude"] = pd.to_numeric(geocoded["longitude"], errors="coerce")

    _geocode_cache[commune_code] = geocoded
    return geocoded


def real_transactions_for_zone(
    department_code: str,
    commune_code: str,
    bounds: tuple[float, float, float, float],
    max_results: int = 40,
) -> list[dict]:
    """Vraies ventes DVF geolocalisees dans la zone visible, pretes pour
    l'affichage carte (cf. app/connectors/annonces_lookup.py).

    Geocode a la demande (une fois par commune, cf. _geocode_cache) si les
    donnees locales n'ont pas deja de coordonnees. Leve DvfLookupUnavailable
    si les donnees DVF du departement sont indisponibles ou si le
    geocodage BAN echoue - a l'appelant de retomber sur le mode demo.
    """
    geocoded = _geocoded_transactions_for_commune(department_code, commune_code)
    if geocoded.empty:
        return []

    lat_min, lon_min, lat_max, lon_max = bounds
    in_bounds = geocoded[
        geocoded["latitude"].between(lat_min, lat_max) & geocoded["longitude"].between(lon_min, lon_max)
    ]
    if in_bounds.empty:
        return []

    listings = []
    for _, row in in_bounds.head(max_results).iterrows():
        surface = row.get("surface_reelle_bati")
        valeur = row.get("valeur_fonciere")
        prix_m2 = row.get("prix_m2")
        lat, lon = float(row["latitude"]), float(row["longitude"])
        listings.append({
            "id": f"dvf-{row.get('code_commune')}-{row.name}",
            "lat": lat,
            "lon": lon,
            "adresse": row.get("adresse") or row.get("nom_commune"),
            "type_bien": row.get("type_local"),
            "surface_m2": float(surface) if pd.notna(surface) else None,
            "prix": float(valeur) if pd.notna(valeur) else None,
            "prix_m2": round(float(prix_m2), 0) if pd.notna(prix_m2) else None,
            "pieces": int(row["nombre_pieces_principales"]) if pd.notna(row.get("nombre_pieces_principales")) else None,
            "dpe": None,  # DVF ne contient pas le DPE (donnee ADEME distincte)
            "date_publication": row.get("date_mutation"),
            "climat_score": None,  # zone scoring pipeline removed; use /diagnostic/adresse per address
            "source": "dvf",
            "url": None,
        })
    return listings
