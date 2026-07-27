"""
Agent 1 - Extracteur / constructeur du referentiel.

Lit chaque document du dossier documents/, l'envoie par morceaux au modele
Mistral avec des consignes strictes de non-invention, et sauvegarde les
fiches extraites dans data/referentiel.json.

Usage:
    python agent1_extract.py
"""
import csv
import json
import os

import config
from utils.pdf_loader import list_documents, load_text, chunk_text
from utils.mistral_client import chat_json


SYSTEM_PROMPT = """Tu es un agent de preparation d'un referentiel de recommandations de reduction
de vulnerabilite climatique pour les maisons individuelles situees en France.

Tu travailles a partir d'un extrait de document qui t'est fourni. Tu produis des fiches
structurees et tracables. Tu ne prends aucune decision technique, reglementaire, assurantielle
ou financiere: tu documentes uniquement ce que dit le texte fourni.

PERIMETRE
- Type de bien: maison individuelle.
- Territoire: France.
- Risques possibles: inondation, ruissellement, submersion, tempete, grele, canicule, secheresse,
  retrait_gonflement_argiles, feu_vegetation, et autres risques explicitement documentes.

REGLES IMPERATIVES
1. Utilise uniquement les informations presentes dans l'extrait fourni. N'ajoute aucune
   connaissance externe, n'invente aucun element.
2. Pour chaque fiche, conserve un extrait exact et court (moins de 200 caracteres) permettant de
   retrouver l'information dans la source. Sans cet extrait, ne cree pas de fiche exploitable.
3. Distingue explicitement le type de chaque fiche:
   - "recommandation_source": mesure recommandee explicitement par une source
   - "obligation_locale": obligation ou prescription reglementaire explicite (avec territoire et
     conditions d'application precises)
   - "regle_consolidee": recoupement explicite de plusieurs regles similaires dans le meme extrait
   - "estimation_cout": estimation chiffree avec devise, unite, fourchette, date, zone geo,
     hypotheses et perimetre des travaux tous presents dans la source
   - "info_aide": information sur une aide financiere, avec conditions telles que decrites par la
     source (jamais d'affirmation d'eligibilite -> statut "potential_eligibility_only")
   - "info_insuffisante": information interessante mais incomplete ou non exploitable telle quelle
4. Ne deduis jamais qu'un travail est obligatoire sauf si le texte le dit explicitement pour un
   territoire et des conditions donnes.
5. Ne produis aucun prix, montant, pourcentage de reduction du risque, rendement ou eligibilite
   definitive a une aide sans que TOUTES les informations necessaires soient presentes dans le
   texte (devise, unite, fourchette, date, zone, hypotheses, perimetre). A defaut, utilise le type
   "info_insuffisante" et laisse les champs numeriques a null.
6. Si le texte source semble commercial/publicitaire (site d'entreprise, blog commercial), tu peux
   quand meme extraire les faits mais ils doivent rester du type "info_insuffisante" sauf s'ils
   citent eux-memes une source officielle verifiable dans le texte.
7. Si l'extrait ne contient aucune information exploitable pour ce perimetre, renvoie une liste
   vide.

FORMAT DE SORTIE
Reponds UNIQUEMENT avec un objet JSON de la forme:
{"fiches": [
  {
    "type": "recommandation_source|obligation_locale|regle_consolidee|estimation_cout|info_aide|info_insuffisante",
    "alea": "nom_normalise_de_l_alea_ou_null",
    "territoire": {"echelle": "national|departemental|communal|null", "code": null},
    "zone_maison": "fondations|toiture|facade|menuiseries|ouvertures|sous_sol|jardin|null",
    "conditions_application": "texte ou null",
    "mesure": "description de la mesure de prevention/protection/adaptation/diagnostic",
    "limites_prerequis": "texte ou null",
    "cout": {"montant_min": null, "montant_max": null, "devise": null, "unite": null,
             "date_estimation": null, "zone_geo": null, "hypotheses": null},
    "aide": {"dispositif": null, "conditions": null, "statut": "potential_eligibility_only"},
    "sources": [{"extrait_exact": "citation courte exacte tiree du texte fourni"}]
  }
]}
Utilise des noms d'alea normalises en minuscules avec underscores (ex: retrait_gonflement_argiles,
inondation, tempete, grele, canicule, secheresse, feu_vegetation, submersion, ruissellement).
"""


