"""
Normalisation du JSON du collector vers le contrat canonique.

Regles structurantes appliquees ici :
  - un `null` brut est toujours traduit vers un Status explicite ;
  - une erreur d'API produit SOURCE_ERROR, jamais NO_FEATURE_FOUND ;
  - `results: 0` produit NO_FEATURE_FOUND, jamais "risque nul" ;
  - les donnees BDNB decrivent un GROUPE de batiments -> scope building_group ;
  - les champs nominatifs (proprietaires, SIREN) sont supprimes, jamais normalises.
"""
from __future__ import annotations

from typing import Any, Optional

from .canonical import (
    CanonicalVariable,
    Domain,
    Scope,
    Status,
    TimeHorizon,
    VariableBag,
    ANSWER_BASIS_RANK,
)

#: Champs BDNB nominatifs / administratifs : jamais introduits dans le schema.
PII_FIELDS = frozenset(
    {
        "l_denomination_proprietaire",
        "l_siren",
        "numero_immat_principal",
        "identifiant_dpe",
    }
)

#: Valeurs BDNB qui signifient "renseigne mais indetermine".
BDNB_UNKNOWN_TOKENS = frozenset({"INDETERMINE", "INDÉTERMINÉ", "NON RENSEIGNE", ""})


def normalize(collector: dict, answers: Optional[dict] = None) -> tuple[VariableBag, dict]:
    """Renvoie (bag de variables canoniques, metadonnees de contexte)."""
    bag = VariableBag()
    meta: dict[str, Any] = {"source_status": {}, "warnings": []}

    errors_by_source = {
        e.get("source"): e.get("erreur") for e in (collector.get("erreurs") or [])
    }
    meta["source_errors"] = errors_by_source

    _normalize_address(collector, bag, meta)
    _normalize_geography(collector, bag, meta)
    _normalize_bdnb(collector, bag, meta)
    _normalize_georisques(collector, bag, meta)
    _normalize_climate(collector, bag, meta, errors_by_source)
    _normalize_answers(answers or {}, bag, meta)

    return bag, meta


# --- Adresse et correspondance d'entite -----------------------------------------


def _normalize_address(collector: dict, bag: VariableBag, meta: dict) -> None:
    adr = collector.get("adresse") or {}
    meta["address"] = {
        "label": adr.get("label"),
        "citycode": adr.get("citycode"),
        "lat": adr.get("lat"),
        "lon": adr.get("lon"),
        "score_geocodage": adr.get("score_geocodage"),
    }
    score = adr.get("score_geocodage")
    bag.add(
        CanonicalVariable(
            key="meta.geocoding.score",
            value=float(score) if score is not None else None,
            unit="ratio",
            status=Status.AVAILABLE if score is not None else Status.NOT_COLLECTED,
            source="BAN",
            raw_path="adresse.score_geocodage",
            scope=Scope.DWELLING,
            spatial_scale=Scope.DWELLING,
            domain=Domain.BUILDING,
            source_rank=1,
        )
    )


def _entity_match(collector: dict, meta: dict) -> dict:
    """Determine si l'adresse saisie correspond au groupe BDNB retourne.

    Cas de Nice : adresse saisie n. 73, adresse principale BDNB n. 67, mais la
    cle d'interoperabilite du 73 figure dans la liste du groupe. On conclut a une
    correspondance de GROUPE, sans pretendre disposer d'infos propres au logement.
    """
    adr = collector.get("adresse") or {}
    bd = (collector.get("bdnb") or {}).get("batiment") or {}
    cle_input = (collector.get("bdnb") or {}).get("cle_interop_adr")
    liste = bd.get("l_cle_interop_adr") or []
    principale = bd.get("cle_interop_adr_principale_ban")

    if cle_input and cle_input in liste:
        level = "building_group"
        exact = cle_input == principale
        reason = (
            "adresse saisie presente dans le groupe BDNB"
            + ("" if exact else " mais differente de l'adresse principale du groupe")
        )
    elif cle_input:
        level = "uncertain"
        reason = "cle d'interoperabilite absente de la liste du groupe"
    else:
        level = "none"
        reason = "aucune cle d'interoperabilite BDNB"

    return {
        "level": level,
        "reason": reason,
        "input_label": adr.get("label"),
        "bdnb_principal_label": bd.get("libelle_adr_principale_ban"),
        "n_addresses_in_group": len(liste),
        "parcel_ids": bd.get("l_parcelle_id") or [],
    }


