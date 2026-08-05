"""
F-B3 (coût net des travaux) + F-D1 (retour sur investissement) + F-D2
(valeur immobilière, qualitative) — assemblage du volet économique.

F-B3 :
    C_net = Σ c_i × (1 − r_sub)   borné par le plafond FPRNM (36 000 € et
                                   50 % de la valeur vénale)
    c_i = cout_estime sourcé (fiches MRN/BRGM/CEPRI/ADEME, data/index.json)
    r_sub = 0,80 uniquement pour les mesures éligibles au fonds Barnier/FPRNM
            (l'aide du fiche le mentionne), sinon 0.

F-D1 :
    TR (années) = C_net / (B_assu + B_AAL)     — seulement si B_total > 0
    jamais de durée inventée ; le TR hérite du statut `fourchette`.

F-D2 : les décotes de valeur à la revente (littérature US) sont EXCLUES du
ROI et présentées qualitativement avec leurs limites (cf. doc §3.5).
"""

from __future__ import annotations

from typing import Any

from app.economie.benefice_assurance import benefice_assurance
from app.economie.schemas import CALCULE, FOURCHETTE, NULL, bloc, bloc_null
from app.economie.sources import source_refs
from app.economie.valuateur import estimer_valeur
from app.economie.effet_travaux import _bucket_zone, appliquer_effets
from app.economie.aal import aal_inondation

# FPRNM : subvention 80 %, plafonds 36 000 € / 50 % valeur vénale (réf. FPRNM).
_SUB_RATE = 0.80
_CAP_EUR = 36_000.0
_CAP_VALEUR_VENALE_RATIO = 0.50

_ELIG_FPRNM_KEYWORDS = ("fprnm", "barnier", "fonds de prevention", "fonds de prévention", "fond de prevention", "fond barnier")


def _est_eligible_fprnm(reco: dict[str, Any]) -> bool:
    aide = reco.get("aide") or {}
    dispositif = str(aide.get("dispositif") or "")
    if not dispositif:
        return False
    return any(kw in dispositif.lower() for kw in _ELIG_FPRNM_KEYWORDS)


