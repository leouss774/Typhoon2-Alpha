#!/usr/bin/env python3
"""
Peuple automatiquement data/sources_registry.csv en analysant les documents
du dossier documents/ avec Mistral.

Pour chaque fichier non encore reference dans le registre, le script :
1. Lit les premieres pages du document (ou les 4000 premiers caracteres)
2. Envoie cet extrait a Mistral qui suggere : organisme, lien, categorie
3. Ajoute la ligne au registre CSV

Usage :
    python populate_registry.py

Options :
    --dry-run   Affiche ce qui serait ajoute sans modifier le CSV
    --overwrite Re-analyse et remplace les entrees existantes
"""

import argparse
import csv
import os
import re
import sys

import config
from utils.mistral_client import chat_json
from utils.pdf_loader import list_documents, load_text


CATEGORIES_CONNUES = [
    "reglementaire_technique",
    "officiel_technique",
    "officiel",
    "scientifique",
    "scientifique_technique",
    "technique",
    "commercial",
    "piste_commerciale_uniquement",
    "non_classee",
]

SYSTEM_PROMPT = """Tu es un assistant qui analyse des documents techniques (PDF, guides, normes)
sur la construction, la renovation et la vulnerabilite climatique des batiments.

Tu recois le debut d'un document. Tu dois en extraire les metadonnees suivantes :

1. **organisme** : le nom de l'organisme ou de l'editeur du document
   (ex: ADEME, BRGM, CSTB, FFB, Ministere, etc.)
2. **lien** : le site web ou la reference du document, si identifiable dans le texte
   (ex: https://librairie.ademe.fr/, fichier local)
3. **categorie** : la categorie la plus adaptee parmi la liste fournie

Categories possibles :
- reglementaire_technique : normes, DTU, regles de l'art
- officiel_technique : guide officiel (ADEME, ministere, etc.)
- officiel : document officiel general
- scientifique : etude, rapport scientifique
- scientifique_technique : document a la fois scientifique et technique
- technique : guide technique non officiel
- commercial : document a but commercial ou publicitaire
- piste_commerciale_uniquement : source purement commerciale sans valeur reglementaire
- non_classee : aucune categorie pertinente

Si tu ne peux pas determiner l'organisme, reponds "inconnu".
Si tu ne peux pas determiner le lien, reponds le nom du fichier.
Si tu ne peux pas determiner la categorie, reponds "non_classee".

Reponds UNIQUEMENT avec un objet JSON valide, sans texte autour :
{"organisme": "...", "lien": "...", "categorie": "..."}"""


FIELD_NAMES = ["source_id", "organisme", "fichier", "lien", "categorie"]


def next_source_id(registry_rows: list) -> str:
    """Genere le prochain ID source (S01, S02, ...) en fonction des lignes existantes."""
    max_num = 0
    for row in registry_rows:
        sid = row.get("source_id", "")
        m = re.search(r"S(\d+)", sid)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"S{max_num + 1:02d}"


def sample_document(filepath: str, max_chars: int = 4000):
    """Extrait le debut d'un document pour analyse.
    Retourne (succes: bool, contenu_ou_erreur: str)."""
    try:
        text = load_text(filepath)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n[... tronque ...]"
        return True, text
    except Exception as e:
        return False, str(e)


def analyze_with_llm(filepath: str, filename: str) -> dict:
    """Utilise Mistral pour suggerer les metadonnees d'un document."""
    success, sample = sample_document(filepath)
    if not success:
        print(f"    Erreur de lecture: {sample}")
        return {"organisme": "inconnu", "lien": filename, "categorie": "non_classee"}

    user_prompt = f"""Analyse le document suivant et suggere ses metadonnees.

Nom du fichier : {filename}

DEBUT DU DOCUMENT :
\"\"\"
{sample}
\"\"\"

Retourne un JSON avec : organisme, lien, categorie.
"""
    try:
        result = chat_json(SYSTEM_PROMPT, user_prompt, max_retries=2)
        organisme = result.get("organisme", "inconnu").strip()
        lien = result.get("lien", filename).strip()
        categorie = result.get("categorie", "non_classee").strip()

        if categorie not in CATEGORIES_CONNUES:
            categorie = "non_classee"

        return {"organisme": organisme, "lien": lien, "categorie": categorie}
    except Exception as e:
        print(f"    Erreur analyse LLM: {e}")
        return {"organisme": "inconnu", "lien": filename, "categorie": "non_classee"}