# --- Geographie ------------------------------------------------------------------


def _normalize_geography(collector: dict, bag: VariableBag, meta: dict) -> None:
    alt = collector.get("altitude_m")
    bag.add(
        CanonicalVariable(
            key="site.altitude",
            value=float(alt) if alt is not None else None,
            unit="m",
            status=Status.AVAILABLE if alt is not None else Status.NOT_COLLECTED,
            source="IGN RGE ALTI",
            raw_path="altitude_m",
            scope=Scope.PARCEL,
            spatial_scale=Scope.PARCEL,
            domain=Domain.HAZARD,
            source_rank=1,
            notes="Altitude absolue. NE constitue PAS une altitude relative au "
            "cours d'eau (HAND) ni une distance au littoral.",
        )
    )

    # Variables geospatiales annoncees au data dictionary mais ABSENTES du JSON reel.
    for key, src, note in (
        ("site.distance_to_waterway", "IGN WFS BDTOPO", "module WFS non raccorde au collector"),
        ("site.distance_to_forest", "IGN WFS masque foret", "module WFS non raccorde au collector"),
        ("site.distance_to_coast", "trait de cote", "couche littorale non implementee"),
        ("site.hand", "derive MNT", "non implemente"),
        ("site.twi", "derive MNT", "non implemente"),
        ("site.slope_degrees", "derive MNT", "non implemente ; seuils de la variable "
                                             "categorielle `slope` non documentes"),
    ):
        bag.add(
            CanonicalVariable(
                key=key,
                status=Status.NOT_COLLECTED,
                source=src,
                scope=Scope.PARCEL,
                spatial_scale=Scope.PARCEL,
                domain=Domain.HAZARD,
                source_rank=1,
                notes=note,
            )
        )


# --- BDNB -------------------------------------------------------------------------


def _bdnb_value(bat: dict, field: str) -> tuple[Any, Status]:
    if field not in bat:
        return None, Status.NOT_COLLECTED
    raw = bat.get(field)
    if raw is None:
        return None, Status.UNKNOWN
    if isinstance(raw, str) and raw.strip().upper() in BDNB_UNKNOWN_TOKENS:
        return None, Status.UNKNOWN
    return raw, Status.AVAILABLE


def _add_bdnb(bag: VariableBag, bat: dict, key: str, field: str, *,
              unit=None, scope=Scope.BUILDING_GROUP, domain=Domain.BUILDING,
              rank=4, notes=None) -> None:
    value, status = _bdnb_value(bat, field)
    bag.add(
        CanonicalVariable(
            key=key, value=value, unit=unit, status=status,
            source="BDNB", raw_path=f"bdnb.batiment.{field}",
            scope=scope, spatial_scale=scope, domain=domain,
            source_rank=rank, notes=notes,
        )
    )


