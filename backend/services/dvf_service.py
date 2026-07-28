"""
Service DVF local — Données officielles DGFiP (data.gouv.fr).

Workflow :
  1. Téléchargement des fichiers DVF (zip) depuis data.gouv.fr
  2. Parsing des fichiers pipe-separated → SQLite
  3. Indexation par commune + type de bien
  4. Requête → prix médian au m² + transactions comparables

Mise à jour : exécuter `python scripts/update_dvf.py` (manuel ou cron semestriel).
"""

import csv
import io
import json
import logging
import os
import re
import sqlite3
import time
import urllib.parse
import zipfile
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DB_DIR = os.path.join(BASE_DIR, "data", "processed")
DB_PATH = os.path.join(DB_DIR, "dvf.sqlite")
META_PATH = os.path.join(DB_DIR, "dvf_meta.json")

# ── Sources data.gouv.fr ─────────────────────────────────────────────────────
DATASET_API = "https://www.data.gouv.fr/api/1/datasets/demandes-de-valeurs-foncieres/"
TIMEOUT = 30  # secondes pour le téléchargement (fichier volumineux)
OPENDATA_TIMEOUT = 5  # secondes pour les appels API légers

# ── Colonnes utiles du fichier DVF ──────────────────────────────────────────
# Index basés sur le header du fichier ValeursFoncieres-2025.txt (43 colonnes)
COL_DATE_MUTATION = 8
COL_NATURE_MUTATION = 9
COL_VALEUR_FONCIERE = 10
COL_CODE_POSTAL = 16
COL_COMMUNE = 17
COL_CODE_DEPARTEMENT = 18
COL_CODE_COMMUNE = 19
COL_TYPE_LOCAL = 36
COL_SURFACE_BATI = 38
COL_NB_PIECES = 39
COL_SURFACE_TERRAIN = 42

# Mapping types DVF → types normalisés
TYPE_MAPPING = {
    "Maison": "Maison",
    "Appartement": "Appartement",
    "Local industriel. commercial ou assimilé": "Local commercial",
    "Dépendance": "Dépendance",
    "Local d'habitation": "Appartement",
}


