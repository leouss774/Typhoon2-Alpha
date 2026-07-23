"""
Données de test simulant la sortie du risk engine orchestrateur
pour 3 adresses réelles françaises différentes.
"""

# ─── ADRESSE 1 : Paris 15e — zone urbaine dense ───────────────────────────────
ADRESSE_1_PARIS = {
    "formulaire": {
        "adresse": "15 Rue Lacordaire, 75015 Paris",
        "type_bien": "appartement",
        "surface_m2": 65,
        "etage": 3,
        "annee_construction": 1972,
        "valeur_bien": 550000,
        "nom_client": "Martin Dupont",
        "usage": "residence_principale"
    },
    "donnees_risk_engine": {
        "coordonnees": {"lat": 48.8417, "lon": 2.2954},
        "commune": {"nom": "Paris", "code_insee": "75115", "departement": "75"},

        # BDNB
        "bdnb": {
            "dpe_classe": "D",
            "consommation_ep_kwh_m2_an": 210,
            "emissions_ges_kg_co2_m2_an": 45,
            "annee_dpe": 2022,
            "type_chauffage": "gaz_collectif",
            "type_construction": "beton",
            "nb_logements_batiment": 24
        },

        # Géorisques
        "georisques": {
            "zone_sismique": 1,
            "alea_inondation": "faible",
            "ppr_inondation": False,
            "ppr_risque_naturel": False,
            "retrait_gonflement_argile": "faible",
            "mouvement_terrain": False,
            "radon": 1,
            "installations_classees_500m": 2,
            "canalisations_matieres_dangereuses": True
        },

        # IGN
        "ign": {
            "altitude_m": 42,
            "distance_cours_eau_m": 850,
            "distance_mer_km": 250,
            "pente_pct": 1.2,
            "zone_urbaine": True,
            "densite_batiment_ha": 85,
            "presence_foret_5km": False
        },

        # Open-Meteo (données climatiques récentes)
        "open_meteo": {
            "temperature_moy_annuelle_c": 12.5,
            "temperature_max_record_c": 42.6,
            "precipitations_moy_annuelles_mm": 641,
            "jours_canicule_an": 8,
            "jours_gel_an": 15,
            "vitesse_vent_max_ms": 28.5
        },

        # CATNAT
        "catnat": {
            "arretes_depuis_1982": 3,
            "types_sinistres": ["inondation", "tempete"],
            "dernier_arrete": "2016-06-01",
            "montants_sinistres_estimes": 45000
        },

        # DVF
        "dvf": {
            "prix_m2_median_commune": 9800,
            "nb_transactions_12mois": 1250,
            "tendance_prix_12mois_pct": -2.1,
            "delai_vente_median_jours": 55,
            "prix_vente_bien_similaire_min": 8200,
            "prix_vente_bien_similaire_max": 11500
        },

        # DRIAS (projections climatiques)
        "drias": {
            "horizon_2050": {
                "rcp45": {
                    "delta_temp_ete_c": +1.8,
                    "delta_temp_hiver_c": +1.2,
                    "delta_precipitations_ete_pct": -12,
                    "delta_precipitations_hiver_pct": +8,
                    "jours_canicule_supplementaires": 12,
                    "jours_secheresse_supplementaires": 18
                },
                "rcp85": {
                    "delta_temp_ete_c": +3.2,
                    "delta_temp_hiver_c": +2.5,
                    "delta_precipitations_ete_pct": -22,
                    "delta_precipitations_hiver_pct": +15,
                    "jours_canicule_supplementaires": 28,
                    "jours_secheresse_supplementaires": 35
                }
            },
            "montee_eaux_cm_2050": 25,
            "intensite_evenements_extremes": "augmentation_moderee"
        }
    }
}


