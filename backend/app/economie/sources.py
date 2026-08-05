"""
Registre des sources du volet économique — correspond au §4 de
docs/STRATEGIE_RETOUR_INVESTISSEMENT.md (refs 1-16). Chaque paramètre
utilisé dans les formules F-A1 -> F-D2 doit porter ses `source_ids` ici.

Deux règles :
- Ne jamais citer ici une référence non vérifiée (van Ierland, UNEP FI,
  GCA sont marqués « non vérifié » dans le doc §5 et ne figurent PAS ici).
- La liste de sources est renvoyée telle quelle dans le contrat JSON : un
  montant n'est jamais affiché sans sa liste de sources.
"""

from __future__ import annotations

SOURCE_REGISTRY: dict[str, str] = {
    "JFE2019": (
        "Bernstein, A., Gustafson, M., Lewis, R. (2019). Disaster on the Horizon: "
        "The Price Effect of Sea Level Rise. J. Financial Economics 134(2), 253-272. "
        "DOI 10.1016/j.jfineco.2019.03.013."
    ),
    "RFS2020": (
        "Baldauf, M., Garlappi, L., Yannelis, C. (2020). Does Climate Change Affect "
        "Real Estate Prices? Only If You Believe In It. Rev. Financial Studies 33(3), "
        "1256-1295. DOI 10.1093/rfs/hhz073."
    ),
    "ECB2025": (
        "Foerster, K., Ryan, E., Scheid, B. (2025). Pricing or panicking? Commercial "
        "real estate markets and climate change. ECB Working Paper 3059. "
        "DOI 10.2866/3583063."
    ),
    "JPM2021": (
        "Clayton, J., Devaney, S., Sayce, S., Van de Wetering, J. (2021). Climate Risk "
        "and Real Estate Prices: What Do We Know? J. Portfolio Management 47(10), 75-90. "
        "DOI 10.3905/jpm.2021.1.278."
    ),
    "FW2022": (
        "Gnan, E., Friedland, C., Rahim, M.A., Mostafiz, R.B., Rohli, R., Orooji, F., "
        "Taghinezhad, A., McElwee, J. (2022). Improved building-specific flood risk "
        "assessment and implications of depth-damage function selection. Frontiers in "
        "Water 4:919726. DOI 10.3389/frwa.2022.919726."
    ),
    "IJER2024": (
        "Al Assi, A., Mostafiz, R.B., Friedland, C., Rohli, R. (2024). Theoretical "
        "Boundaries of Annual Flood Risk for Single-Family Homes Within the 100-Year "
        "Floodplain. Int. J. Environ. Res. 18(2). DOI 10.1007/s41742-024-00577-7."
    ),
    "CICC2026": (
        "Campos Rodrigues, L., Riera-Spiegelhalder, M., Navarro, F., et al. (2026). "
        "Hybrid adaptation to urban riverine floods: a cost-benefit analysis in "
        "Vilanova i la Geltru (Spain). Critical Insights in Climate Change 2(1). "
        "DOI 10.1080/29931495.2025.2590372."
    ),
    "FEMA2018": (
        "FEMA (2018). Guidance for Flood Risk Analysis and Mapping — formule "
        "annualized loss. fema.gov."
    ),
    "USACE2001": (
        "USACE (2001). Economic Guidance Memorandum 01-03, Generic Depth-Damage "
        "Relationships. planning.erdc.dren.mil."
    ),
    "BRGM2009": (
        "P. Plat, BRGM RP-56771-FR — Impacts du changement climatique, adaptation et "
        "couts associes en France pour le risque de secheresse geotechnique (couts RGA, "
        "donnees CCR)."
    ),
    "CCR2023": (
        "CCR / SDES (2023). Chiffres cles des risques naturels (cout moyen sinistre "
        "RGA 21 000 € ; sinistralite secheresse +30 %/+60 % a 2050)."
    ),
    "COURCOMPTES": (
        "Cout moyen d'un sinistre retrait-gonflement des argiles : 16 500 € — "
        "ecologie.gouv.fr, source Cour des Comptes (cite doc §3.3)."
    ),
    "MRN2024": (
        "MRN / France Assureurs (2024). Referentiels de resilience du bati aux aleas "
        "naturels (couts et efficacite des mesures de prevention)."
    ),
    "MRN2023": (
        "MRN (2023). Prevention, adaptation, rehabilitation face au retrait-gonflement "
        "des argiles (ecologie.gouv.fr) — couts des mesures (ecran racinaire/bordure "
        "2-5 k€ HT, gouttieres/descentes 1 000 € HT)."
    ),
    "ARRETE2023": (
        "Arrete du 28/12/2023 : surprime CatNat 12 % -> 20 % au 1/1/2025 "
        "(presse.economie.gouv.fr)."
    ),
    "D1255": (
        "Code des assurances art. D.125-5 et suivants : franchises de sinistre "
        "CatNat — 380 € (aleas courants) / 1 520 € (retrait-gonflement des argiles) "
        "(synthese georisques.gouv.fr, mise a jour 2024)."
    ),
    "FPRNM": (
        "Plaquette FPRNM / fonds Barnier (DDT de l'Ain, habitat) : subvention 80 %, "
        "plafonds 36 000 € et 50 % de la valeur venale."
    ),
    "SENAT2024": (
        "Rapport Lavarde « Le regime CatNat : prevenir la catastrophe financiere », "
        "Sénat r23-603 (mai 2024) ; PPL adoptee au Senat le 29/10/2024 — cadre de "
        "modulation future de la franchise/surprime selon la prevention."
    ),
    "CATNAT_GEO": (
        "Arretes CATNAT de la commune — georisques.gouv.fr, donnees collectees par "
        "collector_agent (champ georisques.catnat.data)."
    ),
    "DVF": (
        "Transactions DVF (demandes de valeurs foncieres) de la commune — donnees "
        "reelles du projet (collector_agent -> dvf_local)."
    ),
    "MOTEUR_PROJET": (
        "Moteur de score F/V/R du projet — backend/app/scoring/risk_model.py "
        "(R = 100 x (F/100)^0.5 x (V/100)^0.5 ; formule F-A1 du doc)."
    ),
    "HAZUS_METHODE": (
        "Methode HAZUS : cout de remplacement = surface x cout unitaire — FEMA, "
        "Hazus 7.0 Flood Model Technical Manual (2025)."
    ),
}

NON_VERIFIEES = {
    "van_ierland_wageningen": (
        "van Ierland, Weikard et al., Cost benefit analysis for climate change "
        "adaptation (Wageningen) — NON VERIFIE, jamais cite comme source de parametre."
    ),
    "unep_fi_2021": (
        "UNEP FI (2021), Climate Risk and Commercial Property Values — rapport "
        "d'origine du papier JPM n°4, NON RELU, non utilise."
    ),
    "gca": (
        "Rapports GCA (Global Center on Adaptation) — NON RELUS, cites en qualitatif "
        "uniquement."
    ),
}


def source_refs(*ids: str) -> list[dict[str, str]]:
    """Construit la liste `sources` d'un bloc de sortie à partir d'ids du
    registre. Lève une erreur si un id est inconnu : un montant ne doit
    jamais être émis avec une référence fantôme."""
    refs = []
    for sid in ids:
        if sid not in SOURCE_REGISTRY:
            raise KeyError(f"Reference economique inconnue : {sid!r}")
        refs.append({"id": sid, "reference": SOURCE_REGISTRY[sid]})
    return refs