def _get_latest_resources() -> list[dict]:
    """Récupère la liste des fichiers DVF disponibles depuis data.gouv.fr."""
    try:
        resp = requests.get(DATASET_API, timeout=OPENDATA_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        resources = data.get("resources", [])
        # Filtrer les fichiers .txt.zip (DVF annuels)
        dvf_files = [
            r for r in resources
            if r.get("url", "").endswith(".txt.zip")
            and "valeursfoncieres" in r.get("url", "").lower()
        ]
        # Trier par date (les plus récents d'abord)
        dvf_files.sort(key=lambda r: r.get("created", ""), reverse=True)
        return dvf_files
    except Exception as e:
        logger.error(f"Erreur récupération ressources data.gouv.fr : {e}")
        return []


def download_dvf_files(years: Optional[list[int]] = None) -> dict:
    """
    Télécharge les fichiers DVF depuis data.gouv.fr.

    Args:
        years: Liste des années à télécharger (ex: [2025]). None = tous.

    Returns:
        dict: {annee: {"status": "ok"|"exists"|"error", "path": str, "size_mb": float}}
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    resources = _get_latest_resources()
    if not resources:
        logger.warning("Aucune ressource DVF trouvée sur data.gouv.fr")
        return {}

    result = {}
    for res in resources:
        url = res["url"]
        # Extraire l'année du nom de fichier: valeursfoncieres-2025.txt.zip
        fname = url.rsplit("/", 1)[-1]
        year_str = fname.replace("valeursfoncieres-", "").replace(".txt.zip", "")
        try:
            year = int(year_str)
        except ValueError:
            continue

        if years and year not in years:
            continue

        dest = os.path.join(RAW_DIR, fname)
        if os.path.exists(dest):
            size_mb = round(os.path.getsize(dest) / (1024 * 1024), 1)
            logger.info(f"DVF {year} déjà présent ({size_mb} MB)")
            result[year] = {"status": "exists", "path": dest, "size_mb": size_mb}
            continue

        logger.info(f"Téléchargement DVF {year} ({round(res.get('filesize', 0) / 1024 / 1024, 1)} MB)...")
        try:
            dl_resp = requests.get(url, timeout=TIMEOUT)
            dl_resp.raise_for_status()
            with open(dest, "wb") as f:
                f.write(dl_resp.content)
            size_mb = round(os.path.getsize(dest) / (1024 * 1024), 1)
            logger.info(f"✓ DVF {year} téléchargé ({size_mb} MB)")
            result[year] = {"status": "ok", "path": dest, "size_mb": size_mb}
        except Exception as e:
            logger.error(f"Erreur téléchargement DVF {year} : {e}")
            result[year] = {"status": "error", "error": str(e)}

    return result


def _parse_valeur_fonciere(val: str) -> Optional[float]:
    """Parse une valeur foncière DVF (format: '468000,00')."""
    if not val or val.strip() == "":
        return None
    try:
        return float(val.strip().replace(",", ".").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _parse_surface(val: str) -> Optional[float]:
    """Parse une surface."""
    if not val or val.strip() == "":
        return None
    try:
        s = float(val.strip().replace(",", ".").replace(" ", ""))
        return s if s > 0 else None
    except (ValueError, AttributeError):
        return None


def build_sqlite_index(years: Optional[list[int]] = None) -> dict:
    """
    Parse les fichiers DVF téléchargés et construit l'index SQLite.

    Args:
        years: Années à indexer. None = toutes les années disponibles.

    Returns:
        dict: Statistiques d'indexation.
    """
    os.makedirs(DB_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Création de la table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS mutations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_mutation TEXT,
            valeur_fonciere REAL,
            code_departement TEXT,
            code_commune TEXT,
            code_postal TEXT,
            nom_commune TEXT,
            type_local TEXT,
            surface_reelle_bati REAL,
            nombre_pieces INTEGER,
            surface_terrain REAL,
            annee INTEGER
        )
    """)

    # Index pour les requêtes rapides
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_commune_type ON mutations(code_commune, type_local)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_departement ON mutations(code_departement)")

    conn.commit()

    # Lister les fichiers zip disponibles
    zip_files = sorted(
        [f for f in os.listdir(RAW_DIR) if f.startswith("valeursfoncieres") and f.endswith(".txt.zip")],
        reverse=True,
    )

    total_parsed = 0
    total_inserted = 0
    years_processed = []

    for zf_name in zip_files:
        year_str = zf_name.replace("valeursfoncieres-", "").replace(".txt.zip", "")
        try:
            year = int(year_str)
        except ValueError:
            continue

        if years and year not in years:
            continue

        if year in years_processed:
            continue

        zf_path = os.path.join(RAW_DIR, zf_name)
        if not os.path.exists(zf_path):
            continue

        logger.info(f"Parsing DVF {year}...")
        parsed = 0
        inserted = 0

        try:
            with zipfile.ZipFile(zf_path) as zf:
                txt_name = zf.namelist()[0]
                with zf.open(txt_name) as f:
                    # Lire le header
                    header_line = f.readline().decode("latin-1").strip()

                    # Lire les lignes par blocs
                    for line_bytes in f:
                        line = line_bytes.decode("latin-1", errors="replace").strip()
                        if not line:
                            continue

                        cols = line.split("|")
                        if len(cols) < 43:
                            continue

                        parsed += 1

                        # Ne garder que les ventes
                        nature = cols[COL_NATURE_MUTATION].strip()
                        if nature != "Vente":
                            continue

                        # Valeur foncière
                        valeur = _parse_valeur_fonciere(cols[COL_VALEUR_FONCIERE])
                        if valeur is None or valeur <= 0 or valeur > 50_000_000:
                            continue

                        # Surface bâtie
                        surface = _parse_surface(cols[COL_SURFACE_BATI])
                        # Si pas de surface bâtie, ignorer (pas de prix au m²)
                        if surface is None:
                            continue

                        # Type de bien
                        type_local = cols[COL_TYPE_LOCAL].strip()
                        type_normalise = TYPE_MAPPING.get(type_local, type_local)

                        # Code commune (concaténer département + commune pour code INSEE complet)
                        dept = cols[COL_CODE_DEPARTEMENT].strip()
                        commune_code = cols[COL_CODE_COMMUNE].strip()
                        # Code INSEE = département + commune (sauf Corse 2A/2B)
                        if dept in ("2A", "2B"):
                            code_insee = dept + commune_code.zfill(3)
                        else:
                            code_insee = dept.zfill(2) + commune_code.zfill(3)

                        pieces = _parse_surface(cols[COL_NB_PIECES])
                        terrain = _parse_surface(cols[COL_SURFACE_TERRAIN])

                        cursor.execute(
                            """INSERT INTO mutations
                            (date_mutation, valeur_fonciere, code_departement,
                             code_commune, code_postal, nom_commune,
                             type_local, surface_reelle_bati,
                             nombre_pieces, surface_terrain, annee)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                cols[COL_DATE_MUTATION].strip(),
                                valeur,
                                dept,
                                code_insee,
                                cols[COL_CODE_POSTAL].strip(),
                                cols[COL_COMMUNE].strip(),
                                type_normalise,
                                surface,
                                int(pieces) if pieces else None,
                                terrain,
                                year,
                            ),
                        )
                        inserted += 1

                        if parsed % 100000 == 0:
                            conn.commit()
                            logger.info(f"  ... {parsed} lignes parsées, {inserted} insérées")

        except Exception as e:
            logger.error(f"Erreur parsing DVF {year} : {e}")
            conn.rollback()
            continue

        conn.commit()
        years_processed.append(year)
        total_parsed += parsed
        total_inserted += inserted
        logger.info(f"✓ DVF {year} : {parsed} lignes lues, {inserted} mutations insérées")

    # Statistiques
    cursor.execute("SELECT COUNT(*) FROM mutations")
    total_rows = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT code_commune) FROM mutations")
    total_communes = cursor.fetchone()[0]
    cursor.execute("SELECT MIN(annee), MAX(annee) FROM mutations")
    year_min, year_max = cursor.fetchone()
    
    # Calculer la moyenne nationale du prix au m2 (pour le fallback dynamique)
    try:
        cursor.execute(
            """SELECT ROUND(AVG(valeur_fonciere / surface_reelle_bati))
               FROM mutations
               WHERE surface_reelle_bati > 10
                 AND surface_reelle_bati < 1000
                 AND valeur_fonciere > 1000
                 AND valeur_fonciere < 5000000"""
        )
        avg_row = cursor.fetchone()
        prix_m2_national = round(avg_row[0]) if avg_row and avg_row[0] else None
    except Exception:
        prix_m2_national = None

    # Métadonnées enrichies
    meta = {
        "last_update": datetime.now().isoformat(),
        "total_mutations": total_rows,
        "total_communes": total_communes,
        "prix_m2_national": prix_m2_national,
        "years": year_min and year_max and f"{year_min}-{year_max}",
        "data_source": "DGFiP - Demandes de Valeurs Foncières (data.gouv.fr)",
        "years_processed": years_processed,
    }
    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    conn.close()
    logger.info(f"Indexation terminée : {total_rows} mutations, {total_communes} communes")
    return meta


def get_metadata() -> dict:
    """Retourne les métadonnées de la base DVF locale."""
    if os.path.exists(META_PATH):
        try:
            with open(META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_update": None,
        "total_mutations": 0,
        "total_communes": 0,
        "prix_m2_national": None,
        "years": None,
        "data_source": "DGFiP - Demandes de Valeurs Foncières (data.gouv.fr)",
    }


def _geocode(adresse: str) -> Optional[dict]:
    """Géocode une adresse via l'API Adresse data.gouv.fr.
    
    Fallback: si l'API est indisponible, extrait le code postal depuis l'adresse.
    """
    url = f"https://api-adresse.data.gouv.fr/search/?q={urllib.parse.quote(adresse)}&limit=1"
    try:
        resp = requests.get(url, timeout=OPENDATA_TIMEOUT)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if not features:
            return _geocode_regex_fallback(adresse)
        props = features[0]["properties"]
        citycode = props.get("citycode", "") or ""
        if not citycode:
            return _geocode_regex_fallback(adresse)
        return {
            "lat": features[0]["geometry"]["coordinates"][1],
            "lon": features[0]["geometry"]["coordinates"][0],
            "citycode": citycode,
            "postcode": props.get("postcode", ""),
            "city": props.get("city", ""),
            "score": props.get("score", 0),
        }
    except Exception as e:
        logger.warning(f"API géocodage indisponible, fallback regex : {e}")
        return _geocode_regex_fallback(adresse)


# Mapping code postal → code INSEE pour les communes principales
# Source: Code Officiel Géographique (data.gouv.fr)
# 
# NB: Pour Paris/Lyon/Marseille, chaque arrondissement a son propre code postal
# et son propre code INSEE. Les autres villes ont un code postal unique.
CP_TO_INSEE: dict[str, str] = {
    # Paris (arrondissements 1-20)
    "75001": "75101", "75002": "75102", "75003": "75103", "75004": "75104",
    "75005": "75105", "75006": "75106", "75007": "75107", "75008": "75108",
    "75009": "75109", "75010": "75110", "75011": "75111", "75012": "75112",
    "75013": "75113", "75014": "75114", "75015": "75115", "75016": "75116",
    "75017": "75117", "75018": "75118", "75019": "75119", "75020": "75120",
    # Marseille (arrondissements 1-16)
    "13001": "13201", "13002": "13202", "13003": "13203", "13004": "13204",
    "13005": "13205", "13006": "13206", "13007": "13207", "13008": "13208",
    "13009": "13209", "13010": "13210", "13011": "13211", "13012": "13212",
    "13013": "13213", "13014": "13214", "13015": "13215", "13016": "13216",
    # Lyon (arrondissements 1-9)
    "69001": "69381", "69002": "69382", "69003": "69383", "69004": "69384",
    "69005": "69385", "69006": "69386", "69007": "69387", "69008": "69388",
    "69009": "69389",
    # Nantes
    "44000": "44109", "44200": "44109", "44300": "44109", "44100": "44109",
    # Autres grandes villes
    "64200": "64122",  # Biarritz
    "17310": "17346",  # Saint-Pierre-d'Oleron
    "31000": "31555",  # Toulouse
    "33800": "33063",  # Bordeaux
    "33000": "33063",  # Bordeaux
    "06000": "06088",  # Nice
    "59000": "59350",  # Lille
    "67000": "67482",  # Strasbourg
    "35000": "35238",  # Rennes
    "29200": "29019",  # Brest
    "57000": "57463",  # Metz
    "54000": "54395",  # Nancy
    "21000": "21231",  # Dijon
    "63000": "63113",  # Clermont-Ferrand
    "49100": "49007",  # Angers
    "86000": "86194",  # Poitiers
    "87000": "87085",  # Limoges
    "34000": "34172",  # Montpellier
    "34070": "34172",  # Montpellier
    "34080": "34172",  # Montpellier
    "34090": "34172",  # Montpellier
    "69000": "69381",  # Lyon (code postal générique)
    "13000": "13201",  # Marseille (code postal générique)
}


def _geocode_regex_fallback(adresse: str) -> Optional[dict]:
    """Fallback: extrait le code postal (5 chiffres) depuis l'adresse.
    
    Ex: "3 Rue de la Paix, 44000 Nantes" → code postal "44000" → INSEE "44109"
    Permet de continuer à fonctionner même quand l'API Adresse est en timeout.
    Utilise une table de correspondance CP→INSEE pour les communes principales.
    """
    if not adresse:
        return None
    # Chercher un code postal français à 5 chiffres
    match = re.search(r'\b(\d{5})\b', adresse)
    if not match:
        return None
    code_postal = match.group(1)
    
    # Essayer de trouver l'INSEE dans la table CP→INSEE
    insee = CP_TO_INSEE.get(code_postal, "")
    
    city = ""
    # Essayer d'extraire le nom de la ville après le code postal
    parts = adresse.replace(",", " ").split()
    for i, p in enumerate(parts):
        if p == code_postal and i + 1 < len(parts):
            city = parts[i + 1]
            break
    
    return {
        "lat": None,
        "lon": None,
        "citycode": insee if insee else code_postal,  # INSEE si connu, sinon CP
        "postcode": code_postal,
        "city": city,
        "score": 0.3,  # Confiance plus faible
        "_fallback": True,  # Marquer comme fallback
    }


def _type_to_dvf_type(type_bien: str) -> str:
    """Convertit le type de bien du formulaire en type DVF."""
    t = type_bien.lower()
    if "appartement" in t:
        return "Appartement"
    if "maison" in t:
        return "Maison"
    if "immeuble" in t or "commerce" in t or "local" in t:
        return "Local commercial"
    if "terrain" in t:
        return "Terrain"
    return "Maison"  # fallback


def query_market_value(
    adresse: str,
    surface: float = 100,
    type_bien: str = "Maison",
) -> dict:
    """
    Interroge la base DVF locale pour obtenir la valeur de marché d'un bien.

    Args:
        adresse: Adresse complète du bien
        surface: Surface en m²
        type_bien: Type de bien (Maison, Appartement, etc.)

    Returns:
        dict: Résultat avec valeur estimée, nombre de comparables, etc.
    """
    # 1. Vérifier si la base existe
    if not os.path.exists(DB_PATH):
        return {
            "valeur_estimee": None,
            "devise": "EUR",
            "indice_confiance": 0,
            "source": "Base DVF non initialisée",
            "nb_transactions": 0,
            "prix_m2_median": None,
            "date_min": None,
            "date_max": None,
            "donnees_manquantes": True,
        }

    # 2. Géocoder l'adresse
    geo = _geocode(adresse)
    if not geo:
        return {
            "valeur_estimee": None,
            "devise": "EUR",
            "indice_confiance": 0,
            "source": "Adresse non géolocalisable",
            "nb_transactions": 0,
            "prix_m2_median": None,
            "donnees_manquantes": True,
        }

    code_insee = geo["citycode"]
    dvf_type = _type_to_dvf_type(type_bien)
    surface = max(surface, 20)  # minimum 20 m² pour le calcul

    # 3. Interroger SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Requête : transactions récentes dans la même commune, même type
    cursor.execute(
        """SELECT valeur_fonciere, surface_reelle_bati, date_mutation, annee
           FROM mutations
           WHERE code_commune = ? AND type_local = ?
             AND surface_reelle_bati > 10
             AND surface_reelle_bati < 5000
             AND valeur_fonciere > 1000
           ORDER BY annee DESC, date_mutation DESC
           LIMIT 200""",
        (code_insee, dvf_type),
    )
    rows = cursor.fetchall()

    # Si pas assez de résultats, élargir au type principal
    if len(rows) < 3 and dvf_type in ("Appartement", "Local commercial"):
        parent_type = "Maison" if dvf_type == "Local commercial" else "Appartement"
        cursor.execute(
            """SELECT valeur_fonciere, surface_reelle_bati, date_mutation, annee
               FROM mutations
               WHERE code_commune = ? AND type_local = ?
                 AND surface_reelle_bati > 10
                 AND surface_reelle_bati < 5000
                 AND valeur_fonciere > 1000
               ORDER BY annee DESC, date_mutation DESC
               LIMIT 200""",
            (code_insee, parent_type),
        )
        rows = cursor.fetchall()
        dvf_type = parent_type

    # Si toujours pas assez, élargir au département
    if len(rows) < 3:
        dept = code_insee[:2]
        cursor.execute(
            """SELECT valeur_fonciere, surface_reelle_bati, date_mutation, annee
               FROM mutations
               WHERE code_departement = ? AND type_local = ?
                 AND surface_reelle_bati > 10
                 AND surface_reelle_bati < 5000
                 AND valeur_fonciere > 1000
               ORDER BY annee DESC, date_mutation DESC
               LIMIT 200""",
            (dept, dvf_type),
        )
        rows = cursor.fetchall()
        scope = "département"
    else:
        scope = "commune"

    conn.close()

    if not rows:
        return {
            "valeur_estimee": None,
            "devise": "EUR",
            "indice_confiance": 0,
            "source": f"Aucune transaction DVF trouvée pour {code_insee}",
            "nb_transactions": 0,
            "prix_m2_median": None,
            "donnees_manquantes": True,
        }

    # 4. Calculer le prix au m² pour chaque transaction
    prix_m2_list = []
    for val, surf, date_mut, annee in rows:
        if surf and surf > 0:
            pm2 = val / surf
            if 100 < pm2 < 50000:  # Filtrer les aberrations
                prix_m2_list.append((pm2, val, surf, date_mut, annee))

    if not prix_m2_list:
        return {
            "valeur_estimee": None,
            "devise": "EUR",
            "indice_confiance": 0,
            "source": "Transactions DVF trouvées mais valeurs aberrantes filtrées",
            "nb_transactions": len(rows),
            "donnees_manquantes": True,
        }

    # 5. Calculer la médiane du prix au m²
    prix_m2_list.sort(key=lambda x: x[0])
    n = len(prix_m2_list)
    median_idx = n // 2
    prix_m2_median = prix_m2_list[median_idx][0]

    # Filtrer les outliers (3× la médiane)
    prix_m2_filtres = [p for p in prix_m2_list if p[0] <= prix_m2_median * 3]
    
    # Recalculer la médiane après filtrage
    if prix_m2_filtres:
        prix_m2_filtres.sort(key=lambda x: x[0])
        prix_m2_median = prix_m2_filtres[len(prix_m2_filtres) // 2][0]
    else:
        prix_m2_filtres = prix_m2_list

    # 6. Valeur estimée
    valeur_estimee = round(prix_m2_median * surface)

    # 7. Indice de confiance
    annees_list = [p[4] for p in prix_m2_filtres]  # années (int)
    recency = max(annees_list) if annees_list else 0
    annee_courante = datetime.now().year

    confiance = 80  # base
    if n < 5:
        confiance -= 20
    if n < 10:
        confiance -= 10
    if recency < annee_courante - 2:
        confiance -= 15  # données vieilles
    if scope == "département":
        confiance -= 15  # échelle départementale
    if surface < 30 or surface > 500:
        confiance -= 5  # surface atypique

    confiance = max(15, min(95, confiance))

    date_min = str(min(p[4] for p in prix_m2_filtres))  # année min
    date_max = str(max(p[4] for p in prix_m2_filtres))  # année max

    return {
        "valeur_estimee": valeur_estimee,
        "devise": "EUR",
        "indice_confiance": confiance,
        "source": f"DVF DGFiP ({scope})",
        "nb_transactions": len(prix_m2_filtres),
        "prix_m2_median": round(prix_m2_median, 2),
        "surface_utilisee": surface,
        "type_bien": dvf_type,
        "date_min": str(date_min),
        "date_max": str(date_max),
        "donnees_manquantes": False,
    }


def estimate_from_department(depcode: str, surface: float = 100) -> dict:
    """Estimation par département basée sur les données DVF déjà indexées."""
    if not os.path.exists(DB_PATH):
        return {
            "valeur_estimee": round(2500 * max(surface, 50)),
            "devise": "EUR",
            "indice_confiance": 20,
            "source": "Estimation (base DVF non disponible)",
            "donnees_manquantes": True,
        }

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """SELECT valeur_fonciere, surface_reelle_bati
           FROM mutations
           WHERE code_departement = ?
             AND surface_reelle_bati > 10
             AND surface_reelle_bati < 1000
             AND valeur_fonciere > 1000
             AND valeur_fonciere < 5000000
           ORDER BY annee DESC
           LIMIT 500""",
        (depcode,),
    )
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return {
            "valeur_estimee": round(2500 * max(surface, 50)),
            "devise": "EUR",
            "indice_confiance": 20,
            "source": "Estimation (aucune donnée DVF pour ce département)",
            "donnees_manquantes": True,
        }

    prix_m2 = [v / s for v, s in rows if s > 0 and 100 < v / s < 50000]
    if not prix_m2:
        return {
            "valeur_estimee": round(2500 * max(surface, 50)),
            "devise": "EUR",
            "indice_confiance": 20,
            "source": "Estimation départementale",
            "donnees_manquantes": True,
        }

    median_pm2 = sorted(prix_m2)[len(prix_m2) // 2]
    return {
        "valeur_estimee": round(median_pm2 * max(surface, 50)),
        "devise": "EUR",
        "indice_confiance": 30,
        "source": f"Estimation départementale ({depcode}) — DVF",
        "prix_m2_median": round(median_pm2, 2),
        "nb_transactions": len(rows),
        "donnees_manquantes": False,
    }


def get_price_evolution(adresse: str, type_bien: str = "Maison", max_years: int = 5) -> dict:
    """
    Récupère l'évolution du prix au m² année par année pour une adresse.
    
    Utilise les vraies transactions DVF indexées dans SQLite.
    Retourne un tableau [{annee, prix_m2_median, nb_transactions}] ordonné par année.
    
    Args:
        adresse: Adresse complète du bien
        type_bien: Type de bien (Maison, Appartement, etc.)
        max_years: Nombre max d'années à retourner
    
    Returns:
        dict: data=évolution, source, metadata
    """
    # 1. Géocoder pour obtenir le code commune
    geo = _geocode(adresse)
    if not geo or not geo.get("citycode"):
        return {"data": [], "source": "Adresse non géolocalisable", "nb_annees": 0}
    
    code_insee = geo["citycode"]
    dvf_type = _type_to_dvf_type(type_bien)
    
    # 2. Interroger SQLite
    if not os.path.exists(DB_PATH):
        return {"data": [], "source": "Base DVF non initialisée", "nb_annees": 0}
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Requête : prix par année pour cette commune et ce type
    # Note: SQLite ne supporte pas MEDIAN() comme fonction d'agrégation
    # On utilise AVG comme approximation pour le graphique.
    cursor.execute(
        """SELECT annee, 
                  ROUND(AVG(valeur_fonciere / surface_reelle_bati), 2) as pm2_moyen,
                  ROUND(AVG(valeur_fonciere / surface_reelle_bati), 2) as pm2_median_approx,
                  COUNT(*) as tx_count,
                  ROUND(AVG(valeur_fonciere), 0) as v_moy,
                  MIN(valeur_fonciere) as v_min,
                  MAX(valeur_fonciere) as v_max
           FROM mutations
           WHERE code_commune = ? AND type_local = ?
             AND surface_reelle_bati > 10
             AND surface_reelle_bati < 5000
             AND valeur_fonciere > 1000
             AND valeur_fonciere < 50000000
           GROUP BY annee
           ORDER BY annee DESC
           LIMIT ?""",
        (code_insee, dvf_type, max_years),
    )
    rows = cursor.fetchall()

    # Si pas de données pour ce type, essayer tous types
    if not rows:
        cursor.execute(
            """SELECT annee, 
                      ROUND(AVG(valeur_fonciere / surface_reelle_bati), 2),
                      ROUND(AVG(valeur_fonciere / surface_reelle_bati), 2),
                      COUNT(*),
                      ROUND(AVG(valeur_fonciere), 0),
                      MIN(valeur_fonciere),
                      MAX(valeur_fonciere)
               FROM mutations
               WHERE code_commune = ?
                 AND surface_reelle_bati > 10
                 AND surface_reelle_bati < 5000
                 AND valeur_fonciere > 1000
                 AND valeur_fonciere < 50000000
               GROUP BY annee
               ORDER BY annee DESC
               LIMIT ?""",
            (code_insee, max_years),
        )
        rows = cursor.fetchall()
        scope = "tous types"
    else:
        scope = dvf_type
    
    conn.close()
    
    if not rows:
        return {"data": [], "source": f"Aucune transaction DVF pour {code_insee}", "nb_annees": 0}
    
    # 3. Formater les résultats
    evolution = []
    for row in rows:
        annee, pm2_moyen, pm2_median, nb, v_moy, v_min, v_max = row
        evolution.append({
            "annee": int(annee),
            "prix_m2_moyen": round(pm2_moyen, 2) if pm2_moyen else 0,
            "prix_m2_median": round(pm2_median, 2) if pm2_median else 0,
            "nb_transactions": int(nb),
            "valeur_moyenne": round(v_moy, 0) if v_moy else 0,
            "valeur_min": round(v_min, 0) if v_min else 0,
            "valeur_max": round(v_max, 0) if v_max else 0,
        })
    
    evolution.sort(key=lambda x: x["annee"])  # ordre chronologique
    
    return {
        "evolution": evolution,
        "data": evolution,  # alias pour compatibilité
        "source": f"DVF DGFiP ({scope})",
        "code_insee": code_insee,
        "nb_annees": len(evolution),
        "tendance": _calculer_tendance(evolution),
        "valeur_actuelle": evolution[-1]["valeur_moyenne"] if evolution else None,
        "nb_transactions": sum(d["nb_transactions"] for d in evolution) if evolution else 0,
    }


def _calculer_tendance(evolution: list[dict]) -> str:
    """Calcule la tendance à partir des données d'évolution."""
    if len(evolution) < 2:
        return "stable"
    premier = evolution[0]["prix_m2_median"]
    dernier = evolution[-1]["prix_m2_median"]
    if premier == 0:
        return "stable"
    variation = round((dernier - premier) / premier * 100, 1)
    if variation > 5:
        return f"hausse ({variation:+.1f}%)"
    elif variation < -5:
        return f"baisse ({variation:+.1f}%)"
    else:
        return f"stable ({variation:+.1f}%)"


def needs_update() -> bool:
    """Vérifie si la base DVF a besoin d'être mise à jour (> 6 mois)."""
    meta = get_metadata()
    last_update = meta.get("last_update")
    if not last_update:
        return True
    try:
        last = datetime.fromisoformat(last_update)
        delta = datetime.now() - last
        return delta.days > 180  # 6 mois
    except (ValueError, TypeError):
        return True


def update_all(years: Optional[list[int]] = None) -> dict:
    """
    Exécute la mise à jour complète : téléchargement + indexation.

    Args:
        years: Années à télécharger/indexer. None = toutes les années disponibles.

    Returns:
        dict: Résultat de la mise à jour.
    """
    logger.info("=== Mise à jour DVF ===")
    
    # Étape 1 : Téléchargement
    dl_result = download_dvf_files(years)
    ok_count = sum(1 for v in dl_result.values() if v.get("status") in ("ok", "exists"))
    error_count = sum(1 for v in dl_result.values() if v.get("status") == "error")
    logger.info(f"Téléchargement : {ok_count} OK, {error_count} erreurs")

    # Étape 2 : Indexation SQLite
    meta = build_sqlite_index(years)

    return {
        "download": dl_result,
        "index": meta,
        "status": "ok" if ok_count > 0 else "error",
    }
