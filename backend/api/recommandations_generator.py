"""
Générateur de recommandations par zone.
Portage Python de generateDynamicRecommendations() du script.cjs.

Prend les données API + formulaire client et produit
les recommandations structurées par zone (fondations, toiture, etc.)
"""

from __future__ import annotations

from typing import Any


def generate_zone_recommendations(
    api_data: dict[str, Any],
    form_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Génère les recommandations dynamiques par zone.

    Args:
        api_data: Données des API (georisques, climate, building, etc.)
        form_data: Données du formulaire client (optionnel)

    Returns:
        Dict avec zones, projection_2050, synthese_financiere, scores
    """
    georisques = api_data.get("georisques", {})
    climate = api_data.get("climate", api_data.get("open_meteo", {}))
    building = api_data.get("building", api_data.get("bdnb", {}))
    altitude_data = api_data.get("altitude", api_data.get("ign", {}))
    water_dist = api_data.get("waterDist", api_data.get("distance_eau"))
    forest_dist = api_data.get("forestDist", api_data.get("distance_foret"))

    # ─── Signaux de risque ──────────────────────────────────────────────────
    rN = georisques.get("risquesNaturels", {})
    if not rN:
        rN = {
            "inondation": {"present": georisques.get("alea_inondation") == "fort"},
            "retraitGonflementArgile": {"present": bool(georisques.get("retrait_gonflement_argile"))},
            "seisme": {"present": bool(georisques.get("zone_sismique", 0) > 1)},
            "radon": {"present": bool(georisques.get("radon_classe", 0) > 1)},
            "remonteeNappe": {"present": False},
            "mouvementTerrain": {"present": georisques.get("mouvement_terrain", False)},
        }

    inondation = _get(rN, "inondation", {}).get("present", False)
    rga = _get(rN, "retraitGonflementArgile", {}).get("present", False) or bool(georisques.get("argiles_rga"))
    seisme = _get(rN, "seisme", {}).get("present", False)
    radon = _get(rN, "radon", {}).get("present", False)
    remontee_nappe = _get(rN, "remonteeNappe", {}).get("present", False)
    mouvement_terrain = _get(rN, "mouvementTerrain", {}).get("present", False)

    # ─── Signaux climatiques ────────────────────────────────────────────────
    c = climate if isinstance(climate, dict) else {}
    heatwave = (c.get("heatwaveDaysPerYear", 0) or 0) > 10
    heavy_rain = (c.get("annualPrecipitation", 0) or 0) > 800
    strong_wind = (c.get("stormFrequency", 0) or 0) >= 3
    freeze = (c.get("freezeDaysPerYear", 0) or 0) > 20
    soil_moisture = c.get("soilMoisture")
    soil_dry = soil_moisture is not None and soil_moisture < 0.25

    # ─── Signaux du bâti ────────────────────────────────────────────────────
    bdnb = building.get("bdnb", building) if isinstance(building, dict) else {}
    built_year = bdnb.get("annee_construction", form_data.get("annee_construction", 2000)) or 2000
    is_old = built_year < 1980
    is_very_old = built_year < 1950
    has_dpe = bool(bdnb.get("classe_bilan_dpe"))
    dpe_bad = has_dpe and bdnb.get("classe_bilan_dpe") in ("F", "G")

    # ─── Altitude / eau ─────────────────────────────────────────────────────
    alt = altitude_data.get("altitude", 50) if isinstance(altitude_data, dict) else 50
    low_altitude = alt < 20
    near_water = water_dist is not None and water_dist < 200

    # ─── Calcul des scores par zone ──────────────────────────────────────────
    score_sous_sol = _calc_score(
        [(inondation, 35), (remontee_nappe, 20), (radon, 15),
         (near_water, 15), (low_altitude, 10)],
        default=15
    )
    score_fondations = _calc_score(
        [(rga, 40), (seisme, 20), (mouvement_terrain, 15),
         (soil_dry, 10), (is_very_old, 10)],
        default=15
    )
    score_toiture = _calc_score(
        [(heatwave, 30), (dpe_bad, 25), (strong_wind, 15),
         (is_old, 15), (heavy_rain, 10)],
        default=15
    )
    score_murs = _calc_score(
        [(freeze, 20), (dpe_bad, 20), (strong_wind, 15),
         (is_old, 15), (heatwave, 10)],
        default=10
    )

    def _level(s: int) -> str:
        if s >= 70:
            return "critique"
        if s >= 55:
            return "eleve"
        if s >= 35:
            return "modere"
        return "faible"

    def _alea_label(zone: str) -> str:
        if zone == "sous_sol":
            if inondation:
                return "Inondation"
            if remontee_nappe:
                return "Remontée de nappe"
            if radon:
                return "Radon"
            return "Humidité"
        if zone == "fondations":
            if rga:
                return "RGA"
            if seisme:
                return "Séisme"
            if mouvement_terrain:
                return "Mouvement de terrain"
            return "Tassement"
        if zone == "toiture":
            if heatwave:
                return "Thermique (canicule)"
            if strong_wind:
                return "Tempête"
            if heavy_rain:
                return "Pluie"
            return "Usure"
        if zone == "murs_nord":
            if freeze:
                return "Gel/dégel"
            if strong_wind:
                return "Tempête"
            if heatwave:
                return "Thermique"
            return "Vieillissement"
        return "Non classé"

    # ─── Génération des recommandations ──────────────────────────────────────
    recos = {"fondations": [], "murs_nord": [], "toiture": [], "sous_sol": []}

    # SOUS-SOL
    if score_sous_sol >= 30 or inondation or remontee_nappe:
        recos["sous_sol"].append({
            "ref": "DYN_INO_01", "travaux": "Pose de batardeaux amovibles étanches sur baies et portes (protection inondation)",
            "cout_estime": "800€", "gain_resilience": 60, "priorite": 1,
            "norme": "DTU 36.5 / Cahier CSTB 3724", "aide_financiere": "Fonds Barnier (80%)", "reste_a_charge": "160€"
        })
        recos["sous_sol"].append({
            "ref": "DYN_INO_02", "travaux": "Installation d'une station de pompage sous-sol (puisard + pompe vide-cave)",
            "cout_estime": "2100€", "gain_resilience": 65, "priorite": 2,
            "norme": "DTU 60.11 / CCTG 70", "aide_financiere": "Fonds Barnier (80%)", "reste_a_charge": "420€"
        })
    if radon or score_sous_sol >= 25:
        recos["sous_sol"].append({
            "ref": "DYN_RAD_01", "travaux": "Installation VMC Double Flux avec filtration radon et extraction continue",
            "cout_estime": "5250€", "gain_resilience": 70, "priorite": 3 if radon else 6,
            "norme": "DTU 68.3 / Avis Technique CSTB", "aide_financiere": "MaPrimeRénov' (2 500€)", "reste_a_charge": "2750€"
        })
    if score_sous_sol < 20:
        recos["sous_sol"].append({
            "ref": "DYN_HUM_01", "travaux": "Application d'un revêtement d'étanchéité des murs de sous-sol + drain périphérique",
            "cout_estime": "1500€", "gain_resilience": 40, "priorite": 4,
            "norme": "DTU 20.1", "aide_financiere": "", "reste_a_charge": "1500€"
        })

    # FONDATIONS
    if rga or score_fondations >= 30:
        recos["fondations"].append({
            "ref": "DYN_RGA_01", "travaux": "Gestion étanche des eaux pluviales + gouttières éloignées à >2m des fondations",
            "cout_estime": "120€", "gain_resilience": 30, "priorite": 3,
            "norme": "Loi ELAN R.132-3 / DTU 20.1", "aide_financiere": "Anah (50%)", "reste_a_charge": "60€"
        })
        recos["fondations"].append({
            "ref": "DYN_RGA_02", "travaux": "Trottoir périphérique étanche (largeur ≥1,5m) avec géomembrane anti-évaporation",
            "cout_estime": "160€", "gain_resilience": 35, "priorite": 4,
            "norme": "DTU 13.1 / NF P 94-500", "aide_financiere": "Anah (50%)", "reste_a_charge": "80€"
        })
    if seisme or score_fondations >= 40:
        recos["fondations"].append({
            "ref": "DYN_SIS_01", "travaux": "Diagnostic structurel fondations + renforcement par chaînage si nécessaire",
            "cout_estime": "3000€", "gain_resilience": 55, "priorite": 5,
            "norme": "DTU 14.1 / Eurocode 8", "aide_financiere": "Fonds CatNat (jusqu'à 80%)", "reste_a_charge": "600€"
        })
    if score_fondations < 20:
        recos["fondations"].append({
            "ref": "DYN_FON_01", "travaux": "Contrôle visuel des fondations + surveillance des fissures",
            "cout_estime": "300€", "gain_resilience": 20, "priorite": 6,
            "norme": "NF P 94-500", "aide_financiere": "", "reste_a_charge": "300€"
        })

    # TOITURE
    if is_old or heatwave or dpe_bad:
        recos["toiture"].append({
            "ref": "DYN_ISO_01", "travaux": "Isolation des combles perdus (laine de bois, ép. 350mm, R ≥ 7, déphasage >10h)",
            "cout_estime": "2500€", "gain_resilience": 40, "priorite": 7,
            "norme": "DTU 45.1 / RE2020", "aide_financiere": "MaPrimeRénov' (20€/m²)", "reste_a_charge": "1500€"
        })
    if strong_wind or heavy_rain:
        recos["toiture"].append({
            "ref": "DYN_TOI_01", "travaux": "Vérification et renforcement de la couverture (fixations anti-tempête, gouttières renforcées)",
            "cout_estime": "1200€", "gain_resilience": 45, "priorite": 5,
            "norme": "DTU 40.21 / NF EN 1991-1-4", "aide_financiere": "", "reste_a_charge": "1200€"
        })
    if heatwave and score_toiture >= 30:
        recos["toiture"].append({
            "ref": "DYN_CLI_01", "travaux": "Pompe à chaleur Air-Eau (COP ≥4,2, 14kW, mode rafraîchissant)",
            "cout_estime": "13000€", "gain_resilience": 50, "priorite": 9,
            "norme": "DTU 65.16 / RE2020", "aide_financiere": "MaPrimeRénov' (5 000€)", "reste_a_charge": "8000€"
        })
    if score_toiture < 20:
        recos["toiture"].append({
            "ref": "DYN_ENT_01", "travaux": "Entretien préventif toiture (nettoyage, inspection annuelle)",
            "cout_estime": "200€/an", "gain_resilience": 15, "priorite": 8,
            "norme": "NF P 08-301", "aide_financiere": "", "reste_a_charge": "200€/an"
        })

    # MURS
    if is_old or freeze or dpe_bad:
        recos["murs_nord"].append({
            "ref": "DYN_ITE_01", "travaux": "Isolation des murs par l'extérieur (ITE) sous ATEC CSTB",
            "cout_estime": "17000€", "gain_resilience": 45, "priorite": 8,
            "norme": "CPT 3035 / Cahier CSTB 3035", "aide_financiere": "MaPrimeRénov' (75€/m²)", "reste_a_charge": "9500€"
        })
    if strong_wind or score_murs >= 20:
        recos["murs_nord"].append({
            "ref": "DYN_MUR_01", "travaux": "Traitement des ponts thermiques + bardage protecteur façade nord",
            "cout_estime": "3500€", "gain_resilience": 35, "priorite": 7,
            "norme": "DTU 23.1", "aide_financiere": "", "reste_a_charge": "3500€"
        })
    if score_murs < 15:
        recos["murs_nord"].append({
            "ref": "DYN_PEI_01", "travaux": "Peinture isolante et hydrofuge sur façades exposées",
            "cout_estime": "800€", "gain_resilience": 15, "priorite": 9,
            "norme": "", "aide_financiere": "", "reste_a_charge": "800€"
        })

    # ─── Construction des zones ──────────────────────────────────────────────
    zones = {}
    for zone_name, zone_score in [
        ("fondations", score_fondations),
        ("murs_nord", score_murs),
        ("toiture", score_toiture),
        ("sous_sol", score_sous_sol),
    ]:
        zones[zone_name] = {
            "risque": zone_score,
            "niveau": _level(zone_score),
            "alea_principal": _alea_label(zone_name),
            "justification": _generate_justification(zone_name, zone_score, api_data, form_data),
            "recommandations": recos[zone_name],
            "test_vulnerabilite": {
                "verdict": _generate_verdict(zone_score),
                "explication": _generate_explication(zone_name, zone_score, api_data),
            }
        }

    # ─── Scores par aléa ─────────────────────────────────────────────────────
    scores_par_alea = {
        "inondation": score_sous_sol,
        "rga": score_fondations,
        "canicule": score_toiture,
        "tempete": round((score_toiture + score_murs) / 2),
    }

    # ─── Score global ────────────────────────────────────────────────────────
    global_score = round(score_sous_sol * 0.3 + score_fondations * 0.25 + score_toiture * 0.25 + score_murs * 0.2)

    # ─── Projection 2050 ─────────────────────────────────────────────────────
    projection = _build_projection(zones, global_score)

    # ─── Synthèse financière ─────────────────────────────────────────────────
    total_cost = 0
    for r_list in recos.values():
        for r in r_list:
            m = r["cout_estime"].replace(" ", "").replace("€/an", "").replace("€", "")
            try:
                total_cost += int(m)
            except ValueError:
                pass
    total_aide = round(total_cost * 0.35)
    reste = total_cost - total_aide

    synthese_fin = {
        "cout_brut_total": f"{total_cost}€",
        "aides_mobilisables": f"{total_aide}€",
        "reste_a_charge_net": f"{reste}€",
    }

    return {
        "zones": zones,
        "projection_2050": projection,
        "synthese_financiere": synthese_fin,
        "scores_par_alea": scores_par_alea,
        "score_global": global_score,
        "nb_recommandations": sum(len(v) for v in recos.values()),
    }


def _get(d: dict, key: str, default=None):
    """Safe dict access."""
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _calc_score(conditions: list[tuple[bool, int]], default: int = 0) -> int:
    """Calcule un score à partir de conditions booléennes."""
    score = sum(points for cond, points in conditions if cond)
    return min(100, max(0, score)) if score > 0 else default


def _generate_justification(
    zone: str, score: int, api_data: dict, form_data: dict | None = None
) -> str:
    """Génère une justification textuelle pour le score d'une zone."""
    if not isinstance(api_data, dict):
        return f"Score {score}/100 basé sur les données disponibles."

    rN = api_data.get("georisques", {}).get("risquesNaturels", {})
    climate = api_data.get("climate", api_data.get("open_meteo", {}))
    building = api_data.get("building", api_data.get("bdnb", {}))
    parts = []

    if zone == "sous_sol":
        if _get(rN, "inondation", {}).get("present"):
            parts.append("Risque inondation présent au droit de l'adresse")
        if _get(rN, "remonteeNappe", {}).get("present"):
            parts.append("Remontée de nappe identifiée")
        if _get(rN, "radon", {}).get("present"):
            parts.append(f"Potentiel radon présent")
        wd = api_data.get("waterDist", api_data.get("distance_eau"))
        if wd is not None and wd < 200:
            parts.append(f"Proximité d'un cours d'eau ({wd}m)")
        if not parts:
            parts.append("Exposition modérée aux risques hydriques")
    elif zone == "fondations":
        if _get(rN, "retraitGonflementArgile", {}).get("present"):
            parts.append("Présence d'aléa retrait-gonflement des argiles")
        if _get(rN, "seisme", {}).get("present"):
            parts.append("Zone sismique active")
        if isinstance(building, dict) and building.get("annee_construction", 2000) < 1950:
            parts.append("Bâti ancien (antérieur à 1950)")
        if not parts:
            parts.append("Risque structurel faible à moyen")
    elif zone == "toiture":
        c = climate if isinstance(climate, dict) else {}
        if (c.get("heatwaveDaysPerYear", 0) or 0) > 10:
            parts.append(f"{c['heatwaveDaysPerYear']} jours de canicule par an")
        if (c.get("stormFrequency", 0) or 0) >= 3:
            parts.append("Zone venteuse (fréquence de tempêtes modérée)")
        if isinstance(building, dict) and building.get("annee_construction", 2000) < 1980:
            parts.append("Bâti antérieur aux premières réglementations thermiques")
        if not parts:
            parts.append("Exposition thermique standard")
    elif zone == "murs_nord":
        c = climate if isinstance(climate, dict) else {}
        if (c.get("freezeDaysPerYear", 0) or 0) > 20:
            parts.append(f"{c['freezeDaysPerYear']} jours de gel par an")
        if (c.get("stormFrequency", 0) or 0) >= 3:
            parts.append("Exposition au vent dominants")
        if isinstance(building, dict) and building.get("mat_mur_txt"):
            parts.append(f"Mur en {building['mat_mur_txt']}")
        if not parts:
            parts.append("Vulnérabilité faible des murs extérieurs")

    return ". ".join(parts) + "." if parts else f"Score {score}/100 — données insuffisantes."


def _generate_verdict(score: int) -> str:
    if score >= 70:
        return "Vulnérabilité critique — des travaux urgents sont nécessaires"
    if score >= 55:
        return "Vulnérabilité élevée — des travaux de mitigation sont recommandés dans les 12 mois"
    if score >= 35:
        return "Vulnérabilité modérée — des travaux de mitigation sont recommandés dans les 24 mois"
    return "Vulnérabilité faible — aucune action urgente requise, suivi périodique conseillé"


def _generate_explication(zone: str, score: int, api_data: dict) -> str:
    rN = api_data.get("georisques", {}).get("risquesNaturels", {})
    climate = api_data.get("climate", api_data.get("open_meteo", {}))
    c = climate if isinstance(climate, dict) else {}

    if zone == "sous_sol":
        causes = []
        if _get(rN, "inondation", {}).get("present"):
            causes.append("l'inondation")
        if _get(rN, "remonteeNappe", {}).get("present"):
            causes.append("la remontée de nappe")
        if _get(rN, "radon", {}).get("present"):
            causes.append("le radon")
        liés = f"liés à {', '.join(causes)}" if causes else "liés à l'humidité"
        conseil = "Des travaux d'étanchéité et de protection sont conseillés." if score >= 35 else "La situation actuelle est acceptable."
        return f"Le score {score}/100 est {liés}. {conseil}"
    elif zone == "fondations":
        causes = []
        if _get(rN, "retraitGonflementArgile", {}).get("present"):
            causes.append("l'exposition au retrait-gonflement des argiles")
        if _get(rN, "seisme", {}).get("present"):
            causes.append("le risque sismique")
        if c.get("soilMoisture") is not None and c["soilMoisture"] < 0.25:
            causes.append("la sécheresse des sols")
        conseil = "Une étude géotechnique et des travaux de drainage sont recommandés." if score >= 35 else "Les fondations ne présentent pas de signe de fragilité majeur."
        default_cause = "l'etat general des fondations"
        causes_str = ', '.join(causes) if causes else default_cause
        return f"Le score {score}/100 tient compte de {causes_str}. {conseil}"
    elif zone == "toiture":
        toiture_conseil = "L'isolation et la resistance aux intemperies sont a ameliorer." if score >= 35 else "La toiture est en etat correct."
        return f"Le score {score}/100 est base sur les donnees climatiques ({c.get('heatwaveDaysPerYear', '?')} jours canicule, {c.get('annualPrecipitation', '?')}mm pluie/an) et les caracteristiques du bati. {toiture_conseil}"
    elif zone == "murs_nord":
        murs_conseil = "Un renforcement de l'isolation exterieure est conseille." if score >= 35 else "Les murs sont en etat satisfaisant."
        return f"Le score {score}/100 integre les contraintes climatiques ({c.get('freezeDaysPerYear', '?')} jours gel, vents dominants) et l'etat du bati. {murs_conseil}"
    return ""


def _build_projection(zones: dict, global_score: int) -> dict:
    """Construit la projection 2050 à partir des zones actuelles."""
    pz = {}
    for name, zn in zones.items():
        p = min(100, round(zn["risque"] * 1.3))
        pz[name] = {
            "risque_projete": p,
            "evolution": f"+{p - zn['risque']} points (aggravation climatique)",
        }
    return {
        "score_global": min(100, round(global_score * 1.4)),
        "scenario_climatique": "CMIP6 EC_Earth3P_HR (≈RCP8.5) + DRIAS ADAMONT +4°C France",
        "zones": pz,
    }
