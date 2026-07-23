"""
Script principal : lance l'agent Digital Twin sur un fichier JSON d'entrée.

Usage :
    python run.py nantes_input.json
    python run.py nantes_input.json --output nantes_output.json
    python run.py nantes_input.json --vuln
"""
import json
import sys
import os
import argparse

# Forcer UTF-8 sur Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from .digital_twin_agent import DigitalTwinAgent
except ImportError:
    from digital_twin_agent import DigitalTwinAgent


def main():
    parser = argparse.ArgumentParser(
        description="Digital Twin Agent — Analyse de risques depuis JSON unifie",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  python run.py nantes_input.json
  python run.py nantes_input.json --output nantes_risques.json
  python run.py nantes_input.json --vuln
        """
    )
    parser.add_argument("input",         help="Fichier JSON d'entree (user_data + agent_data + step7)")
    parser.add_argument("--output", "-o", default=None, help="Fichier JSON de sortie (defaut: <input>_output.json)")
    parser.add_argument("--api-key",      default=None, help="Cle API Mistral")
    parser.add_argument("--vuln",         action="store_true", help="Test de vulnerabilite rapide en plus")
    parser.add_argument("--quiet", "-q",  action="store_true", help="Mode silencieux (pas de log dans le terminal)")
    args = parser.parse_args()

    # Config API key
    if args.api_key:
        os.environ["MISTRAL_API_KEY"] = args.api_key

    # Fichier de sortie par defaut
    if args.output is None:
        base = os.path.splitext(args.input)[0]
        args.output = base + "_output.json"

    # Charger le JSON d'entree
    print(f"\n[>>] Chargement : {args.input}")
    with open(args.input, "r", encoding="utf-8") as f:
        input_json = json.load(f)

    adresse = (
        input_json.get("user_data", {}).get("adresse")
        or input_json.get("agent_data", {}).get("adresse")
        or "Adresse inconnue"
    )
    print(f"[>>] Adresse    : {adresse}")
    print(f"[>>] Sortie     : {args.output}")
    print("-" * 60)

    # Initialiser l'agent
    agent = DigitalTwinAgent()

    # ── Analyse principale ────────────────────────────────────────────────────
    print("[>>] Appel Mistral — analyse des risques en cours...")
    resultat = agent.genererDepuisJSON(input_json)

    # ── Test de vulnerabilite optionnel ───────────────────────────────────────
    if args.vuln:
        coordonnees = input_json.get("agent_data", {}).get("coordonnees", {})
        lat = coordonnees.get("latitude", 0)
        lon = coordonnees.get("longitude", 0)
        print(f"\n[>>] Test vulnerabilite rapide ({lat}, {lon})...")
        vuln = agent.testVulnerabilite(lat, lon, adresse=adresse)
        resultat["_test_vulnerabilite"] = vuln
        print(f"     Verdict : {vuln.get('verdict', '?')} ({vuln.get('score_risque', '?')}/100) en {vuln.get('delai_reponse_ms', '?')}ms")

    # ── Sauvegarder ──────────────────────────────────────────────────────────
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)

    # ── Afficher le résumé ───────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  RESULTATS")
    print("=" * 60)

    sg = resultat.get("score_global", {})
    perf = resultat.get("_performance", {})
    erreur = resultat.get("_erreur")

    if erreur:
        print(f"[!] ERREUR : {erreur.get('message', 'Inconnue')}")
    else:
        print(f"  Score global   : {sg.get('note', '?')}/100 (classe {sg.get('classe', '?')})")
        print(f"  Resilience     : {sg.get('score_resilience', '?')}/100")
        print(f"  Vulnerabilite  : {sg.get('score_vulnerabilite', '?')}/100")
        print(f"  Interpretation : {sg.get('interpretation', '')[:80]}")
        print(f"  JSON valide    : {perf.get('json_valide', '?')}")
        print(f"  Duree          : {perf.get('duree_analyse_s', '?')}s")

        # Risques actuels
        print("\n  RISQUES ACTUELS :")
        risques = resultat.get("risques_actuels", {})
        for nom, r in risques.items():
            if isinstance(r, dict):
                score = r.get("score", 0)
                niveau = r.get("niveau", "?")
                barre = "#" * int(score / 10) + "-" * (10 - int(score / 10))
                print(f"    {nom:35s} [{barre}] {score:3d}/100  {niveau}")

        # Risques 2050 (apercu)
        rf = resultat.get("risques_futurs_2050", {})
        rcp85 = rf.get("scenario_rcp85", {})
        if rcp85:
            print("\n  PROJECTION 2050 (RCP 8.5 — scenario pessimiste) :")
            for nom in ["inondation", "chaleur_extreme", "secheresse", "incendie_foret"]:
                r = rcp85.get(nom, {})
                if r:
                    print(f"    {nom:35s} {r.get('score', '?'):3}/100  {r.get('niveau', '?')}")

        # Recommandations urgentes
        recs_urgentes = resultat.get("recommandations", {}).get("urgentes", [])
        if recs_urgentes:
            print(f"\n  RECOMMANDATIONS URGENTES ({len(recs_urgentes)}) :")
            for r in recs_urgentes[:3]:
                cout = r.get("cout_estime_eur")
                cout_str = f"  ~{cout:,.0f}EUR" if cout else ""
                print(f"    [P{r.get('priorite','?')}] {r.get('titre', '?')[:60]}{cout_str}")

        # Simulation
        sim = resultat.get("simulation_periode", {})
        if sim:
            cout_cumule = sim.get("cout_risque_cumule_estime")
            if cout_cumule:
                print(f"\n  Cout risques cumules 2050 : {cout_cumule:,.0f} EUR")
            print(f"  Assurabilite             : {sim.get('indice_assurabilite', '?')}")

    print("\n" + "=" * 60)
    print(f"  [OK] Fichier sauvegarde : {args.output}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
