"""Test lookup DVF."""
import sys
sys.path.insert(0, r"c:\Users\USER\Desktop\cout\Typhoon2-Alpha\backend")

from app.connectors.dvf_lookup import lookup_dvf

r = lookup_dvf("06088")
print(f"Nb transactions: {len(r)}")
for t in r[:5]:
    print(f"  {t.get('type_local')} | {t.get('valeur_fonciere')} | {t.get('surface_reelle_bati')} m2")