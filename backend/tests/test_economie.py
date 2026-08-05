"""
Tests unitaires du volet économique (app/economie) — cf.
docs/STRATEGIE_RETOUR_INVESTISSEMENT.md.

Aucun appel réseau : données mockées calquées sur les formats réels de
collector_agent (catnat via libelle_risque_jo, dvf_local, bdnb).

Points vérifiés :
  - les trois statuts (calcule / fourchette / null) et leur honnêteté :
    aucun montant non-null sans liste de sources ;
  - F-B1 valeur (DVF médian x surface) ;
  - F-B2 bénéfice assurantiel (p = fréquence CATNAT, franchises D.125-5) ;
  - F-C3 AAL inondation (fourchette 0,47-0,98 % de la valeur) ;
  - niveau A : Δ score via _combine_risk (moteur du projet) ;
  - F-B3 coût net FPRNM plafonné ; F-D1 temps de retour seulement si
    bénéfice > 0.
"""

from __future__ import annotations

import math

from app.economie.aal import aal_inondation
from app.economie.benefice_assurance import benefice_assurance
from app.economie.effet_travaux import appliquer_effets
from app.economie.service import compute_retour_investissement
from app.economie.valuateur import estimer_valeur
from app.scoring.risk_model import ZONE_NAMES, _clamp, _combine_risk, _score_global


# ---------------------------------------------------------------------------
#   Données mockées
# ---------------------------------------------------------------------------

def _fake_building_data(
    nb_secheresse: int = 0,
    nb_inondation: int = 0,
    zones_inondables: bool = False,
    dvf: bool = True,
    surface_m2: float | None = 100.0,
) -> dict:
    catnat_data = [{"libelle_risque_jo": "Sécheresse"}] * nb_secheresse
    catnat_data += [{"libelle_risque_jo": "Inondations et/ou Coulées de Boue"}] * nb_inondation

    dvf_local = None
    if dvf:
        dvf_local = [
            {
                "nature_mutation": "Vente",
                "type_local": "Maison",
                "valeur_fonciere": 200_000.0,
                "surface_reelle_bati": 100.0,
            },
            {
                "nature_mutation": "Vente",
                "type_local": "Maison",
                "valeur_fonciere": 300_000.0,
                "surface_reelle_bati": 100.0,
            },
            {
                "nature_mutation": "Vente",
                "type_local": "Appartement",
                "valeur_fonciere": 400_000.0,
                "surface_reelle_bati": 100.0,
            },
        ]

    bdnb_batiment = {}
    if surface_m2 is not None:
        bdnb_batiment["surface_emprise_sol"] = surface_m2

    return {
        "adresse": {"label": "10 Rue Test, 75000 Paris", "citycode": "75056"},
        "bdnb": {"batiment": bdnb_batiment},
        "georisques": {
            "catnat": {"data": catnat_data} if catnat_data else {"data": []},
            "zones_inondables": {"data": [{"id": "AZI"}]} if zones_inondables else None,
        },
        "dvf_local": dvf_local,
    }


def _reco(mesure: str, montant_min: float | None = None, montant_max: float | None = None,
          fprnm: bool = False) -> dict:
    cout = None
    if montant_min is not None or montant_max is not None:
        cout = {
            "montant_min": montant_min,
            "montant_max": montant_max,
            "devise": "EUR",
            "unite": "global",
            "date_estimation": None,
            "zone_geo": "France",
            "hypotheses": None,
        }
    return {
        "mesure": mesure,
        "explication": "explication",
        "risque_concerne": "inondation",
        "type": "recommandation_source",
        "cout_estime": cout,
        "aide": {"dispositif": "Fonds Barnier / FPRNM" if fprnm else None, "statut": "potential_eligibility_only"},
        "sources": [{"fiche_id": "REF-X", "source_id": "S01", "extrait_exact": "..."}],
    }


