"""
Adaptateur d'entrée : convertit le format JSON unifié
(user_data + agent_data + step7) vers le format interne de l'agent.
"""
from typing import Dict, Any, Optional


def adapter_input(input_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Prend le JSON d'entrée unifié et retourne un tuple
    (donnees_risk_engine, formulaire) prêt pour genererAnalyse().

    Format d'entrée supporté :
        { "user_data": {...}, "agent_data": {...}, "step7": {...} }

    Ou le format legacy :
        { "formulaire": {...}, "donnees_risk_engine": {...} }
    """
    # ── Format legacy déjà structuré ──────────────────────────────────────────
    if "formulaire" in input_json and "donnees_risk_engine" in input_json:
        return input_json["donnees_risk_engine"], input_json["formulaire"]

    # ── Nouveau format unifié ─────────────────────────────────────────────────
    user_data  = input_json.get("user_data", {})
    agent_data = input_json.get("agent_data", {})
    step7      = input_json.get("step7", {})

    coordonnees    = agent_data.get("coordonnees", {})
    georisques_raw = agent_data.get("georisques", {})
    risk_context   = step7.get("risk_context", {})
    profil_bien    = step7.get("profil_bien", {})
    score_step7    = step7.get("score", {})
    perils         = score_step7.get("perils", {})

    # ── Formulaire client ─────────────────────────────────────────────────────
    formulaire = {
        "adresse"            : user_data.get("adresse") or agent_data.get("adresse", ""),
        "type_bien"          : user_data.get("type_bien", "maison"),
        "surface_m2"         : user_data.get("surface", 0),
        "surface_terrain_m2" : user_data.get("surface_terrain_m2"),
        "nb_etages"          : user_data.get("nb_etages", 1),
        "annee_construction" : user_data.get("annee_construction"),
        "annee_renovation"   : user_data.get("annee_renovation"),
        "type_structure"     : user_data.get("type_structure"),
        "etat_structure"     : user_data.get("etat_structure"),
        "fissures"           : user_data.get("fissures"),
        "affaissement"       : user_data.get("affaissement"),
        "type_toiture"       : user_data.get("type_toiture"),
        "age_toiture"        : user_data.get("age_toiture"),
        "etat_toiture"       : user_data.get("etat_toiture"),
        "infiltrations"      : user_data.get("infiltrations"),
        "presence_sous_sol"  : user_data.get("presence_sous_sol", False),
        "presence_cave"      : user_data.get("presence_cave", False),
        "occupation"         : user_data.get("occupation"),
        "installation_electrique_annee": user_data.get("installation_electrique_annee"),
        "lat"                : coordonnees.get("latitude"),
        "lon"                : coordonnees.get("longitude"),
    }

    # ── Données Géorisques normalisées ────────────────────────────────────────
    argiles = georisques_raw.get("argiles_rga", [{}])
    seisme  = georisques_raw.get("zonage_sismique", [{}])
    catnat  = georisques_raw.get("catnat", {})
    radon   = georisques_raw.get("radon", {})

    # Récupère aussi depuis risk_context (plus détaillé)
    rc_catnat  = risk_context.get("historique_catnat", {})
    rc_topo    = risk_context.get("donnees_topo", {})
    rc_seisme  = risk_context.get("zone_sismique", {})
    rc_radon   = risk_context.get("radon", {})
    rc_rga     = risk_context.get("rga", {})
    rc_cavites = risk_context.get("cavites", {})

    # ── Données risk engine complètes ─────────────────────────────────────────
    donnees_risk_engine = {
        "coordonnees": {
            "lat": coordonnees.get("latitude", 0),
            "lon": coordonnees.get("longitude", 0)
        },
        "commune": {
            "nom"         : _extraire_commune(user_data.get("adresse", "")),
            "code_insee"  : agent_data.get("code_insee", ""),
            "departement" : agent_data.get("code_insee", "")[:2] if agent_data.get("code_insee") else ""
        },

        # ── BDNB ──────────────────────────────────────────────────────────────
        "bdnb": {
            "annee_construction"   : profil_bien.get("annee_construction") or user_data.get("annee_construction"),
            "type_bien"            : profil_bien.get("type_bien", "maison"),
            "type_toiture"         : profil_bien.get("type_toiture") or user_data.get("type_toiture"),
            "isolation_toiture"    : profil_bien.get("isolation_toiture", "inconnue"),
            "isolation_murs"       : profil_bien.get("isolation_murs", "inconnue"),
            "presence_sous_sol"    : profil_bien.get("presence_sous_sol", False),
            "presence_cave"        : profil_bien.get("presence_cave", False),
            "installation_electrique_annee": profil_bien.get("installation_electrique_annee"),
            "type_structure"       : user_data.get("type_structure"),
            "etat_structure"       : user_data.get("etat_structure"),
            "etat_toiture"         : user_data.get("etat_toiture"),
            "annee_renovation"     : user_data.get("annee_renovation"),
        },

        # ── Géorisques ────────────────────────────────────────────────────────
        "georisques": {
            "zone_sismique"              : int(rc_seisme.get("zone_code") or (seisme[0].get("zone", 1) if seisme else 1)),
            "zone_sismique_libelle"      : rc_seisme.get("zone_libelle") or (seisme[0].get("libelle", "") if seisme else ""),
            "alea_inondation"            : "fort" if rc_catnat.get("evts_par_type", {}).get("inondation", 0) > 5 else "modere",
            "ppr_inondation"             : rc_catnat.get("evts_par_type", {}).get("inondation", 0) > 0,
            "retrait_gonflement_argile"  : rc_rga.get("exposition", argiles[0].get("exposition", "") if argiles else ""),
            "code_rga"                   : rc_rga.get("code_exposition") or (argiles[0].get("codeExposition", "") if argiles else ""),
            "mouvement_terrain"          : rc_catnat.get("evts_par_type", {}).get("mouvement_terrain", 0) > 0,
            "radon_classe"               : int(rc_radon.get("classe_potentiel") or radon.get("classe_potentiel", 1)),
            "cavites_souterraines"       : rc_cavites.get("present", False),
            "nb_catnat_total"            : rc_catnat.get("total_evts") or catnat.get("total_evts", 0),
            "nb_catnat_10ans"            : rc_catnat.get("nb_evt_10ans", 0),
            "catnat_par_type"            : rc_catnat.get("evts_par_type", {}),
        },

        # ── IGN / Topographie ─────────────────────────────────────────────────
        "ign": {
            "altitude_m"         : rc_topo.get("altitude_m", 0),
            "zone_urbaine"       : True,
            "presence_foret_5km" : False,
        },

        # ── Open-Meteo (proxys déduits de la localisation Nantes) ─────────────
        "open_meteo": {
            "temperature_moy_annuelle_c" : 12.8,
            "temperature_max_record_c"   : 40.5,
            "precipitations_moy_annuelles_mm": 820,
            "jours_canicule_an"          : 8,
            "jours_pluie_intense_an"     : 55,
            "note": "Valeurs proxy pour Nantes (44) — données DRIAS manquantes"
        },

        # ── Scores du risk engine step7 (déjà calculés) ───────────────────────
        "scores_risk_engine": {
            "score_global"         : score_step7.get("global", 0),
            "score_global_raw"     : score_step7.get("global_raw", 0),
            "score_infiltration"   : perils.get("infiltration", {}).get("score", 0),
            "score_thermique"      : perils.get("thermique", {}).get("score", 0),
            "score_incendie_elec"  : perils.get("incendie_electrique", {}).get("score", 0),
            "score_aleas_naturels" : perils.get("aleas_naturels", {}).get("score", 0),
            "weights"              : score_step7.get("weights", {}),
        },

        # ── Règles déclenchées (traçabilité) ──────────────────────────────────
        "regles_declenchees": {
            peril: [
                {"rule_id": r.get("rule_id"), "points": r.get("points"), "justification": r.get("justification")}
                for r in data.get("triggered_rules", [])
            ]
            for peril, data in perils.items()
        },

        # ── DRIAS (manquant — proxy déduit) ───────────────────────────────────
        "drias": {
            "disponible": False,
            "donnees_manquantes": risk_context.get("donnees_manquantes", []),
            "note": "Données DRIAS non disponibles — projections 2050 déduites par Mistral à partir du contexte géographique et climatique de Nantes",
            # Proxys DRIAS pour Nantes d'après les scénarios nationaux
            "horizon_2050": {
                "rcp45": {
                    "delta_temp_ete_c"                : 1.7,
                    "delta_temp_hiver_c"              : 1.2,
                    "delta_precipitations_ete_pct"    : -10,
                    "delta_precipitations_hiver_pct"  : +8,
                    "jours_canicule_supplementaires"  : 10,
                    "jours_secheresse_supplementaires": 15,
                    "risque_inondation_multiplied_par": 1.4
                },
                "rcp85": {
                    "delta_temp_ete_c"                : 3.0,
                    "delta_temp_hiver_c"              : 2.2,
                    "delta_precipitations_ete_pct"    : -20,
                    "delta_precipitations_hiver_pct"  : +15,
                    "jours_canicule_supplementaires"  : 25,
                    "jours_secheresse_supplementaires": 35,
                    "risque_inondation_multiplied_par": 2.1
                }
            },
            "montee_eaux_cm_2050": 30,
            "intensite_evenements_extremes": "augmentation_moderee_a_forte"
        },

        # ── Confiance de l'analyse ────────────────────────────────────────────
        "confidence": step7.get("confidence", {}),
        "version_input": input_json.get("version", "1.0"),
        "generated_at" : input_json.get("generated_at", ""),
    }

    return donnees_risk_engine, formulaire


def _extraire_commune(adresse: str) -> str:
    """Extrait le nom de la commune depuis l'adresse."""
    if not adresse:
        return "Inconnue"
    parties = adresse.split()
    # Cherche un code postal (5 chiffres) et prend le mot suivant
    for i, p in enumerate(parties):
        if p.isdigit() and len(p) == 5 and i + 1 < len(parties):
            return " ".join(parties[i+1:])
    return parties[-1] if parties else "Inconnue"


def charger_json(chemin: str) -> Dict[str, Any]:
    """Charge un fichier JSON depuis le disque."""
    import json
    with open(chemin, "r", encoding="utf-8") as f:
        return json.load(f)