def _normalize_bdnb(collector: dict, bag: VariableBag, meta: dict) -> None:
    bdnb = collector.get("bdnb") or {}
    bat = bdnb.get("batiment")
    if not bat:
        meta["source_status"]["bdnb"] = Status.SOURCE_ERROR.value
        return
    meta["source_status"]["bdnb"] = Status.AVAILABLE.value

    dropped = sorted(f for f in PII_FIELDS if f in bat)
    if dropped:
        meta["pii_dropped"] = dropped

    meta["entity_match"] = _entity_match(collector, meta)

    # --- Alea publie a l'echelle du batiment : source primaire de P02 (D02).
    _add_bdnb(bag, bat, "hazard.clay.exposure_class", "alea_argile",
              scope=Scope.BUILDING_GROUP, domain=Domain.HAZARD, rank=1,
              notes="Classe publiee (carte RGA). Ne PAS reappliquer la methode "
                    "BRGM par-dessus : double comptage (D02).")

    # --- Structure : priorite au champ descriptif precis sur le champ generique.
    struct_val, struct_status = _bdnb_value(bat, "materiaux_structure_mur_exterieur")
    generic_val, generic_status = _bdnb_value(bat, "mat_mur_txt")
    if struct_status == Status.AVAILABLE:
        chosen, chosen_field, chosen_status = struct_val, "materiaux_structure_mur_exterieur", struct_status
        note = "Champ descriptif precis retenu ; `mat_mur_txt` generique ignore."
    else:
        chosen, chosen_field, chosen_status = generic_val, "mat_mur_txt", generic_status
        note = "Champ generique utilise faute de description structurelle."
    bag.add(
        CanonicalVariable(
            key="building.structure.wall_material", value=chosen,
            status=chosen_status, source="BDNB",
            raw_path=f"bdnb.batiment.{chosen_field}",
            scope=Scope.BUILDING_GROUP, spatial_scale=Scope.BUILDING_GROUP,
            domain=Domain.BUILDING, source_rank=4, notes=note,
        )
    )

    _add_bdnb(bag, bat, "building.structure.roof_material", "mat_toit_txt")
    _add_bdnb(bag, bat, "building.year_built", "annee_construction", unit="year")
    _add_bdnb(bag, bat, "building.height", "hauteur_mean", unit="m")
    _add_bdnb(bag, bat, "building.levels", "nb_niveau", unit="count")
    _add_bdnb(bag, bat, "building.n_dwellings", "nb_log", unit="count")
    _add_bdnb(bag, bat, "building.footprint_area", "surface_emprise_sol", unit="m2")
    _add_bdnb(bag, bat, "building.usage", "usage_principal_bdnb_open")
    _add_bdnb(bag, bat, "building.dpe_type", "type_batiment_dpe")
    _add_bdnb(bag, bat, "building.has_balcony", "presence_balcon")

    # --- Chauffage et ECS : deux systemes DISTINCTS, jamais fusionnes.
    _add_bdnb(bag, bat, "building.heating.energy", "type_energie_chauffage")
    _add_bdnb(bag, bat, "building.heating.generator", "type_generateur_chauffage")
    _add_bdnb(bag, bat, "building.heating.generator_age", "type_generateur_chauffage_anciennete")
    _add_bdnb(bag, bat, "building.dhw.generator", "type_generateur_ecs",
              notes="Systeme d'ECS distinct du chauffage. Une PAC electrique en "
                    "chauffage et une chaudiere gaz en ECS ne sont PAS une contradiction : "
                    "ce sont deux sources d'ignition a evaluer separement.")
    _add_bdnb(bag, bat, "building.openings.shutter_type", "type_fermeture")
    _add_bdnb(bag, bat, "building.openings.joinery_material", "type_materiaux_menuiserie")
    _add_bdnb(bag, bat, "building.openings.glazing", "type_vitrage")
    _add_bdnb(bag, bat, "building.ventilation", "type_ventilation")

    # --- Fiabilite auto-declaree par BDNB : alimente la confiance, pas les scores.
    for key, field in (
        ("meta.bdnb.reliability_height", "fiabilite_hauteur"),
        ("meta.bdnb.reliability_footprint", "fiabilite_emprise_sol"),
        ("meta.bdnb.reliability_address_1", "fiabilite_cr_adr_niv_1"),
        ("meta.bdnb.reliability_address_2", "fiabilite_cr_adr_niv_2"),
    ):
        _add_bdnb(bag, bat, key, field, domain=Domain.BUILDING, rank=4)

    meta["building_typology"] = _derive_typology(bag)