def _fake_risk_scores(
    fondations_f: float = 50.0,
    fondations_v: float = 50.0,
    recos_fondations: list[dict] | None = None,
    recos_sous_sol: list[dict] | None = None,
) -> dict:
    zones: dict = {}
    for name in ZONE_NAMES:
        zones[name] = {
            "risque": _clamp(_combine_risk(20.0, 50.0)),
            "niveau": "modere",
            "alea_principal": "Inondation",
            "justification": "j",
            "_f_score": 20.0,
            "_v_score": 50.0,
            "recommandations": [],
        }

    zones["fondations"]["_f_score"] = fondations_f
    zones["fondations"]["_v_score"] = fondations_v
    zones["fondations"]["risque"] = _clamp(_combine_risk(fondations_f, fondations_v))
    zones["fondations"]["alea_principal"] = "Retrait-gonflement des argiles"
    zones["fondations"]["recommandations"] = list(recos_fondations or [])

    zones["sous_sol"]["_f_score"] = 50.0
    zones["sous_sol"]["_v_score"] = 50.0
    zones["sous_sol"]["risque"] = _clamp(_combine_risk(50.0, 50.0))
    zones["sous_sol"]["recommandations"] = list(recos_sous_sol or [])

    return {"zones": zones, "score_global": _score_global(zones)}


# ---------------------------------------------------------------------------
#   F-B1 — valeur du bien
# ---------------------------------------------------------------------------

def test_estimer_valeur_calcule():
    data = _fake_building_data(dvf=True, surface_m2=100.0)
    res = estimer_valeur(data)
    # prix/m² : 2000, 3000, 4000 -> médiane 3000 ; V = 3000 x 100
    assert res["valeur_reconstruction"]["statut"] == "calcule"
    assert res["valeur_reconstruction"]["valeur"] == 300_000
    assert res["prix_m2_median"]["valeur"] == 3_000
    assert res["statut"] == "calcule"
    print("test_estimer_valeur_calcule OK")


def test_estimer_valeur_null_sans_dvf():
    res = estimer_valeur(_fake_building_data(dvf=False, surface_m2=100.0))
    assert res["valeur_reconstruction"]["statut"] == "null"
    assert res["valeur_reconstruction"]["raison"]
    print("test_estimer_valeur_null_sans_dvf OK")


def test_estimer_valeur_null_sans_surface():
    res = estimer_valeur(_fake_building_data(dvf=True, surface_m2=None))
    assert res["valeur_reconstruction"]["statut"] == "null"
    assert res["prix_m2_median"]["statut"] == "calcule"
    print("test_estimer_valeur_null_sans_surface OK")


# ---------------------------------------------------------------------------
#   F-B2 — bénéfice assurantiel
# ---------------------------------------------------------------------------

def test_benefice_assurance_rga():
    data = _fake_building_data(nb_secheresse=3, nb_inondation=2)
    res = benefice_assurance(data)
    rga = res["par_alea"]["retrait_gonflement_argiles"]
    assert rga["nb_arretes"] == 3
    assert rga["probabilite_annuelle"] == 0.1
    # B = 0.1 x (16500-1520)=1498 ... 0.1 x (21000-1520)=1948
    assert rga["benefice"]["statut"] == "fourchette"
    assert math.isclose(rga["benefice"]["min"], 0.1 * (16_500 - 1_520), abs_tol=1.0)
    assert math.isclose(rga["benefice"]["max"], 0.1 * (21_000 - 1_520), abs_tol=1.0)
    # Inondation : p = 2/30, franchise 380 €, sinistre 10 900-17 800 €
    inond = res["par_alea"]["inondation"]
    assert math.isclose(inond["probabilite_annuelle"], 2 / 30, rel_tol=1e-3)
    total = res["total"]
    assert total["statut"] == "fourchette"
    assert total["min"] > rga["benefice"]["min"]
    assert total["max"] > rga["benefice"]["max"]
    print("test_benefice_assurance_rga OK")