# ─── ADRESSE 2 : Bordeaux — zone inondable, vignoble, chaleur ─────────────────
ADRESSE_2_BORDEAUX = {
    "formulaire": {
        "adresse": "8 Allée de la Garonne, 33100 Bordeaux",
        "type_bien": "maison",
        "surface_m2": 145,
        "surface_terrain_m2": 320,
        "etages": 2,
        "annee_construction": 1958,
        "valeur_bien": 480000,
        "nom_client": "Sophie Bernard",
        "usage": "residence_principale"
    },
    "donnees_risk_engine": {
        "coordonnees": {"lat": 44.8378, "lon": -0.5792},
        "commune": {"nom": "Bordeaux", "code_insee": "33063", "departement": "33"},

        "bdnb": {
            "dpe_classe": "E",
            "consommation_ep_kwh_m2_an": 310,
            "emissions_ges_kg_co2_m2_an": 65,
            "annee_dpe": 2021,
            "type_chauffage": "fioul",
            "type_construction": "pierre_moellon",
            "nb_logements_batiment": 1
        },

        "georisques": {
            "zone_sismique": 1,
            "alea_inondation": "fort",
            "ppr_inondation": True,
            "zone_inondable_100ans": True,
            "ppr_risque_naturel": True,
            "retrait_gonflement_argile": "moyen",
            "mouvement_terrain": False,
            "radon": 1,
            "installations_classees_500m": 0
        },

        "ign": {
            "altitude_m": 3,
            "distance_cours_eau_m": 120,
            "distance_mer_km": 90,
            "pente_pct": 0.3,
            "zone_urbaine": True,
            "densite_batiment_ha": 25,
            "presence_foret_5km": True,
            "surface_foret_5km_ha": 450
        },

        "open_meteo": {
            "temperature_moy_annuelle_c": 14.2,
            "temperature_max_record_c": 44.1,
            "precipitations_moy_annuelles_mm": 942,
            "jours_canicule_an": 15,
            "jours_gel_an": 8,
            "vitesse_vent_max_ms": 35.2,
            "jours_pluie_intense_an": 22
        },

        "catnat": {
            "arretes_depuis_1982": 12,
            "types_sinistres": ["inondation", "secheresse", "tempete", "grele"],
            "dernier_arrete": "2021-03-15",
            "crue_reference_m": 1.8,
            "montants_sinistres_estimes": 125000
        },

        "dvf": {
            "prix_m2_median_commune": 3850,
            "nb_transactions_12mois": 580,
            "tendance_prix_12mois_pct": -4.2,
            "delai_vente_median_jours": 75,
            "decote_zone_inondable_pct": -15,
            "prix_vente_bien_similaire_min": 2900,
            "prix_vente_bien_similaire_max": 4800
        },

        "drias": {
            "horizon_2050": {
                "rcp45": {
                    "delta_temp_ete_c": +2.2,
                    "delta_temp_hiver_c": +1.5,
                    "delta_precipitations_ete_pct": -18,
                    "delta_precipitations_hiver_pct": +12,
                    "jours_canicule_supplementaires": 18,
                    "jours_secheresse_supplementaires": 28,
                    "risque_incendie_multiplie_par": 2.5
                },
                "rcp85": {
                    "delta_temp_ete_c": +4.1,
                    "delta_temp_hiver_c": +3.0,
                    "delta_precipitations_ete_pct": -35,
                    "delta_precipitations_hiver_pct": +20,
                    "jours_canicule_supplementaires": 45,
                    "jours_secheresse_supplementaires": 55,
                    "risque_incendie_multiplie_par": 5.2
                }
            },
            "montee_eaux_cm_2050": 35,
            "intensite_evenements_extremes": "augmentation_forte"
        }
    }
}