def _derive_typology(bag: VariableBag) -> dict:
    """Aiguillage maison individuelle / collectif (ADDENDUM §4).

    Le corpus de vulnerabilite du referentiel (BRGM, Mzungu, SafeLand, CEPRI) est
    calibre sur la MAISON INDIVIDUELLE. Appliquer tel quel a une tour de 17 etages
    serait une erreur de categorie, pas une approximation.
    """
    usage = bag.get("building.usage")
    dpe = bag.get("building.dpe_type")
    levels = bag.get("building.levels")
    ndw = bag.get("building.n_dwellings")

    usage_v = (usage.value or "") if usage and usage.usable else ""
    dpe_v = (dpe.value or "") if dpe and dpe.usable else ""
    lv = levels.value if levels and levels.usable else None
    nd = ndw.value if ndw and ndw.usable else None

    collective_signals = []
    if "collectif" in str(usage_v).lower():
        collective_signals.append("usage_principal=collectif")
    if str(dpe_v).lower() == "appartement":
        collective_signals.append("type_batiment_dpe=appartement")
    if nd is not None and nd > 2:
        collective_signals.append(f"nb_log={nd}")
    if lv is not None and lv >= 4:
        collective_signals.append(f"nb_niveau={lv}")

    if collective_signals:
        kind = "collective"
    elif lv is not None and lv <= 3 and (nd is None or nd <= 2):
        kind = "individual_house"
    else:
        kind = "unknown"

    return {
        "kind": kind,
        "signals": collective_signals,
        "levels": lv,
        "n_dwellings": nd,
        "note": (
            "Le corpus de vulnerabilite est calibre sur la maison individuelle. "
            "Pour un bien collectif, les facteurs de type profondeur de fondation "
            "ou distance aux arbres perdent leur validite."
            if kind == "collective" else None
        ),
    }


# --- Georisques -------------------------------------------------------------------


def _normalize_georisques(collector: dict, bag: VariableBag, meta: dict) -> None:
    geo = collector.get("georisques") or {}
    if not geo:
        meta["source_status"]["georisques"] = Status.SOURCE_ERROR.value
        return
    meta["source_status"]["georisques"] = Status.AVAILABLE.value

    geo_errors = {e.get("source"): e.get("erreur") for e in (geo.get("erreurs") or [])}

    # --- Zonage sismique : zonage officiel communal, rang 3, dominant de P03 F.
    zs = (geo.get("zonage_sismique") or {}).get("data") or []
    if zs:
        code = zs[0].get("code_zone")
        bag.add(
            CanonicalVariable(
                key="hazard.seismic.zone",
                value=str(code) if code is not None else None,
                unit="zone",
                status=Status.AVAILABLE if code is not None else Status.UNKNOWN,
                source="Georisques zonage_sismique",
                raw_path="georisques.zonage_sismique.data[0].code_zone",
                scope=Scope.COMMUNE, spatial_scale=Scope.COMMUNE,
                domain=Domain.HAZARD, source_rank=3,
                notes="Zonage reglementaire art. D.563-8-1 du code de l'environnement. "
                      "Echelle communale : les effets de site (classe de sol EC8) "
                      "ne sont pas pris en compte.",
            )
        )
    else:
        bag.add(CanonicalVariable(
            key="hazard.seismic.zone", status=Status.NO_FEATURE_FOUND,
            source="Georisques zonage_sismique", scope=Scope.COMMUNE,
            spatial_scale=Scope.COMMUNE, domain=Domain.HAZARD, source_rank=3))

    # --- Cavites et mouvements de terrain : requetes ponctuelles reelles.
    for key, node, label in (
        ("hazard.landslide.cavities_count", "cavites", "cavites"),
        ("hazard.landslide.events_count", "mouvements_de_terrain", "mouvements de terrain"),
    ):
        blk = geo.get(node)
        if blk is None:
            status, value = Status.SOURCE_ERROR, None
        else:
            n = blk.get("results")
            if n is None:
                status, value = Status.UNKNOWN, None
            elif n == 0:
                # "aucun objet retourne par cette requete", PAS "risque nul".
                status, value = Status.NO_FEATURE_FOUND, 0
            else:
                status, value = Status.AVAILABLE, int(n)
        bag.add(
            CanonicalVariable(
                key=key, value=value, unit="count", status=status,
                source=f"Georisques {node}", raw_path=f"georisques.{node}.results",
                scope=Scope.NEIGHBOURHOOD, spatial_scale=Scope.NEIGHBOURHOOD,
                domain=Domain.HAZARD, source_rank=2,
                notes=f"Zero resultat = aucun objet {label} retourne dans le rayon et "
                      f"selon la couverture de cette base. Rayon et filtres non "
                      f"documentes par le collector : a enregistrer (voir backlog).",
            )
        )

    # --- Zones inondables (AZI) : 404 -> SOURCE_ERROR, jamais "pas de zone".
    azi_err = geo_errors.get("georisques.zones_inondables")
    azi = geo.get("zones_inondables")
    if azi_err is not None or azi is None:
        bag.add(
            CanonicalVariable(
                key="hazard.flood.zone",
                status=Status.SOURCE_ERROR if azi_err else Status.NOT_COLLECTED,
                source="Georisques AZI",
                raw_path="georisques.zones_inondables",
                scope=Scope.PARCEL, spatial_scale=Scope.PARCEL,
                domain=Domain.HAZARD, source_rank=2,
                notes=(f"Erreur endpoint AZI : {azi_err}. Ne PAS interpreter comme "
                       f"une absence de zone inondable." if azi_err else
                       "Endpoint AZI non interroge."),
            )
        )
        if azi_err:
            meta["warnings"].append(
                "AZI en erreur (SOURCE_ERROR) : l'absence de zone inondable n'est PAS etablie."
            )

    # --- Contexte communal : poids strictement nul dans F (D03).
    meta["commune_context"] = _commune_context(geo)
    meta["catnat"] = _catnat_context(geo)