def test_benefice_assurance_null_sans_catnat():
    data = _fake_building_data(nb_secheresse=0, nb_inondation=0)
    data["georisques"]["catnat"] = {}
    res = benefice_assurance(data)
    assert res["total"]["statut"] == "null"
    assert res["modulation_surprime"]["statut"] == "cadre_reglementaire_a_venir"
    print("test_benefice_assurance_null_sans_catnat OK")


# ---------------------------------------------------------------------------
#   Niveau A — Δ score
# ---------------------------------------------------------------------------

def test_effet_travaux_reduit_fondations():
    recos = [_reco("Mise en place d'un drainage périphérique")]
    rs = _fake_risk_scores(fondations_f=50.0, fondations_v=50.0, recos_fondations=recos)
    res = appliquer_effets(rs)
    assert res["statut"] == "calcule"
    fond = next(z for z in res["par_zone"] if z["zone"] == "fondations")
    # F: 50 -> 50 x 0.7 = 35 ; R_apres = 100 x sqrt(0.35) x sqrt(0.5) ~ 41.8 -> 42
    assert fond["risque_avant"] == 50
    assert fond["risque_apres"] < fond["risque_avant"]
    assert fond["delta"] > 0
    assert res["delta_global"] > 0
    print("test_effet_travaux_reduit_fondations OK")


def test_effet_travaux_aucune_application():
    recos = [_reco("Bonne pratique générale non chiffrée")]
    rs = _fake_risk_scores(recos_fondations=recos)
    res = appliquer_effets(rs)
    assert res["statut"] == "null"
    assert res["delta_global"] == 0
    print("test_effet_travaux_aucune_application OK")


# ---------------------------------------------------------------------------
#   F-C3 — AAL inondation
# ---------------------------------------------------------------------------

def test_aal_inondation_fourchette():
    valeur = estimer_valeur(_fake_building_data(dvf=True, surface_m2=100.0))
    data = _fake_building_data(nb_inondation=3, zones_inondables=True)
    res = aal_inondation(valeur, data)
    assert res["statut"] == "fourchette"
    assert math.isclose(res["min"], 0.0047 * 300_000, abs_tol=1.0)
    assert math.isclose(res["max"], 0.0098 * 300_000, abs_tol=1.0)
    print("test_aal_inondation_fourchette OK")


def test_aal_null_sans_inondation():
    valeur = estimer_valeur(_fake_building_data(dvf=True, surface_m2=100.0))
    data = _fake_building_data(nb_secheresse=5)
    res = aal_inondation(valeur, data)
    assert res["statut"] == "null"
    print("test_aal_null_sans_inondation OK")


# ---------------------------------------------------------------------------
#   F-B3 + F-D1 — coût net / retour sur investissement
# ---------------------------------------------------------------------------

def test_cout_travaux_fprnm_cap():
    recos = [
        _reco("Mise en place d'un drainage périphérique", montant_min=50_000, montant_max=60_000, fprnm=True),
        _reco("Installation de batardeaux", montant_min=3_000, montant_max=5_000, fprnm=False),
    ]
    rs = _fake_risk_scores(recos_fondations=recos[:1], recos_sous_sol=recos[1:])
    valeur = estimer_valeur(_fake_building_data(dvf=True, surface_m2=100.0))
    res = compute_retour_investissement(
        _fake_building_data(dvf=True, surface_m2=100.0, nb_secheresse=3, nb_inondation=2),
        rs,
        surface_m2=100.0,
    )
    cout = res["niveau_b"]["cout_travaux"]
    # total brut : 53 000 ... 65 000
    assert cout["total_brut"]["min"] == 53_000
    assert cout["total_brut"]["max"] == 65_000
    # subvention : 80 % de 50 000 (mesure éligible) = 40 000, plafonné à 36 000 €
    assert cout["subvention_fprnm"]["min"] == 36_000
    assert cout["cout_net"]["min"] == 53_000 - 36_000
    assert res["roi"]["temps_de_retour"]["statut"] == "fourchette"
    assert res["roi"]["temps_de_retour"]["min"] > 0
    print("test_cout_travaux_fprnm_cap OK")