def build_user_prompt(source_meta: dict, chunk: str) -> str:
    return f"""SOURCE ANALYSEE:
id: {source_meta.get('source_id')}
organisme: {source_meta.get('organisme')}
reference/lien: {source_meta.get('lien')}
categorie: {source_meta.get('categorie')}

EXTRAIT DU DOCUMENT:
\"\"\"
{chunk}
\"\"\"

Extrait toutes les fiches exploitables de cet extrait en respectant strictement le format et les
regles du systeme."""


def load_registry(path: str) -> dict:
    registry = {}
    if not os.path.exists(path):
        return registry
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            registry[row["fichier"]] = row
    return registry


def is_usable(fiche: dict) -> bool:
    if fiche.get("type") == "info_insuffisante":
        return False
    sources = fiche.get("sources") or []
    if not sources:
        return False
    if not sources[0].get("extrait_exact"):
        return False
    if not fiche.get("mesure"):
        return False
    return True


def load_progress():
    """Charge l'etat d'avancement (fiches deja extraites + chunks deja traites)."""
    if os.path.exists(config.PROGRESS_PATH):
        with open(config.PROGRESS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("fiches", []), set(tuple(x) for x in data.get("done_chunks", []))
    return [], set()


def save_progress(all_fiches, done_chunks):
    """Sauvegarde apres CHAQUE chunk: reprise possible sans tout refaire en cas
    de coupure reseau, timeout, ou fermeture du PC."""
    with open(config.PROGRESS_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"fiches": all_fiches, "done_chunks": [list(x) for x in done_chunks]},
            f, ensure_ascii=False,
        )
    with open(config.REFERENTIEL_PATH, "w", encoding="utf-8") as f:
        json.dump({"fiches": all_fiches}, f, ensure_ascii=False, indent=2)


def main():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    registry = load_registry(config.SOURCES_REGISTRY_PATH)
    docs = list_documents(config.DOCUMENTS_DIR)

    if not docs:
        print(f"Aucun document trouve dans {config.DOCUMENTS_DIR}/. "
              f"Mets tes PDF/txt dedans et relance.")
        return

    all_fiches, done_chunks = load_progress()
    counter = len(all_fiches)
    if done_chunks:
        print(f"Reprise: {len(done_chunks)} chunk(s) deja traites, "
              f"{len(all_fiches)} fiche(s) deja extraites.")

    for doc_path in docs:
        filename = os.path.basename(doc_path)
        meta = registry.get(filename, {
            "source_id": filename,
            "organisme": "inconnu (a completer dans sources_registry.csv)",
            "lien": filename,
            "categorie": "non_classee",
        })

        print(f"[Agent1] Lecture: {filename}")
        try:
            text = load_text(doc_path)
        except Exception as e:
            print(f"  -> erreur de lecture, fichier ignore: {e}")
            continue

        chunks = chunk_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        print(f"  -> {len(chunks)} chunk(s) a traiter")

        for i, ch in enumerate(chunks):
            chunk_key = (filename, i)
            if chunk_key in done_chunks:
                print(f"  -> chunk {i + 1}/{len(chunks)} deja traite, on passe")
                continue
            if len(ch.strip()) < 200:
                done_chunks.add(chunk_key)
                continue

            print(f"  -> extraction chunk {i + 1}/{len(chunks)}")
            try:
                result = chat_json(SYSTEM_PROMPT, build_user_prompt(meta, ch))
            except Exception as e:
                print(f"     erreur Mistral, chunk ignore pour l'instant "
                      f"(relance le script plus tard, il reprendra ici): {e}")
                # on ne marque PAS ce chunk comme "done": un prochain lancement
                # du script le retentera au lieu de le perdre silencieusement.
                continue

            for fiche in result.get("fiches", []):
                counter += 1
                fiche["id"] = f"REF-{counter:04d}"
                fiche["statut_validation"] = "validated" if is_usable(fiche) else "info_insuffisante"
                for s in fiche.get("sources", []):
                    s.setdefault("source_id", meta.get("source_id"))
                    s.setdefault("organisme", meta.get("organisme"))
                    s.setdefault("titre", meta.get("lien"))
                fiche["extraction"] = {
                    "agent": "agent1_extracteur",
                    "prompt_version": "v1.0",
                    "fichier_source": filename,
                }
                all_fiches.append(fiche)

            done_chunks.add(chunk_key)
            # sauvegarde apres chaque chunk, pas seulement a la fin du script
            save_progress(all_fiches, done_chunks)

    n_valid = sum(1 for f in all_fiches if f["statut_validation"] == "validated")
    print(f"\nTermine. {len(all_fiches)} fiches extraites, {n_valid} validees automatiquement.")
    print(f"Referentiel sauvegarde -> {config.REFERENTIEL_PATH}")


if __name__ == "__main__":
    main()