def _commune_context(geo: dict) -> dict:
    data = (geo.get("risques_commune") or {}).get("data") or []
    detail = data[0].get("risques_detail") if data else []
    risks = [
        {"code": d.get("num_risque"), "label": d.get("libelle_risque_long")}
        for d in (detail or [])
    ]
    return {
        "risks": risks,
        "codes": sorted({r["code"] for r in risks if r["code"]}),
        "weight_in_F": 0.0,
        "note": "Presence declaree a l'echelle de la COMMUNE. Ni intensite, ni "
                "exposition au batiment. Poids nul dans F (decision D03/D04).",
    }


def _catnat_context(geo: dict) -> dict:
    cat = geo.get("catnat") or {}
    data = cat.get("data") or []
    announced = cat.get("results")
    pages = cat.get("total_pages")
    complete = (announced is None) or (len(data) >= announced)
    return {
        "records_present": len(data),
        "records_announced": announced,
        "total_pages": pages,
        "pagination_complete": complete,
        "weight_in_F": 0.0,
        "note": "Historique administratif. Un arrete CatNat reflete autant la demarche "
                "de la commune que l'alea physique. Poids nul dans F (D03).",
        "warning": None if complete else
        f"Pagination incomplete : {len(data)}/{announced} enregistrements sur "
        f"{pages} pages. Le collector doit paginer integralement.",
    }


# --- Climat ------------------------------------------------------------------------


