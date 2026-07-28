"""
Pont vers les agents Typhoon2-Alpha.
Collecte les donnees reelles, calcule les scores de risque par zone
a partir des donnees Georisques, climat Open-Meteo, altitude IGN, BDNB.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TYPHOON_BACKEND = os.path.join(HERE, "..", "Typhoon2-Alpha", "backend")

_collect = None
_collector_available = False

RISK_DESCRIPTIONS = {
    "fondations": {
        "rga": "Retrait-gonflement des argiles : le sol argileux se dilate avec l'humidite et se retire en secheresse, provoquant des fissures.",
        "cavites": "Cavites souterraines : risque d'effondrement du sol sous les fondations.",
        "mvt": "Mouvement de terrain : glissement ou affaissement du sol pouvant destabiliser les fondations.",
    },
    "sous_sol": {
        "inondation": "Inondation / remontee de nappe : infiltration d'eau dans le sous-sol et les parties basses.",
        "catnat": "Sinistres climatiques recurrents : historique d'inondations ou de coulees de boue sur la commune.",
        "radon": "Radon : gaz radioactif naturel pouvant s'accumuler dans les sous-sols et caves.",
    },
    "toiture": {
        "canicule": "Stress thermique : les episodes de canicule accelèrent le vieillissement des materiaux de couverture.",
        "tempete": "Rafales de vent : risque d'arrachement des tuiles et de degradation de la charpente.",
        "precipitation": "Pluies intenses : infiltration par les points de fragilite de la toiture.",
    },
    "murs_nord": {
        "humidite": "Humidite residuelle : la facade nord, moins exposee au soleil, seche moins vite et developpe des moisissures.",
        "infiltration": "Infiltrations laterales : les murs exposes aux intemperies du nord subissent une degradation plus rapide.",
    },
    "murs_sud": {
        "stress_thermique": "Stress thermique : la facade sud subit les ecarts de temperature les plus importants (dilatation/contraction).",
        "uv": "Rayonnement UV : degradation des revetements de facade et des joints par l'exposition solaire directe.",
    },
    "murs_est": {
        "vent": "Vents dominants : la facade est est exposee aux vents dominants, provoquant une usure prematuree des joints.",
        "pluie_battante": "Pluie battante : lessivage des facades par les precipitations accompagnees de vent.",
    },
    "murs_ouest": {
        "intemperies": "Intemperies : la facade ouest est generalement la plus exposee aux pluies et aux tempêtes.",
        "humidite_persistante": "Humidite persistante : infiltration capillaire et developpement de salpetre.",
    },
}


def _init_typhoon():
    global _collect, _collector_available
    if _collect is not None:
        return _collector_available
    try:
        if os.path.isdir(TYPHOON_BACKEND):
            sys.path.insert(0, TYPHOON_BACKEND)
        from app.agents.collector_agent import collect
        _collect = collect
        _collector_available = True
        return True
    except Exception:
        _collector_available = False
        return False


def _safe_get(obj, *keys, default=None):
    """Accede recursivement a une cle dans un dict sans lever d'exception."""
    for k in keys:
        try:
            obj = obj[k]
        except (KeyError, IndexError, TypeError):
            return default
    return obj if obj is not None else default


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _niveau(score):
    if score < 20:
        return "tres_faible"
    if score < 40:
        return "faible"
    if score < 60:
        return "modere"
    if score < 80:
        return "eleve"
    return "critique"


def _extract_rga(georisques):
    """Extrait le niveau d'exposition RGA (retrait-gonflement argiles)."""
    risques = _safe_get(georisques, "risques_commune")
    if isinstance(risques, dict):
        risques = risques.get("data", risques)
    if isinstance(risques, list):
        for r in risques:
            if isinstance(r, dict):
                lib = str(r.get("libelle", "")).lower()
                if "retrait" in lib or "argile" in lib:
                    alea = str(r.get("alea", r.get("code_alea", "2")))
                    return {"1": 1, "2": 2, "3": 3}.get(alea, 2)
    return 2


