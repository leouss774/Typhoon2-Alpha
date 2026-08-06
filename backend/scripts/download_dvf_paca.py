"""Télécharge et décompresse les fichiers DVF (geo-dvf) pour les 6 départements PACA."""
import gzip
import os
import shutil
import urllib.request

BASE_URL = "https://files.data.gouv.fr/geo-dvf/latest/csv/2024/departements"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "lookup", "dvf")
DEPTS = ["04", "05", "06", "13", "83", "84"]

os.makedirs(OUT_DIR, exist_ok=True)

for d in DEPTS:
    gz_path = os.path.join(OUT_DIR, f"{d}.csv.gz")
    csv_path = os.path.join(OUT_DIR, f"{d}.csv")

    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        print(f"{d}.csv déjà présent, skip")
        continue

    url = f"{BASE_URL}/{d}.csv.gz"
    print(f"Téléchargement {d}.csv.gz...", flush=True)
    urllib.request.urlretrieve(url, gz_path)

    print(f"Décompression {d}.csv...", flush=True)
    with gzip.open(gz_path, "rb") as fin, open(csv_path, "wb") as fout:
        shutil.copyfileobj(fin, fout)

    # Nettoyer le .gz pour ne garder que le .csv
    os.remove(gz_path)
    print(f"OK {d}.csv ({os.path.getsize(csv_path)/1e6:.1f} Mo)", flush=True)

print("=== Tous les DVF PACA sont prêts ===")