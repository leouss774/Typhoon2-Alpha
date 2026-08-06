"""Debug valeur avec DVF."""
import sys
sys.path.insert(0, r"c:\Users\USER\Desktop\cout\Typhoon2-Alpha\backend")

from app.connectors.dvf_lookup import lookup_dvf
from app.economie.valuateur import estimer_valeur

# Récupérer le dvf_local
dvf = lookup_dvf("06088")
print(f"dvf_local: {len(dvf)} transactions")

# Construire building_data minimal
building_data = {
    "adresse": {"label": "Test", "citycode": "06088"},
    "bdnb": {"batiment": {"surface_emprise_sol": 64.0}},
    "dvf_local": dvf,
}

res = estimer_valeur(building_data, surface_m2=64.0)
print(f"\nRésultat estimer_valeur:")
print(f"  statut: {res['statut']}")
print(f"  surface: {res['surface_m2']}")
print(f"  nb_transactions: {res['nb_transactions_dvf']}")
pm = res["prix_m2_median"]
print(f"  prix_m2_median: {pm}")
print(f"  valeur: {res['valeur_reconstruction']}")

# Test manuel du prix m2 median
from app.economie.valuateur import _prix_m2_median
prix = _prix_m2_median(dvf)
print(f"\n  _prix_m2_median manuel: {prix}")
if dvf:
    for t in dvf[:3]:
        print(f"    nature={t.get('nature_mutation')} type={t.get('type_local')} valeur={t.get('valeur_fonciere')} surface={t.get('surface_reelle_bati')}")