def read_all_rows(path: str) -> list:
    """Lit toutes les lignes du CSV (incluant l'en-tete)."""
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_all_rows(path: str, rows: list):
    """Ecrit toutes les lignes dans le CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELD_NAMES)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Peuple le registre des sources")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche ce qui serait ajoute sans modifier le CSV"
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-analyse et remplace les entrees existantes"
    )
    args = parser.parse_args()

    if not os.path.isdir(config.DOCUMENTS_DIR):
        print(f"Le dossier {config.DOCUMENTS_DIR}/ n'existe pas. "
              f"Cree-le et mets-y des documents.")
        sys.exit(1)

    # Verification prealable de la cle API
    if not config.MISTRAL_API_KEY:
        print("Erreur : MISTRAL_API_KEY non definie. "
              "Cree un fichier .env avec la ligne : MISTRAL_API_KEY=ta_cle")
        sys.exit(1)

    os.makedirs(config.DATA_DIR, exist_ok=True)

    # Lit toutes les lignes existantes
    existing_rows = read_all_rows(config.SOURCES_REGISTRY_PATH)
    existing_by_file = {r["fichier"]: r for r in existing_rows}

    docs = list_documents(config.DOCUMENTS_DIR)
    if not docs:
        print(f"Aucun document trouve dans {config.DOCUMENTS_DIR}/.")
        sys.exit(0)

    print(f"Registre existant : {len(existing_rows)} entree(s)")
    print(f"Documents trouves : {len(docs)} dans {config.DOCUMENTS_DIR}/\n")

    new_rows = []  # Lignes a ajouter ou a remplacer

    for doc_path in docs:
        filename = os.path.basename(doc_path)

        if filename in existing_by_file and not args.overwrite:
            print(f"  [OK]  {filename}  -> deja dans le registre")
            continue

        action_label = "[MAJ]" if filename in existing_by_file else "[NOV]"
        print(f"  {action_label} {filename}...")

        meta = analyze_with_llm(doc_path, filename)

        # Conserve l'ID d'origine quand on remplace une entree existante
        if filename in existing_by_file:
            new_id = existing_by_file[filename]["source_id"]
        else:
            new_id = next_source_id(existing_rows + new_rows)

        entry = {
            "source_id": new_id,
            "organisme": meta["organisme"],
            "fichier": filename,
            "lien": meta["lien"],
            "categorie": meta["categorie"],
        }

        print(f"    -> ID: {new_id}, Organisme: {meta['organisme']}, "
              f"Categorie: {meta['categorie']}")

        new_rows.append(entry)

    if not new_rows:
        print("\nAucune nouvelle entree a ajouter.")
        return

    if args.dry_run:
        print(f"\n--- Mode dry-run : {len(new_rows)} entree(s) auraient ete modifiees ---")
        for e in new_rows:
            print(f"  {e['source_id']} | {e['organisme']:30s} | "
                  f"{e['fichier']:40s} | {e['categorie']}")
        return

    # Construction du jeu final : on remplace les anciennes entrees
    # par les nouvelles (si --overwrite) ou on ajoute les nouvelles
    final_by_file = {r["fichier"]: r for r in existing_rows}
    for e in new_rows:
        final_by_file[e["fichier"]] = e

    final_rows = list(final_by_file.values())
    write_all_rows(config.SOURCES_REGISTRY_PATH, final_rows)

    n_added = sum(1 for e in new_rows if e["fichier"] not in existing_by_file)
    n_updated = sum(1 for e in new_rows if e["fichier"] in existing_by_file)

    print(f"\n✅ {n_added} ajout(s), {n_updated} mise(s) a jour "
          f"dans {config.SOURCES_REGISTRY_PATH}")

    # Affiche le registre mis a jour
    print(f"\nRegistre mis a jour :")
    for row in final_rows:
        print(f"  {row['source_id']} | {row['organisme']:30s} | {row['fichier']}")

    print(f"\nAstuce : verifie/modifie les suggestions dans le CSV "
          f"avant de lancer agent1_extract.py.")


if __name__ == "__main__":
    main()