def test_roi_null_sans_benefice():
    recos = [_reco("Installation de batardeaux", montant_min=5_000, montant_max=8_000)]
    rs = _fake_risk_scores(recos_sous_sol=recos)
    data = _fake_building_data(dvf=True, surface_m2=100.0, nb_secheresse=0, nb_inondation=0)
    res = compute_retour_investissement(data, rs, surface_m2=100.0)
    tr = res["roi"]["temps_de_retour"]
    assert tr["statut"] == "null"
    assert "nul" in tr["raison"]
    print("test_roi_null_sans_benefice OK")


# ---------------------------------------------------------------------------
#   Honnêteté : aucun montant sans source
# ---------------------------------------------------------------------------

def _iter_blocs(obj):
    if isinstance(obj, dict):
        if "statut" in obj and "sources" in obj:
            yield obj
        for v in obj.values():
            yield from _iter_blocs(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_blocs(v)


def test_deduplication_facade_cout():
    """Le coût d'une reco façade (dupliquée sur les 4 murs_*) n'est compté qu'une fois."""
    hydro = _reco("Traitement hydrofuge de la facade", montant_min=2_000, montant_max=3_000, fprnm=False)
    rs = _fake_risk_scores()
    for murs in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        rs["zones"][murs]["recommandations"] = [dict(hydro)]
    data = _fake_building_data(nb_secheresse=3, nb_inondation=2, dvf=True, surface_m2=100.0)
    res = compute_retour_investissement(data, rs, surface_m2=100.0)
    cout = res["niveau_b"]["cout_travaux"]
    assert cout["total_brut"]["min"] == 2_000
    assert cout["total_brut"]["max"] == 3_000
    assert cout["n_avec_cout"] == 1
    # et côté niveau A : une seule entrée par_mesure pour l'hydrofuge
    nb_hydro = [m for m in res["niveau_a"]["par_mesure"] if m.get("statut") != "null" and "hydrofuge" in m["mesure"].lower()]
    assert len(nb_hydro) == 1
    print("test_deduplication_facade_cout OK")


def test_aucun_montant_sans_source():
    rs = _fake_risk_scores(
        recos_fondations=[_reco("Mise en place d'un drainage périphérique", 8_000, 12_000, fprnm=True)],
        recos_sous_sol=[_reco("Installation de batardeaux", 3_000, 5_000)],
    )
    data = _fake_building_data(nb_secheresse=3, nb_inondation=2, zones_inondables=True, dvf=True, surface_m2=100.0)
    res = compute_retour_investissement(data, rs, surface_m2=100.0)
    n_blocs = 0
    for b in _iter_blocs(res):
        if b["statut"] == "null":
            continue
        n_blocs += 1
        assert b["sources"], f"Montant {b} sans source !"
    assert n_blocs > 0
    # valeur_immobiliere est qualitatif et exclu du ROI
    assert res["valeur_immobiliere"]["exclu_du_roi"] is True
    print("test_aucun_montant_sans_source OK")


# ---------------------------------------------------------------------------
#   Execution
# ---------------------------------------------------------------------------

def _run_all():
    test_estimer_valeur_calcule()
    test_estimer_valeur_null_sans_dvf()
    test_estimer_valeur_null_sans_surface()
    test_benefice_assurance_rga()
    test_benefice_assurance_null_sans_catnat()
    test_effet_travaux_reduit_fondations()
    test_effet_travaux_aucune_application()
    test_aal_inondation_fourchette()
    test_aal_null_sans_inondation()
    test_cout_travaux_fprnm_cap()
    test_roi_null_sans_benefice()
    test_deduplication_facade_cout()
    test_aucun_montant_sans_source()
    print("\n=== TOUS LES TESTS ECONOMIE PASSENT ===")


if __name__ == "__main__":
    _run_all()