# ─── ADRESSE 3 : Nice — littoral, séisme, incendie, submersion ────────────────
ADRESSE_3_NICE = {
    "formulaire": {
        "adresse": "42 Boulevard Carnot, 06300 Nice",
        "type_bien": "appartement",
        "surface_m2": 82,
        "etage": 1,
        "annee_construction": 1965,
        "valeur_bien": 650000,
        "nom_client": "Jean-Marc Rossi",
        "usage": "residence_secondaire"
    },
    "donnees_risk_engine": {
        "coordonnees": {"lat": 43.7102, "lon": 7.2620},
        "commune": {"nom": "Nice", "code_insee": "06088", "departement": "06"},

        "bdnb": {
            "dpe_classe": "C",
            "consommation_ep_kwh_m2_an": 155,
            "emissions_ges_kg_co2_m2_an": 28,
            "annee_dpe": 2023,
            "type_chauffage": "pompe_chaleur",
            "type_construction": "beton_ancien",
            "nb_logements_batiment": 18
        },

        "georisques": {
            "zone_sismique": 4,
            "alea_inondation": "modere",
            "ppr_inondation": True,
            "ppr_risque_naturel": True,
            "ppr_seisme": False,
            "retrait_gonflement_argile": "faible",
            "mouvement_terrain": True,
            "radon": 1,
            "risque_tsunami": True,
            "installations_classees_500m": 1
        },

        "ign": {
            "altitude_m": 8,
            "distance_cours_eau_m": 250,
            "distance_mer_km": 0.8,
            "pente_pct": 2.1,
            "zone_urbaine": True,
            "densite_batiment_ha": 95,
            "presence_foret_5km": True,
            "surface_foret_5km_ha": 1200,
            "zone_littorale": True
        },

        "open_meteo": {
            "temperature_moy_annuelle_c": 16.1,
            "temperature_max_record_c": 38.5,
            "precipitations_moy_annuelles_mm": 780,
            "jours_canicule_an": 25,
            "jours_gel_an": 2,
            "vitesse_vent_max_ms": 42.0,
            "jours_pluie_intense_an": 35,
            "episodes_mistral_an": 45
        },

        "catnat": {
            "arretes_depuis_1982": 18,
            "types_sinistres": ["inondation", "tempete", "mouvement_terrain", "secheresse"],
            "dernier_arrete": "2023-10-15",
            "catastrophe_notable": "Inondations Nice Oct 2020 (8 morts)",
            "montants_sinistres_estimes": 280000
        },

        "dvf": {
            "prix_m2_median_commune": 5200,
            "nb_transactions_12mois": 920,
            "tendance_prix_12mois_pct": +1.8,
            "delai_vente_median_jours": 48,
            "prime_vue_mer_pct": +20,
            "decote_risque_inondation_pct": -8,
            "prix_vente_bien_similaire_min": 4100,
            "prix_vente_bien_similaire_max": 7500
        },

        "drias": {
            "horizon_2050": {
                "rcp45": {
                    "delta_temp_ete_c": +1.9,
                    "delta_temp_hiver_c": +1.3,
                    "delta_precipitations_ete_pct": -15,
                    "delta_precipitations_hiver_pct": +10,
                    "jours_canicule_supplementaires": 22,
                    "risque_incendie_multiplie_par": 3.0,
                    "frequence_pluies_intenses_multiplice_par": 1.4
                },
                "rcp85": {
                    "delta_temp_ete_c": +3.5,
                    "delta_temp_hiver_c": +2.8,
                    "delta_precipitations_ete_pct": -28,
                    "delta_precipitations_hiver_pct": +18,
                    "jours_canicule_supplementaires": 42,
                    "risque_incendie_multiplie_par": 6.0,
                    "frequence_pluies_intenses_multiplie_par": 1.8
                }
            },
            "montee_eaux_cm_2050": 40,
            "intensite_evenements_extremes": "augmentation_tres_forte",
            "risque_submersion_aggrave": True
        }
    }
}

# Données DRIAS génériques pour projection 2050
DRIAS_FRANCE_GENERIQUE = {
    "modele": "CNRM-CM6-1",
    "periode_reference": "1981-2010",
    "horizon_projection": "2041-2070",
    "note": "Données issues de la plateforme DRIAS - Les futurs du climat"
}
