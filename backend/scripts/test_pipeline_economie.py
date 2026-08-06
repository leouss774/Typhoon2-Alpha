"""Test le pipeline économique complet via l'API backend."""
import json
import sys
import time
import urllib.request

BASE = "http://localhost:8765"

def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))

# 1. /diagnostic/fast — collecte + scoring
print("=" * 70)
print("Étape 1 : /diagnostic/fast")
t0 = time.time()
fast = post("/diagnostic/fast", {
    "adresse": "10 Promenade des Anglais, 06000 Nice",
    "copernicus": False,
})
print(f"  OK en {time.time()-t0:.1f}s")
print(f"  adresse: {fast.get('adresse')}")
print(f"  score_global: {fast.get('score_global')}")
print(f"  dvf_local: {fast.get('_resume',{}).get('building_data',{}).get('dvf_local') is not None}")
bdnb = fast.get('_resume',{}).get('building_data',{}).get('bdnb') or {}
batiment = bdnb.get('batiment') or {}
print(f"  surface: {batiment.get('surface_emprise_sol')}")

# 2. /diagnostic/recommandations — avec fallback
resume = fast.get("_resume", {})
print("\nÉtape 2 : /diagnostic/recommandations (fallback si Mistral down)")
t0 = time.time()
try:
    recos = post("/diagnostic/recommandations", {
        "building_data": resume.get("building_data"),
        "risk_scores": resume.get("risk_scores"),
        "formulaire": None,
    })
    print(f"  OK en {time.time()-t0:.1f}s")
    nb_recos = sum(len(z.get("recommandations", [])) for z in recos.get("zones", {}).values())
    print(f"  recommandations: {nb_recos}")
    # Afficher les reco de fondations
    fond = recos.get("zones", {}).get("fondations", {})
    for r in fond.get("recommandations", [])[:2]:
        c = r.get("cout_estime") or {}
        print(f"    - {r.get('mesure')}: {c.get('montant_min')}-{c.get('montant_max')} €")
except Exception as e:
    print(f"  ÉCHEC: {e}")

# 3. /diagnostic/retour-investissement — calcul économique
print("\nÉtape 3 : /diagnostic/retour-investissement")
t0 = time.time()
try:
    # Même logique que frontend/api.ts : surface_emprise_m2 sinon largeur × longueur
    geom = fast.get("geometry", {}) or {}
    surface_m2 = geom.get("surface_emprise_m2")
    if not surface_m2 and geom.get("largeur_m") and geom.get("longueur_m"):
        surface_m2 = geom["largeur_m"] * geom["longueur_m"]
    risk_scores_final = {"zones": recos.get("zones")} if recos.get("zones") else resume.get("risk_scores", {})
    eco = post("/diagnostic/retour-investissement", {
        "building_data": resume.get("building_data"),
        "risk_scores": risk_scores_final,
        "surface_m2": surface_m2,
    })
    print(f"  OK en {time.time()-t0:.1f}s")
    valeur = eco.get("valeur", {}).get("valeur_reconstruction", {})
    cout = eco.get("niveau_b", {}).get("cout_travaux", {}).get("cout_net", {})
    bene = eco.get("niveau_b", {}).get("benefice_assurance", {}).get("total", {})
    roi = eco.get("roi", {}).get("temps_de_retour", {})
    print(f"  Valeur du bien: {valeur.get('statut')} = {valeur.get('valeur')} €")
    print(f"  Coût net travaux: {cout.get('statut')} = {cout.get('min')}-{cout.get('max')} €")
    print(f"  Bénéfice assurance: {bene.get('statut')} = {bene.get('min')}-{bene.get('max')} €")
    print(f"  Temps de retour: {roi.get('statut')} = {roi.get('min')}-{roi.get('max')} ans")
    conf = eco.get("confidence", {})
    print(f"  Confiance: {conf.get('niveau')} ({conf.get('score')}/100)")
    print("\n=== PIPELINE COMPLET OK ===")
except Exception as e:
    print(f"  ÉCHEC: {e}")