def cout_travaux(risk_scores: dict[str, Any], valeur: dict[str, Any]) -> dict[str, Any]:
    """Niveau B / F-B3 : coût brut, subvention FPRNM et coût net à charge."""
    par_mesure: list[dict[str, Any]] = []
    total_min = 0.0
    total_max = 0.0
    sub_min = 0.0
    sub_max = 0.0
    n_cout_sources = 0
    n_recos = 0
    n_avec_cout = 0

    zones = risk_scores.get("zones", {})
    # Une même recommandation est dupliquée sur les 4 zones murs_* (facade) :
    # dédupliquée par (bucket de zone, mesure) pour ne pas compter le coût 4×.
    vues: set[tuple[str, str]] = set()
    for zone_name, zone_data in zones.items():
        for reco in zone_data.get("recommandations") or []:
            if not isinstance(reco, dict):
                continue
            cle = (_bucket_zone(zone_name), reco.get("mesure"))
            if cle in vues:
                continue
            vues.add(cle)
            n_recos += 1
            cout = reco.get("cout_estime")
            if not cout:
                continue
            try:
                c_min = float(cout.get("montant_min"))
                c_max = float(cout.get("montant_max"))
            except (TypeError, ValueError):
                continue
            if c_min <= 0 or c_max <= 0:
                continue
            n_avec_cout += 1
            eligible = _est_eligible_fprnm(reco)
            if eligible:
                n_cout_sources += 1
                sub_min += _SUB_RATE * c_min
                sub_max += _SUB_RATE * c_max

            sources = reco.get("sources") or []
            par_mesure.append(
                {
                    "zone": zone_name,
                    "mesure": reco.get("mesure"),
                    "cout_brut_min": round(c_min, 2),
                    "cout_brut_max": round(c_max, 2),
                    "eligible_fprnm": eligible,
                    "subvention_taux": _SUB_RATE if eligible else 0.0,
                    "sources": sources,
                }
            )
            total_min += c_min
            total_max += c_max

    if not par_mesure:
        return {
            "par_mesure": [],
            "total_brut": bloc_null(
                "aucune recommandation ne porte de coût sourcé (cout_estime "
                "absent des fiches) → aucun montant de travaux affiché"
            ),
            "subvention_fprnm": bloc_null("aucun coût éligible"),
            "cout_net": bloc_null("aucun coût de travaux sourcé"),
            "statut": NULL,
        }

    # Plafond FPRNM : min(36 000 €, 50 % de la valeur vénale).
    valeur_bloc = valeur.get("valeur_reconstruction")
    plafond = _CAP_EUR
    if valeur_bloc and valeur_bloc.get("statut") != NULL and valeur_bloc.get("valeur"):
        plafond = min(_CAP_EUR, _CAP_VALEUR_VENALE_RATIO * valeur_bloc["valeur"])

    sub_appliquee_min = min(sub_min, plafond)
    sub_appliquee_max = min(sub_max, plafond)
    net_min = total_min - sub_appliquee_min
    net_max = total_max - sub_appliquee_max

    statut = CALCULE if abs(net_min - net_max) < 1e-6 else FOURCHETTE
    sources = [*source_refs("FPRNM")]
    if n_cout_sources:
        sources += source_refs("MRN2024", "MRN2023")

    return {
        "par_mesure": par_mesure,
        "total_brut": bloc(
            statut=statut,
            min=round(total_min, 2),
            max=round(total_max, 2),
            sources=sources,
            hypotheses=[
                "coûts recopiés intégralement des fiches de l'index RAG "
                "(MRN/BRGM/CEPRI/ADEME) — aucun montant inventé"
            ],
            confidence=70,
        ),
        "subvention_fprnm": bloc(
            statut=CALCULE if sub_appliquee_min == sub_appliquee_max else FOURCHETTE,
            min=round(sub_appliquee_min, 2),
            max=round(sub_appliquee_max, 2),
            sources=sources,
            hypotheses=[
                f"subvention appliquée uniquement aux mesures dont la fiche cite le "
                f"fonds Barnier/FPRNM ; plafond = min({_CAP_EUR:,.0f} €, "
                f"50 % de la valeur vénale)"
            ],
            confidence=70,
        ),
        "cout_net": bloc(
            statut=statut,
            min=round(net_min, 2),
            max=round(net_max, 2),
            sources=sources,
            hypotheses=[
                "coût net à charge du propriétaire = coût brut − subvention FPRNM "
                "plafonnée (F-B3 du doc)"
            ],
            confidence=70,
        ),
        "statut": statut,
        "n_recommandations": n_recos,
        "n_avec_cout": n_avec_cout,
    }


def _benefice_annuel_total(bene: dict[str, Any], aal: dict[str, Any]) -> dict[str, Any]:
    """B_total = B_assu + B_AAL (les deux sont des montants annuels)."""
    from app.economie.schemas import sommes_blocs

    return sommes_blocs([bene["total"], aal])


def calculer_roi(cout: dict[str, Any], bene: dict[str, Any], aal: dict[str, Any]) -> dict[str, Any]:
    """F-D1 : temps de retour simple = C_net / B_total, seulement si B_total > 0."""
    net = cout.get("cout_net") or {}
    b_total = _benefice_annuel_total(bene, aal)

    if b_total.get("statut") == NULL:
        return {
            "temps_de_retour": bloc_null("bénéfice annuel total non calculé"),
            "benefice_annuel_total": b_total,
            "regle": "TR = C_net / (B_assu + B_AAL)",
        }

    b_min = b_total.get("min") or b_total.get("valeur") or 0.0
    b_max = b_total.get("max") or b_total.get("valeur") or 0.0
    if b_max <= 0:
        return {
            "temps_de_retour": bloc_null(
                "bénéfice annuel total nul ou négatif (aucun arrêté CATNAT, "
                "pas d'AAL inondation) → temps de retour non défini"
            ),
            "benefice_annuel_total": b_total,
            "regle": "TR = C_net / (B_assu + B_AAL)",
        }

    if net.get("statut") == NULL:
        return {
            "temps_de_retour": bloc_null("coût net des travaux non calculé"),
            "benefice_annuel_total": b_total,
            "regle": "TR = C_net / (B_assu + B_AAL)",
        }

    net_min = net.get("min") or net.get("valeur")
    net_max = net.get("max") or net.get("valeur")
    # TR borne : coût le plus faible / gain le plus fort -> TR minimal, et
    # coût le plus fort / gain le plus faible -> TR maximal.
    tr_min = net_min / b_max
    tr_max = net_max / b_min

    return {
        "temps_de_retour": bloc(
            statut=FOURCHETTE,
            min=round(tr_min, 1),
            max=round(tr_max, 1),
            sources=source_refs("CICC2026", "FEMA2018"),
            hypotheses=[
                "temps de retour simple (années) = coût net / bénéfice annuel total ; "
                "les bornes reflètent les bornes des composantes",
                "le NPV (taux 3 %, maintenance 1 %/an) est une option F-D1 non "
                "activée — cf. doc §7",
            ],
            confidence=50,
        ),
        "benefice_annuel_total": b_total,
        "regle": "TR = C_net / (B_assu + B_AAL)",
    }