def _normalize_climate(collector: dict, bag: VariableBag, meta: dict,
                       errors_by_source: dict) -> None:
    om_err = errors_by_source.get("open_meteo")
    om = collector.get("climat_open_meteo")
    om_status = (
        Status.SOURCE_ERROR if om_err else
        (Status.AVAILABLE if om else Status.NOT_COLLECTED)
    )
    meta["source_status"]["open_meteo"] = om_status.value
    if om_err:
        meta["warnings"].append(f"Open-Meteo en erreur : {om_err[:120]}")

    # Variables climatiques necessaires aux scores, avec leur statut REEL.
    # Le collector observe ne demande que temperature_2m_max et precipitation_sum.
    collected_daily = {"temperature_2m_max", "precipitation_sum"}
    needed = {
        "climate.freeze_days": ("temperature_2m_min", "count/an", Domain.HAZARD),
        "climate.wind_speed_max_stat": ("wind_speed_10m_max", "m/s", Domain.HAZARD),
        "climate.relative_humidity_mean": ("relative_humidity_2m_mean", "%", Domain.HAZARD),
        "climate.soil_moisture": ("soil_moisture_0_to_10cm_mean", "m3/m3", Domain.HAZARD),
        "climate.consecutive_dry_days": ("precipitation_sum", "count", Domain.HAZARD),
        "climate.annual_precipitation": ("precipitation_sum", "mm", Domain.HAZARD),
    }
    for key, (dep, unit, dom) in needed.items():
        if dep not in collected_daily:
            status = Status.NOT_COLLECTED
            note = (f"Depend de `{dep}`, non demande par le collector "
                    f"(daily=temperature_2m_max,precipitation_sum).")
        elif om_status is Status.SOURCE_ERROR:
            status = Status.SOURCE_ERROR
            note = f"Depend de `{dep}` ; l'appel Open-Meteo a echoue."
        elif om_status is Status.NOT_COLLECTED:
            status = Status.NOT_COLLECTED
            note = "Bloc climat absent du JSON."
        else:
            status = Status.UNKNOWN
            note = f"Derive de `{dep}` : derivation non implementee."
        bag.add(
            CanonicalVariable(
                key=key, unit=unit, status=status, source="Open-Meteo",
                raw_path="climat_open_meteo", scope=Scope.CLIMATE_GRID,
                spatial_scale=Scope.CLIMATE_GRID, domain=dom,
                time_horizon=TimeHorizon.HISTORICAL, source_rank=4, notes=note,
            )
        )

    cop_err = errors_by_source.get("copernicus")
    cop_status = Status.NOT_CONFIGURED if cop_err else (
        Status.AVAILABLE if collector.get("climat_copernicus") else Status.NOT_COLLECTED
    )
    meta["source_status"]["copernicus"] = cop_status.value
    if cop_err:
        meta["warnings"].append(f"Copernicus non configure : {cop_err[:120]}")

    meta["source_status"]["dvf"] = "EXCLUDED_BY_DESIGN"
    meta["prospective_context"] = {
        "available": False,
        "note": "Aucune donnee prospective (DRIAS/Copernicus) dans ce run. Les "
                "projections restent de toute facon exclues de F, V et R (D05).",
    }


# --- Reponses utilisateur ------------------------------------------------------------


def _normalize_answers(answers: dict, bag: VariableBag, meta: dict) -> None:
    """Injecte les reponses structurees du questionnaire.

    Format attendu par cle : {"value": ..., "basis": "observe|document|souvenir|
    estimation|inconnu", "date": "YYYY-MM-DD", "evidence": "..."}
    Une valeur scalaire nue est acceptee et traitee comme `estimation`.
    """
    n_answered = 0
    for key, payload in (answers or {}).items():
        if isinstance(payload, dict):
            value = payload.get("value")
            basis = (payload.get("basis") or "estimation").strip().lower()
            date = payload.get("date")
        else:
            value, basis, date = payload, "estimation", None

        if basis == "inconnu" or value is None:
            status = Status.USER_UNKNOWN
            rank = 5
        else:
            status = Status.AVAILABLE
            rank = ANSWER_BASIS_RANK.get(basis, 3)
            n_answered += 1

        bag.add(
            CanonicalVariable(
                key=key, value=value if status is Status.AVAILABLE else None,
                status=status, source="questionnaire",
                raw_path=f"questionnaire.{key}", scope=Scope.DWELLING,
                spatial_scale=Scope.DWELLING, domain=Domain.BUILDING,
                source_rank=rank, observation_date=date, answer_basis=basis,
            )
        )
    meta["answers_provided"] = n_answered
