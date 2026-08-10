"""Génère un GLB de test à étages séparés (validation des simulations)."""
from app.digital_twin.gltf_builder import build_glb_bim

polygones = [
    {
        "exterieur": [[-10.0, -6.0], [10.0, -6.0], [10.0, 6.0], [-10.0, 6.0]],
        "trous": [],
    }
]
glb = build_glb_bim(
    polygones,
    hauteur_m=12.0,
    label="Test etages",
    mat_mur="BETON",
    mat_toit="TUILES",
    floors=3,
    pente_toit_deg=25.0,
    ridge_axis_deg=0.0,
    facades_avec_vitrage=["murs_est", "murs_ouest"],
    ratio_vitrage=0.12,
    entree_facade="murs_sud",
    etages_separes=True,
    parts_as_nodes=True,
)
with open("../frontend/bim-viewer/dist/test_floors.glb", "wb") as f:
    f.write(glb)
print("written", len(glb), "bytes")