_VALEUR_IMMOBILIERE_ETUDES = [
    {
        "source_id": "JFE2019",
        "resultat": "décote ~7 % (exposé à l'élévation du niveau de la mer), ~4 % "
                    "(même inondation lointaine)",
        "limites": "US, zones côtières, élévation du niveau de la mer uniquement — "
                   "non transposable tel quel en France",
    },
    {
        "source_id": "RFS2020",
        "resultat": "écart ~7 % entre quartiers « croyants » et « sceptiques » au risque",
        "limites": "décote liée aux croyances, pas à un risque objectif",
    },
    {
        "source_id": "ECB2025",
        "resultat": "pénalité sur l'immobilier commercial exposé, croissante 2007-2023",
        "limites": "qualitatif/relatif, pas de pourcentage unique",
    },
    {
        "source_id": "JPM2021",
        "resultat": "décote post-événement modeste et temporaire ; effets de long terme incertains",
        "limites": "synthèse de littérature — recommande de ne pas afficher de % certain",
    },
]


def valeur_immobiliere() -> dict[str, Any]:
    """F-D2 : gain de valeur à la revente — qualitatif, EXCLU du ROI."""
    return {
        "exclu_du_roi": True,
        "raison": (
            "la littérature ne permet pas un pourcentage de décote fiable et "
            "transposable pour un bien français (US, côtière, effets de croyances) — "
            "présenté en liste avec limites, jamais additionné au ROI"
        ),
        "etudes": _VALEUR_IMMOBILIERE_ETUDES,
    }


def evaluate(building_data: dict[str, Any], risk_scores: dict[str, Any], surface_m2: float | None = None) -> dict[str, Any]:
    """Assemble le contrat économique complet (niveaux A, B, C + ROI)."""
    valeur = estimer_valeur(building_data, surface_m2)
    effet = appliquer_effets(risk_scores)
    bene = benefice_assurance(building_data)
    aal = aal_inondation(valeur, building_data)
    cout = cout_travaux(risk_scores, valeur)
    roi = calculer_roi(cout, bene, aal)

    disponibilites = [
        valeur["valeur_reconstruction"].get("statut") != NULL,
        cout["cout_net"].get("statut") != NULL,
        bene["total"].get("statut") != NULL,
        aal.get("statut") != NULL,
    ]
    hypotheses = [
        bool(effet["par_mesure"]),
        bool(aal.get("hypotheses")),
        bool(valeur["valeur_reconstruction"].get("hypotheses")),
    ]
    confidence = _confiance(disponibilites, hypotheses)

    return {
        "schema_version": "1.0",
        "niveau_a": effet,
        "niveau_b": {
            "benefice_assurance": bene,
            "cout_travaux": cout,
        },
        "niveau_c": aal,
        "valeur": valeur,
        "roi": roi,
        "valeur_immobiliere": valeur_immobiliere(),
        "confidence": confidence,
    }


def _confiance(disponibilites: list[bool], hypotheses: list[bool]) -> dict[str, Any]:
    from app.economie.schemas import calculer_confiance

    if not any(disponibilites):
        return {"score": 0, "niveau": "indetermine", "composantes": {}}
    dispo = sum(1 for d in disponibilites if d) / len(disponibilites)
    hyp = 1.0 - (sum(1 for h in hypotheses if h) / len(hypotheses)) if hypotheses else 1.0
    score = dispo * 60.0 + hyp * 25.0 + 15.0
    if score >= 80:
        niveau = "elevee"
    elif score >= 60:
        niveau = "bonne"
    elif score >= 40:
        niveau = "moyenne"
    else:
        niveau = "faible"
    return {
        "score": round(score),
        "niveau": niveau,
        "composantes": {
            "disponibilite_entrees": round(dispo, 3),
            "absence_hypotheses": round(hyp, 3),
        },
    }