def _count_catnat(georisques):
    """Compte le nombre d'arrêtés CatNat."""
    catnat = _safe_get(georisques, "catnat")
    if isinstance(catnat, dict):
        catnat = catnat.get("data", [])
    if isinstance(catnat, list):
        return len(catnat)
    return 0


def _safe_int_list(val):
    if isinstance(val, list):
        return [v for v in val if isinstance(v, (int, float))]
    return []


def _has_risk(georisques, keyword):
    """Verifie si un risque est present dans la liste des risques de la commune."""
    risques = _safe_get(georisques, "risques_commune")
    if isinstance(risques, dict):
        risques = risques.get("data", risques)
    if isinstance(risques, list):
        for r in risques:
            if isinstance(r, dict) and keyword in str(r.get("libelle", "")).lower():
                return True
    return False


def _compute_risk_scores(building_data):
    """Calcule les scores de risque par zone a partir des donnees collectees."""
    geo = building_data.get("georisques") or {}
    climat = building_data.get("climat_open_meteo") or {}
    altitude = building_data.get("altitude_m") or 100
    bdnb = building_data.get("bdnb") or {}

    # --- Données préparatoires ---
    rga_level = _extract_rga(geo)
    nb_catnat = _count_catnat(geo)
    has_cavites = _has_risk(geo, "cavite")
    has_mvt = _has_risk(geo, "mouvement")
    has_inondation = _has_risk(geo, "inondation")

    # Zone sismique
    sismique = _safe_get(geo, "zonage_sismique")
    zone_sismique = 1
    if isinstance(sismique, dict):
        zs = sismique.get("zone_sismique") or _safe_get(sismique, "data", "zone_sismique")
        zone_sismique = int(zs) if zs and str(zs).isdigit() else 1

    # Climat
    ref = climat.get("reference_2015_2024") or {}
    proj = climat.get("projection_2041_2050") or {}
    temp_max_ref = _safe_get(ref, "temperature_max_moyenne_c") or 25
    temp_max_2050 = _safe_get(proj, "temperature_max_moyenne_c") or 28
    precip_ref = _safe_get(ref, "precipitation_annuelle_moyenne_mm") or 600
    jours_chaleur_ref = _safe_get(ref, "jours_chaleur_extreme_par_an") or 5
    jours_chaleur_2050 = _safe_get(proj, "jours_chaleur_extreme_par_an") or 15

    # BDNB
    batiment = _safe_get(bdnb, "batiment") or {}
    annee_construction = batiment.get("annee_construction") or batiment.get("annee_construction")
    if not annee_construction:
        annee_construction = 1980
    age_batiment = 2026 - annee_construction

    # Facteur vétusté basé sur l'année de construction (toutes zones)
    if annee_construction < 1946:
        vetuste = 20    # avant-guerre : fondations sommaires, murs en pierre/pisé
    elif annee_construction < 1970:
        vetuste = 14    # reconstruction : qualité variable
    elif annee_construction < 1990:
        vetuste = 8     # normes modérées
    elif annee_construction < 2005:
        vetuste = 4     # réglementation thermique
    else:
        vetuste = 0     # récent

    # Type de construction estimé (BDNB si disponible)
    type_construction = _safe_get(batiment, "type_construction", "") or ""
    a_etage = 1 if _safe_get(batiment, "nb_etages", default=1) > 1 else 0

    # --- Score FONDATIONS ---
    s_fond_rga = rga_level * 25
    s_fond_cavites = 20 if has_cavites else 0
    s_fond_mvt = 15 if has_mvt else 0
    s_fond_alt = 10 if altitude < 50 else (15 if altitude > 800 else 0)
    s_fond_age = vetuste  # fondations anciennes = moins resistantes
    score_fond = _clamp(s_fond_rga + s_fond_cavites + s_fond_mvt + s_fond_alt + s_fond_age, 3, 95)

    # --- Score SOUS-SOL ---
    if nb_catnat >= 15:
        s_ss_catnat = 50
    elif nb_catnat >= 8:
        s_ss_catnat = 40
    elif nb_catnat >= 4:
        s_ss_catnat = 30
    elif nb_catnat >= 2:
        s_ss_catnat = 20
    elif nb_catnat >= 1:
        s_ss_catnat = 10
    else:
        s_ss_catnat = 0
    s_ss_inond = 25 if has_inondation else 0
    s_ss_precip = 15 if precip_ref > 900 else (8 if precip_ref > 700 else 0)
    s_ss_age = _clamp(vetuste + 5 if a_etage else vetuste, 0, 25)  # etage = cave/sous-sol souvent present
    score_ss = _clamp(s_ss_catnat + s_ss_inond + s_ss_precip + s_ss_age, 3, 95)

    # --- Score TOITURE ---
    if temp_max_2050 > 40:
        s_toit_temp = 40
    elif temp_max_2050 > 36:
        s_toit_temp = 30
    elif temp_max_2050 > 32:
        s_toit_temp = 20
    else:
        s_toit_temp = 10
    if jours_chaleur_2050 > 30:
        s_toit_canicule = 25
    elif jours_chaleur_2050 > 15:
        s_toit_canicule = 15
    else:
        s_toit_canicule = 5
    s_toit_age = _clamp(age_batiment // 10, 0, 25)  # charpente + couverture vieillissent
    s_toit_precip = 10 if precip_ref > 800 else 5
    score_toit = _clamp(s_toit_temp + s_toit_canicule + s_toit_age + s_toit_precip, 3, 95)

    # --- Scores MURS ---
    s_murs_base = (zone_sismique - 1) * 12

    s_mn = s_murs_base + _clamp(int(precip_ref / 50), 0, 20)
    s_mn += int(vetuste * 0.7)                  # mur nord ancien = humidite
    if altitude < 100:
        s_mn += 8
    score_mn = _clamp(s_mn, 3, 90)

    dt = temp_max_2050 - temp_max_ref
    s_ms = s_murs_base + _clamp(int(dt * 5), 5, 25)
    s_ms += _clamp(int((temp_max_2050 - 15) * 1.5), 0, 20)
    s_ms += int(vetuste * 0.5)                  # mur sud ancien = defauts d'etancheite
    score_ms = _clamp(s_ms, 3, 90)

    s_me = s_murs_base + _clamp(int(altitude / 30), 0, 12)
    s_me += _clamp(int(precip_ref / 80), 0, 12)
    s_me += int(vetuste * 0.4)                  # mur est ancien = infiltration
    score_me = _clamp(s_me, 3, 85)

    s_mo = s_murs_base + _clamp(int(precip_ref / 60), 0, 20)
    s_mo += 10 if nb_catnat > 5 else 0
    s_mo += int(vetuste * 0.8)                  # mur ouest ancien = le plus expose
    score_mo = _clamp(s_mo, 3, 90)

    zones = {
        "fondations": {"risque": score_fond, "niveau": _niveau(score_fond)},
        "murs_nord": {"risque": score_mn, "niveau": _niveau(score_mn)},
        "murs_sud": {"risque": score_ms, "niveau": _niveau(score_ms)},
        "murs_est": {"risque": score_me, "niveau": _niveau(score_me)},
        "murs_ouest": {"risque": score_mo, "niveau": _niveau(score_mo)},
        "toiture": {"risque": score_toit, "niveau": _niveau(score_toit)},
        "sous_sol": {"risque": score_ss, "niveau": _niveau(score_ss)},
    }

    # Projection 2050 (aggravation climatique)
    facteur_climat = _clamp(temp_max_2050 / temp_max_ref, 1.0, 1.5)
    zones_2050 = {}
    for name, z in zones.items():
        aggrav = 1.15
        if name in ("toiture", "sous_sol", "fondations"):
            aggrav = _clamp(facteur_climat, 1.05, 1.4)
        elif name.startswith("murs_"):
            aggrav = _clamp(facteur_climat * 0.9, 1.0, 1.3)
        score_2050 = _clamp(round(z["risque"] * aggrav), 5, 99)
        zones_2050[name] = {"risque": score_2050, "niveau": _niveau(score_2050)}

    score_global = round(sum(z["risque"] for z in zones.values()) / len(zones))
    score_global_2050 = round(sum(z["risque"] for z in zones_2050.values()) / len(zones_2050))

    # --- Risques présents (pour le rapport) ---
    risques_presents = []
    if has_inondation:
        risques_presents.append("Inondation / remontee de nappe")
    if rga_level >= 2:
        risques_presents.append("Retrait-gonflement des argiles (RGA)")
    if has_cavites:
        risques_presents.append("Cavites souterraines")
    if has_mvt:
        risques_presents.append("Mouvement de terrain")
    if zone_sismique >= 3:
        risques_presents.append(f"Zone sismique (niveau {zone_sismique})")
    if nb_catnat >= 3:
        risques_presents.append(f"{nb_catnat} arretes CatNat sur la commune")
    if jours_chaleur_2050 > 20:
        risques_presents.append("Canicules extremes (>{0}j/an a 2050)".format(jours_chaleur_2050))
    if precip_ref > 800:
        risques_presents.append("Precipitations abondantes")
    if not risques_presents:
        risques_presents.append("Aucun risque majeur identifie")

    return {
        "score_global": score_global,
        "zones": zones,
        "zones_2050": zones_2050,
        "projection_2050": {"score_global": score_global_2050, "zones": zones_2050},
        "risques_presents": risques_presents,
        "details_climat": {
            "temperature_max_actuelle": temp_max_ref,
            "temperature_max_2050": temp_max_2050,
            "precipitations_annuelles_mm": precip_ref,
            "jours_chaleur_extreme_par_an": jours_chaleur_ref,
            "jours_chaleur_extreme_2050": jours_chaleur_2050,
            "altitude_m": altitude,
            "zone_sismique": zone_sismique,
            "nb_catnat": nb_catnat,
            "rga_exposition": rga_level,
        },
        "altitude_m": altitude,
        "nb_catnat": nb_catnat,
        "zone_sismique": zone_sismique,
        "rga_exposition": rga_level,
    }


def _compute_recommendations(risk_scores, building_data):
    """Genere des recommandations basees sur les scores de risque reels."""
    recos = {}
    zones = risk_scores["zones"]

    if zones["fondations"]["risque"] >= 35:
        recos["rga"] = {
            "priorite": 1 if zones["fondations"]["risque"] >= 60 else 2,
            "titre": "Renforcement des fondations",
            "description": "Traitement des sols argileux par injection de resine expansive et reprise en sous-oeuvre.",
            "cout_estime_bas": 8000,
            "cout_estime_haut": 25000,
            "gain_resilience_pct": _clamp(25 + zones["fondations"]["risque"] * 0.5, 20, 75),
            "aleas_adresses": ["rga"],
        }

    if zones["sous_sol"]["risque"] >= 35:
        recos["inondation"] = {
            "priorite": 1 if zones["sous_sol"]["risque"] >= 60 else 2,
            "titre": "Protection contre les inondations",
            "description": "Installation drainage peripherique, pompe de relevage et batardeaux.",
            "cout_estime_bas": 5000,
            "cout_estime_haut": 15000,
            "gain_resilience_pct": _clamp(20 + zones["sous_sol"]["risque"] * 0.5, 15, 70),
            "aleas_adresses": ["inondation"],
        }

    if zones["toiture"]["risque"] >= 40:
        recos["tempete"] = {
            "priorite": 1 if zones["toiture"]["risque"] >= 65 else 2,
            "titre": "Renforcement de la toiture",
            "description": "Fixations anti-arrachement, renforcement charpente et isolation thermique renforcee.",
            "cout_estime_bas": 6000,
            "cout_estime_haut": 18000,
            "gain_resilience_pct": _clamp(15 + zones["toiture"]["risque"] * 0.5, 15, 65),
            "aleas_adresses": ["tempete"],
        }

    if zones["murs_ouest"]["risque"] >= 45:
        recos["incendie"] = {
            "priorite": 2,
            "titre": "Isolation et protection des facades",
            "description": "Traitement hydrofuge des facades, isolation exterieure et volets protecteurs.",
            "cout_estime_bas": 4000,
            "cout_estime_haut": 12000,
            "gain_resilience_pct": _clamp(15 + zones["murs_ouest"]["risque"] * 0.4, 15, 55),
            "aleas_adresses": ["incendie"],
        }

    return recos


def _apply_house_features(zones, features):
    """Ajuste les scores de risque selon les caracteristiques reelles du bien."""
    if not features:
        return zones

    adj = {k: 0 for k in zones}

    # DPE → toiture + murs + sous-sol
    dpe_map = {"a": 0, "b": 2, "c": 5, "d": 10, "e": 18, "f": 26, "g": 35}
    dpe = dpe_map.get((features.get("dpe") or "d").strip().lower(), 10)
    adj["toiture"] += int(dpe * 0.4)
    for m in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        adj[m] += int(dpe * 0.3)
    adj["sous_sol"] += int(dpe * 0.3)

    # Chauffage type → toiture
    ch_map = {"electrique": 3, "gaz": 8, "fioul": 16, "bois": 12, "pac": 4, "reseau": 5}
    ch = ch_map.get(features.get("chauffage_type", "").lower(), 0)
    # Chauffage âge
    ca_map = {"recent": 0, "moyen": 8, "vieux": 18}
    ca = ca_map.get(features.get("chauffage_age", "").lower(), 5)
    adj["toiture"] += ch + ca

    # Électricité → murs (risque incendie)
    elec_map = {"recent": 0, "bon": 4, "moyen": 12, "vetuste": 22, "dangereux": 32}
    elec = elec_map.get(features.get("electricite", "").lower(), 4)
    for m in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        adj[m] += int(elec * 0.5)
    adj["toiture"] += int(elec * 0.3)

    # Plomberie → sous-sol + murs
    plom_map = {"recent": 0, "bon": 3, "moyen": 10, "vetuste": 18}
    plom = plom_map.get(features.get("plomberie", "").lower(), 3)
    adj["sous_sol"] += plom
    for m in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        adj[m] += int(plom * 0.3)

    # Menuiseries → murs
    menu_map = {"double_vitrage_recent": 0, "double_vitrage": 4, "simple_bois": 14, "simple_metal": 18}
    menu = menu_map.get(features.get("menuiseries", "").lower(), 4)
    for m in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        adj[m] += menu

    # Isolation combles → toiture
    iso_map = {"excellente": -5, "bonne": 0, "moyenne": 10, "insuffisante": 20, "absente": 28}
    iso_c = iso_map.get(features.get("isolation_combles", "").lower(), 0)
    adj["toiture"] += iso_c

    # Isolation murs → murs
    iso_m = iso_map.get(features.get("isolation_murs", "").lower(), 0)
    for m in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        adj[m] += iso_m

    # Amiante → fondations + toiture
    am_map = {"non": 0, "non_recherche": 6, "present": 28}
    am = am_map.get(features.get("amiante", "").lower(), 6)
    adj["fondations"] += int(am * 0.6)
    adj["toiture"] += int(am * 0.4)

    # Plomb → fondations + sous-sol
    plomb_map = {"non": 0, "non_recherche": 5, "present": 18}
    plomb = plomb_map.get(features.get("plomb", "").lower(), 5)
    adj["fondations"] += int(plomb * 0.6)
    adj["sous_sol"] += int(plomb * 0.4)

    # Termites → fondations + murs
    term_map = {"non": 0, "non_recherche": 4, "present": 24}
    term = term_map.get(features.get("termites", "").lower(), 4)
    adj["fondations"] += int(term * 0.5)
    for m in ("murs_nord", "murs_sud", "murs_est", "murs_ouest"):
        adj[m] += int(term * 0.5)

    # Assainissement → sous-sol
    ass_map = {"collecte": 0, "autonome_conforme": 4, "autonome_non_conforme": 20}
    ass = ass_map.get(features.get("assainissement", "").lower(), 0)
    adj["sous_sol"] += ass

    # Copropriete → surcout
    cop_map = {"faibles": 0, "normales": 2, "elevees": 8, "tres_elevees": 15}
    cop = cop_map.get(features.get("copropriete", "").lower(), 2)
    # reparti sur fondations + toiture (risque de sous-financement)
    adj["fondations"] += int(cop * 0.5)
    adj["toiture"] += int(cop * 0.5)

    zones_aj = {}
    for k, z in zones.items():
        s = _clamp(z["risque"] + adj.get(k, 0), 1, 99)
        zones_aj[k] = {"risque": s, "niveau": _niveau(s)}
    return zones_aj


def _estimate_property_value(building_data):
    """Estime la valeur du bien a partir des donnees disponibles."""
    dvf = building_data.get("dvf_local")
    if dvf and isinstance(dvf, dict):
        try:
            p = dvf.get("prix_m2_median") or dvf.get("median_price_m2")
            s = dvf.get("surface_m2") or 100
            if p and s:
                return round(p * s)
        except Exception:
            pass
    adresse = building_data.get("adresse", {})
    cp = adresse.get("postcode", "")
    # Approximation regionale par code postal
    prefix = cp[:2] if len(cp) >= 2 else ""
    table = {
        "75": 450000, "92": 450000, "78": 420000, "91": 380000,
        "06": 330000, "13": 320000, "83": 290000,
        "69": 350000, "38": 290000,
        "31": 280000, "33": 260000,
        "59": 220000, "62": 200000,
        "67": 270000, "68": 260000,
        "44": 280000, "35": 270000,
    }
    return table.get(prefix, 250000)


async def collect_from_address(address, montant_emprunte=300000, duree_annees=20, taux_annuel=3.4, house_features=None):
    """Collecte les donnees reelles et calcule les scores de risque personnalises."""
    building_data = None
    collector_ok = False
    erreur = None

    if _init_typhoon():
        try:
            building_data = await _collect(address)
            collector_ok = True
        except Exception as e:
            erreur = str(e)

    if building_data:
        risque = _compute_risk_scores(building_data)
        if house_features:
            risque["zones"] = _apply_house_features(risque["zones"], house_features)
            risque["zones_2050"] = _apply_house_features(risque["zones_2050"], house_features)
            risque["projection_2050"]["zones"] = risque["zones_2050"]
            risque["projection_2050"]["score_global"] = round(
                sum(z["risque"] for z in risque["zones_2050"].values()) / len(risque["zones_2050"])
            )
        recommandations = _compute_recommendations(risque, building_data)
        valeur = _estimate_property_value(building_data)
    else:
        risque = {
            "score_global": 65,
            "zones": {
                "fondations": {"risque": 78, "niveau": "eleve"},
                "murs_nord": {"risque": 35, "niveau": "modere"},
                "murs_sud": {"risque": 20, "niveau": "faible"},
                "murs_est": {"risque": 28, "niveau": "faible"},
                "murs_ouest": {"risque": 42, "niveau": "modere"},
                "toiture": {"risque": 55, "niveau": "modere"},
                "sous_sol": {"risque": 65, "niveau": "eleve"},
            },
            "projection_2050": {"score_global": 81, "zones": {}},
            "risques_presents": ["Retrait-gonflement des argiles", "Inondation"],
            "details_climat": {},
        }
        recommandations = {
            "rga": {"priorite": 1, "titre": "Renforcement des fondations", "description": "Traitement des sols argileux.", "cout_estime_bas": 8000, "cout_estime_haut": 25000, "gain_resilience_pct": 70, "aleas_adresses": ["rga"]},
            "inondation": {"priorite": 1, "titre": "Drainage peripherique", "description": "Installation drainage.", "cout_estime_bas": 5000, "cout_estime_haut": 15000, "gain_resilience_pct": 65, "aleas_adresses": ["inondation"]},
        }
        valeur = 330000

    dossier = {
        "valeur_marche_bien": valeur,
        "montant_emprunte": montant_emprunte,
        "duree_annees": duree_annees,
        "taux_annuel_propose": taux_annuel / 100 if taux_annuel > 1 else taux_annuel,
        "tendance_marche_annuelle": 0.01,
    }

    return {
        "collector_ok": collector_ok,
        "building_data": building_data,
        "erreur": erreur,
        "risque": risque,
        "recommandations": recommandations,
        "dossier": dossier,
    }
