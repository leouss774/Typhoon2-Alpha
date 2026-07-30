"""
Routes de compatibilité (legacy) — pont entre l'ancienne API frontend
et la nouvelle API backend basée sur Typhoon2-Alpha.

Ces routes permettent au frontend React existant de fonctionner
sans changement avec la nouvelle architecture.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from backend.app.agents.graph import diagnostic_graph
from backend.app.core.logging import get_logger

from backend.services import dvf_service
from backend.services.pdf_generator import generate_bank_report_pdf
from backend.services.analyses_store import get_analysis, set_analysis, analyses_store

# Import partagé du store diagnostic (analyses new-format)
try:
    from backend.app.api.routes.diagnostic import analyses_store as diagnostic_store
except ImportError:
    diagnostic_store = {}

logger = get_logger(__name__)
router = APIRouter()


class LegacyAnalyzeRequest(BaseModel):
    session_id: str | None = None
    client_form: dict
    raw_data: dict = {}


# ─── Routes d'analyse ──────────────────────────────────────────────

@router.post("/analyze")
async def legacy_analyze(req: LegacyAnalyzeRequest):
    """Route legacy : POST /api/analyze → nouveau diagnostic"""
    session_id = req.session_id or f"session-{uuid.uuid4().hex[:12]}"
    form_data = req.client_form
    adresse = form_data.get("adresse", "")

    if not adresse:
        raise HTTPException(status_code=400, detail="L'adresse est obligatoire")

    try:
        final_state = await diagnostic_graph.ainvoke(
            {"adresse": adresse, "formulaire": form_data, "session_id": session_id, "copernicus": False},
            config={"configurable": {"thread_id": session_id}},
        )

        analysis = _build_legacy_response(final_state, session_id, adresse, form_data)
        set_analysis(session_id, analysis)

        return {"status": "ok", "session_id": session_id, "analysis": analysis}

    except Exception as e:
        logger.exception("Erreur legacy analyze")
        analysis = _build_fallback(session_id, adresse, str(e))
        set_analysis(session_id, analysis)
        return {"status": "ok", "session_id": session_id, "analysis": analysis}


@router.post("/bank/analyze")
async def legacy_bank_analyze(req: LegacyAnalyzeRequest):
    """Route legacy : POST /api/bank/analyze (async avec polling)"""
    session_id = req.session_id or f"bank-session-{uuid.uuid4().hex[:12]}"
    form_data = req.client_form
    adresse = form_data.get("adresse", "")

    if not adresse:
        raise HTTPException(status_code=400, detail="L'adresse est obligatoire")

    set_analysis(session_id, {"status": "processing", "session_id": session_id})

    async def background_task():
        try:
            final_state = await diagnostic_graph.ainvoke(
                {"adresse": adresse, "formulaire": form_data, "copernicus": False},
                config={"configurable": {"thread_id": session_id}},
            )
            analysis = _build_legacy_response(final_state, session_id, adresse, form_data)
            analysis["status"] = "completed"
            set_analysis(session_id, analysis)
        except Exception as e:
            set_analysis(session_id, {"status": "error", "session_id": session_id, "error": str(e)})

    asyncio.create_task(background_task())

    return {"status": "ok", "session_id": session_id, "status_analysis": "processing"}


@router.get("/analysis/{session_id}")
async def legacy_get_analysis(session_id: str):
    """Route legacy : GET /api/analysis/{session_id} (polling)
    Lit depuis le store SQLite (persistant après redémarrage).
    """
    analysis = get_analysis(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")
    return analysis


# ─── Route Dashboard (données simulées pour l'UI) ─────────────────

@router.get("/dashboard/{session_id}")
async def legacy_dashboard(session_id: str):
    """Dashboard legacy - retourne les données du diagnostic stocké ou des données neutres"""
    analysis = get_analysis(session_id)
    if analysis and analysis.get("status") == "completed":
        return _dashboard_from_analysis(analysis)
    # Données neutres si pas d'analyse complète
    return {
        "session_id": session_id,
        "score_global": 0,
        "niveau_risque": "non_evalue",
        "adresse": "Analyse en cours...",
        "coordonnees": {"lat": 0, "lng": 0},
        "scores_par_alea": {},
        "risques_dominants": [],
        "projections_2050": {},
        "recommandations": [],
        "synthese": "Analyse en cours de traitement...",
    }


# ─── Route Recommandations ─────────────────────────────────────────

@router.get("/recommendations/{session_id}")
async def legacy_recommendations(session_id: str):
    analysis = get_analysis(session_id)
    if not analysis or analysis.get("status") != "completed":
        return {"session_id": session_id, "recommandations": []}
    zones = analysis.get("recommandations", {}).get("zones", {})
    recos = []
    count = 0
    for zone_name, zone in zones.items():
        for r in zone.get("recommandations", []):
            count += 1
            recos.append({
                "priorite": count,
                "titre": r.get("travaux", r.get("mesure", f"Travaux {zone_name}")),
                "description": r.get("explication", r.get("justification", "")),
                "cout_estime_bas": _parse_cost(r.get("cout_estime", "0")),
                "cout_estime_haut": _parse_cost(r.get("cout_estime", "0")) * 2,
                "gain_resilience_pct": r.get("gain_resilience", 0),
                "aleas_adresses": [zone.get("alea_principal", "")],
            })
    return {
        "session_id": session_id,
        "recommandations": recos,
        "cout_total_bas": sum(r["cout_estime_bas"] for r in recos),
        "cout_total_haut": sum(r["cout_estime_haut"] for r in recos),
        "gain_moyen": round(sum(r["gain_resilience_pct"] for r in recos) / max(len(recos), 1), 1),
    }


# ─── Route Chat ────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    historique: list[dict] = []


# ─── Normalisation des données ─────────────────────────────────────

def _normaliser_analyse(analysis: dict) -> dict:
    """Normalise les données d'analyse pour le chat.

    Le format produit par le graphe LangGraph (backend/app/agent_graph/)
    diffère parfois de ce que legacy_chat attend. Cette fonction
    harmonise les structures.

    Problèmes connus :
    - scores_par_alea peut être des entiers plats ({"inondation": 15})
      au lieu de dicts ({"inondation": {"score": 15, "niveau": "faible"}})
    - zones peut être absent ou dans digital_twin en plus de recommandations
    - bank_decision peut être stocké sous "bank_decision" au lieu de "decision_bancaire"
    """
    if not analysis:
        return analysis

    analysis = {k: v for k, v in analysis.items() if v is not None}

    # 1. Normaliser scores_par_alea (entiers plats → dicts avec score + niveau)
    for score_dict_path in [
        ["analyse_risques", "scores_par_alea"],
        ["recommandations", "scores_par_alea"],
    ]:
        parent = analysis
        for key in score_dict_path[:-1]:
            parent = parent.get(key, {})
            if not isinstance(parent, dict):
                break
        else:
            scores = parent.get(score_dict_path[-1], {})
            if isinstance(scores, dict):
                for key, val in list(scores.items()):
                    if isinstance(val, (int, float)):
                        s = int(val)
                        scores[key] = {
                            "score": s,
                            "niveau": "critique" if s >= 70 else "eleve" if s >= 55 else "modere" if s >= 35 else "faible",
                            "label": key.capitalize(),
                        }

    # 2. Fusionner les zones depuis digital_twin si recommandations.zones est vide
    digital_twin = analysis.get("digital_twin", {}) or {}
    if isinstance(digital_twin, dict):
        twin_zones = digital_twin.get("zones", {}) or {}
        if twin_zones and not analysis.get("recommandations", {}).get("zones"):
            if "recommandations" not in analysis:
                analysis["recommandations"] = {}
            analysis["recommandations"]["zones"] = twin_zones

        # Fusionner la projection 2050 du digital_twin
        twin_proj = digital_twin.get("projection_2050", {}) or {}
        if twin_proj and not analysis.get("recommandations", {}).get("projection_2050"):
            if "recommandations" not in analysis:
                analysis["recommandations"] = {}
            analysis["recommandations"]["projection_2050"] = twin_proj

    # 3. Normaliser bank_decision → decision_bancaire
    bk = analysis.pop("bank_decision", None) or {}
    if bk and not analysis.get("decision_bancaire"):
        analysis["decision_bancaire"] = bk

    # 4. S'assurer que resume existe avec au moins un score
    if "resume" not in analysis or not analysis.get("resume", {}).get("score_global"):
        score_global = 0
        if isinstance(digital_twin, dict):
            score_global = digital_twin.get("score_global", 0)
        if score_global == 0:
            zones = analysis.get("recommandations", {}).get("zones", {}) or {}
            scores_list = [z.get("risque", 0) for z in zones.values() if isinstance(z, dict) and z.get("risque")]
            if scores_list:
                score_global = round(sum(scores_list) / len(scores_list))
        niveau = "critique" if score_global >= 70 else "eleve" if score_global >= 55 else "modere" if score_global >= 35 else "faible"
        analysis["resume"] = {
            "score_global": score_global,
            "niveau_risque": niveau,
            "nb_recommandations": 0,
        }

    return analysis


@router.post("/chat/{session_id}")
async def legacy_chat(session_id: str, req: ChatRequest):
    """Chat enrichi - répond avec les VRAIES données d'analyse.

    Sources de donnees (par ordre de priorite) :
    1. get_analysis() → memoire + SQLite (persistant apres redemarrage)
    2. diagnostic_store (nouveau format, analyses POST /diagnostic)
    3. Donnees par defaut si aucune analyse trouvee

    La fonction utilise :
    - score_global, niveau_risque
    - scores par alea (inondation, rga, tempete, incendie)
    - zones du digital_twin
    - decision_bancaire (taux, valeur, garanties)
    - recommandations
    - projection 2050
    """
    # 1. Chercher dans le store persistant (memoire + SQLite)
    analysis = get_analysis(session_id) or {}
    # 2. Fallback vers le store diagnostic (format new-API)
    if not analysis.get("resume"):
        analysis = diagnostic_store.get(session_id, {}) or {}

    # 3. Normaliser les données pour gérer les différences de format
    analysis = _normaliser_analyse(analysis)

    # Extraire les donnees
    resume = analysis.get("resume", {}) or {}
    score = resume.get("score_global", 0) if isinstance(resume, dict) else 0
    niveau = resume.get("niveau_risque", "non_evalue") if isinstance(resume, dict) else "non_evalue"
    adresse = analysis.get("adresse", "votre bien")

    # Donnees enrichies (normalisees par _normaliser_analyse)
    zones = analysis.get("recommandations", {}).get("zones", {}) or \
            analysis.get("zones", {}) or {}
    scores_alea = analysis.get("analyse_risques", {}).get("scores_par_alea", {}) or {}
    bank = analysis.get("decision_bancaire", {}) or analysis.get("bank_decision", {}) or {}
    projection = analysis.get("recommandations", {}).get("projection_2050", {}) or \
                 analysis.get("projection_2050", {}) or \
                 analysis.get("digital_twin", {}).get("projection_2050", {}) or {}

    # Sante du bien
    form = analysis.get("formulaire_client", {}) or {}
    type_bien = form.get("type_bien", "")
    surface = form.get("surface", "")

    question_lower = req.question.lower()

    # ── Reponses contextualisees ─────────────────────────────────

    if "score" in question_lower or "risque" in question_lower or "eval" in question_lower:
        parts = [f"Le score de risque global pour **{adresse}** est de **{score}/100** ({niveau})."]

        # Ajouter les 3 principaux aleas (maintenant normalises en dicts)
        dominants = sorted(
            scores_alea.items(),
            key=lambda kv: kv[1]["score"] if isinstance(kv[1], dict) else 0,
            reverse=True
        )[:3]
        if dominants:
            aleas_str = "; ".join(
                f"{k} : {v['score']}/100 ({v['niveau']})"
                for k, v in dominants if isinstance(v, dict)
            )
            parts.append(f"Les principaux risques sont : {aleas_str}.")

        if score >= 60:
            parts.append("Le niveau de risque est significatif — des travaux de mitigation sont fortement recommandés.")
        elif score >= 30:
            parts.append("Le niveau de risque est modéré — un suivi régulier et quelques travaux préventifs suffisent.")
        else:
            parts.append("Le niveau de risque est faible — votre bien est peu exposé aux aléas climatiques.")

        reponse = " ".join(parts)

    elif "zone" in question_lower or "fondation" in question_lower or "toiture" in question_lower or "mur" in question_lower or "sous.sol" in question_lower or "sous-sol" in question_lower:
        if zones:
            parts = ["Voici le détail des zones de votre bien :"]
            for zone_name, zone in zones.items():
                if isinstance(zone, dict):
                    z_score = zone.get("risque", "?")
                    z_niveau = zone.get("niveau", "?")
                    z_alea = zone.get("alea_principal", "")
                    parts.append(f"  • **{zone_name}** : {z_score}/100 ({z_niveau}) — {z_alea}")
            reponse = "\n".join(parts)
        else:
            reponse = f"Les données détaillées des zones ne sont pas disponibles pour {adresse}. Consultez le jumeau numérique 3D pour une visualisation interactive."

    elif "cout" in question_lower or "coût" in question_lower or "prix" in question_lower or "combien" in question_lower or "travaux" in question_lower:
        # Extraire les recommandations
        recos = []
        for zone_name, zone in zones.items():
            if isinstance(zone, dict):
                for r in zone.get("recommandations", []):
                    if isinstance(r, dict):
                        recos.append(r)
        if recos:
            total_bas = 0
            total_haut = 0
            lignes = []
            for r in recos[:5]:
                cout = r.get("cout_estime", "0").replace(" ", "").replace("€", "").replace("/an", "")
                try:
                    cout_val = int(cout) if cout.isdigit() else 0
                except ValueError:
                    cout_val = 0
                total_bas += cout_val
                total_haut += cout_val * 2
                lignes.append(f"  • {r.get('travaux', 'Travaux')} : environ {cout_val:,} €")

            reponse = (
                f"Le coût total estimé des travaux pour **{adresse}** se situe entre "
                f"**{total_bas:,} €** et **{total_haut:,} €**.\n"
                f"Détail des travaux :\n" + "\n".join(lignes) + "\n\n"
                "Des aides financières peuvent être mobilisées : MaPrimeRénov', Anah, Fonds Barnier, CEE."
            )
        else:
            reponse = f"Aucune recommandation de travaux n'est disponible pour {adresse} pour le moment."

    elif "taux" in question_lower or "credit" in question_lower or "pret" in question_lower or "banque" in question_lower or "finance" in question_lower or "financier" in question_lower:
        if bank and bank.get("valeur_marche"):
            taux = bank.get("taux_propose", "?")
            valeur = bank.get("valeur_marche", 0)
            valeur_ajustee = bank.get("valeur_ajustee", 0)
            score_bancaire = bank.get("score_risque_bancaire", "?")
            majo = bank.get("majoration_taux", 0)
            decote = bank.get("decote_pct", 0)
            niveau_bancaire = bank.get("niveau_risque_bancaire", bank.get("niveau_risque_global", "?"))

            reponse = (
                f"**Analyse financière** pour {adresse} :\n"
                f"  • Valeur de marché : **{valeur:,} €**\n"
                f"  • Valeur ajustée (décote {decote}%) : **{valeur_ajustee:,} €**\n"
                f"  • Taux proposé : **{taux}%** (majoration de {majo}% incluse)\n"
                f"  • Score de risque bancaire : {score_bancaire}/100 ({niveau_bancaire})\n"
                f"Le taux tient compte du profil de risque climatique du bien. "
                f"Un score faible permet de bénéficier de conditions avantageuses."
            )
        elif bank and bank.get("score_risque_bancaire"):
            # Bank decision exists but maybe no market value
            taux = bank.get("taux_propose", "?")
            score_bancaire = bank.get("score_risque_bancaire", "?")
            niveau_bancaire = bank.get("niveau_risque_bancaire", bank.get("niveau_risque_global", "?"))
            valeur = bank.get("valeur_marche", bank.get("valeur_ajustee", 0))
            reponse = (
                f"**Analyse financière** pour {adresse} :\n"
                f"  • Valeur estimée : **{valeur:,} €**\n"
                f"  • Taux proposé : **{taux}%**\n"
                f"  • Score de risque bancaire : {score_bancaire}/100 ({niveau_bancaire})\n"
                f"Le taux tient compte du profil de risque climatique du bien."
            )
        else:
            reponse = f"L'analyse financière n'a pas été réalisée pour {adresse}. Lancez une analyse en mode bancaire pour obtenir ces informations."

    elif "priorit" in question_lower or "urgence" in question_lower:
        zones_triees = sorted(
            zones.items(),
            key=lambda kv: kv[1].get("risque", 0) if isinstance(kv[1], dict) else 0,
            reverse=True
        )
        if zones_triees:
            parts = ["**Priorités par zone** (de la plus critique à la moins critique) :"]
            for i, (zn, zv) in enumerate(zones_triees, 1):
                if isinstance(zv, dict):
                    parts.append(f"  {i}. **{zn}** : {zv.get('risque', '?')}/100 ({zv.get('niveau', '?')})")
            parts.append("Concentrez-vous d'abord sur les zones en rouge/orange dans le jumeau numérique.")
            reponse = "\n".join(parts)
        else:
            reponse = "Les données de priorité ne sont pas disponibles."

    elif "2050" in question_lower or "projection" in question_lower or "futur" in question_lower:
        if projection:
            score_futur = projection.get("score_global", score) if isinstance(projection, dict) else score
            aggravation = score_futur - score if isinstance(score_futur, (int, float)) and isinstance(score, (int, float)) else 0
            reponse = (
                f"**Projection 2050** pour {adresse} :\n"
                f"  • Score actuel : **{score}/100**\n"
                f"  • Score projeté 2050 : **{score_futur}/100**\n"
                f"  • Aggravation estimée : **+{max(0, aggravation)} points**\n\n"
                f"Les travaux réalisés aujourd'hui vous protégeront mieux demain. "
                f"Utilisez le bouton '2050' dans le jumeau 3D pour visualiser l'évolution."
            )
        else:
            reponse = f"Les données de projection 2050 ne sont pas disponibles pour {adresse}."

    else:
        reponse = (
            f"**Bienvenue !** Pour **{adresse}** (score global : {score}/100, niveau {niveau}).\n\n"
            f"Je peux vous renseigner sur :\n"
            f"  • Le **score de risque** et les principaux aléas\n"
            f"  • Les **zones critiques** (fondations, toiture, sous-sol...)\n"
            f"  • Le **coût des travaux** recommandés\n"
            f"  • Les **taux bancaires** et l'analyse financière\n"
            f"  • Les **priorités d'intervention**\n"
            f"  • La **projection 2050** du changement climatique\n\n"
            f"Que souhaitez-vous savoir ?"
        )

    return {"reponse": reponse, "session_id": session_id}


# ─── Route Test de vulnérabilité ───────────────────────────────────

class VulnTestRequest(BaseModel):
    zone_name: str
    lat: float | None = None
    lon: float | None = None
    zone_data: dict = {}


@router.post("/jumeau/vulnerability-test")
async def legacy_vuln_test(req: VulnTestRequest):
    """Test de vulnérabilité rapide pour une zone."""
    score = req.zone_data.get("risque", 50)
    niveau = req.zone_data.get("niveau", "modere")

    if score >= 70:
        verdict = "DANGER"
        action = "Intervention urgente requise"
    elif score >= 55:
        verdict = "RISQUE_ELEVE"
        action = "Travaux de mitigation recommandés dans les 12 mois"
    elif score >= 35:
        verdict = "VIGILANCE"
        action = "Travaux de mitigation recommandés dans les 24 mois"
    else:
        verdict = "ACCEPTABLE"
        action = "Aucune action urgente, suivi périodique conseillé"

    return {
        "verdict": verdict,
        "score_risque": score,
        "scenario": f"Zone {req.zone_name} — niveau {niveau} ({score}/100)",
        "resume": f"Analyse rapide de la zone '{req.zone_name}'. Score de risque : {score}/100. {action}.",
        "score_avant": score,
        "score_apres_travaux": max(0, score - 20),
        "points_de_vigilance": [
            f"Le niveau actuel de la zone {req.zone_name} est jugé {niveau}",
            "Une étude plus approfondie est recommandée",
        ],
    }


# ─── Route PDF Report (GET) ──────────────────────────────────────────

@router.get("/bank/report/{session_id}/pdf")
async def legacy_report_pdf(session_id: str):
    """Génère et télécharge le rapport d'analyse complet au format PDF.
    Utilise reportlab pour un rendu professionnel avec tableaux et couleurs.
    """
    analysis = get_analysis(session_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analyse introuvable")

    db = analysis.get("decision_bancaire", {}) or {}
    if not db:
        raise HTTPException(status_code=404, detail="Décision bancaire introuvable")

    # Enrichir avec les données de marché DVF
    stats_marche = None
    try:
        adr = analysis.get("adresse", "")
        evo = dvf_service.get_price_evolution(adr)
        current = dvf_service.query_market_value(adr)
        if evo.get("evolution"):
            stats_marche = {
                "prix_m2_actuel": current.get("prix_m2_median"),
                "prix_m2_commune": evo["evolution"][-1]["prix_m2_median"] if evo["evolution"] else None,
                "nb_transactions": current.get("nb_transactions", 0),
                "tendance": evo.get("tendance", "stable"),
            }
    except Exception as e:
        logger.warning(f"Impossible de récupérer les stats marché pour le PDF : {e}")

    pdf_buffer = generate_bank_report_pdf(
        session_id=session_id,
        adresse=analysis.get("adresse", "N/A"),
        decision_bancaire=db,
        stats_marche=stats_marche,
    )

    return StreamingResponse(
        content=pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=rapport-credit-{session_id}.pdf",
            "Content-Type": "application/pdf",
        }
    )


# ─── Route Market Trends ────────────────────────────────────────────

class MarketTrendsRequest(BaseModel):
    """Requête pour obtenir l'évolution des prix DVF pour une adresse."""
    adresse: str
    type_bien: str = "Maison"
    surface: float = 100


@router.post("/bank/market-trends")
async def legacy_market_trends(req: MarketTrendsRequest):
    """Retourne l'évolution du prix au m² + comparaison de marché (données DVF réelles)."""
    evolution = dvf_service.get_price_evolution(req.adresse, req.type_bien)
    current = dvf_service.query_market_value(req.adresse, req.surface, req.type_bien)

    # Données de comparaison : tous types confondus dans la commune
    try:
        all_types = dvf_service.get_price_evolution(req.adresse, "Maison")
        if all_types.get("evolution") and len(all_types["evolution"]) > 0:
            annee_courante = all_types["evolution"][-1]
            prix_m2_commune_tous = annee_courante["prix_m2_median"]
            tx_total = sum(d["nb_transactions"] for d in all_types["evolution"])
        else:
            prix_m2_commune_tous = None
            tx_total = 0

        # Écart entre le type du bien et la moyenne commune
        pm2_bien = current.get("prix_m2_median")
        ecart_pct = None
        if pm2_bien and prix_m2_commune_tous and prix_m2_commune_tous > 0:
            ecart_pct = round((pm2_bien - prix_m2_commune_tous) / prix_m2_commune_tous * 100, 1)
    except Exception:
        prix_m2_commune_tous = None
        tx_total = 0
        ecart_pct = None

    return {
        "evolution": evolution.get("evolution", []),
        "source": evolution.get("source", ""),
        "tendance": evolution.get("tendance", "stable"),
        "valeur_actuelle": current.get("valeur_estimee"),
        "prix_m2_bien": current.get("prix_m2_median"),
        "prix_m2_commune": prix_m2_commune_tous,
        "ecart_vs_commune_pct": ecart_pct,
        "nb_transactions": current.get("nb_transactions", 0),
        "volume_total_transactions": tx_total,
        "indice_confiance_dvf": current.get("indice_confiance", 0),
    }


# ─── Route PDF Report (POST) ─────────────────────────────────────────

class PdfReportRequest(BaseModel):
    """Requête pour générer un PDF à partir des données d'analyse fournies par le client.
    Alternative au endpoint GET /api/bank/report/{session_id}/pdf qui nécessite
    que l'analyse soit stockée côté serveur (perdue si le backend redémarre).
    """
    session_id: str
    adresse: str = ""
    decision_bancaire: dict[str, Any]


@router.post("/bank/report/pdf")
async def legacy_report_pdf_post(req: PdfReportRequest):
    """Génère et télécharge le rapport PDF à partir des données fournies directement.
    Version POST : plus robuste car elle ne dépend pas du stockage serveur.
    Le frontend envoie les données d'analyse récupérées depuis le sessionStorage.
    """
    db = req.decision_bancaire or {}
    if not db:
        raise HTTPException(status_code=400, detail="Données d'analyse manquantes")

    stats_marche = None
    try:
        adr = req.adresse or ""
        evo = dvf_service.get_price_evolution(adr)
        current = dvf_service.query_market_value(adr)
        if evo.get("evolution"):
            stats_marche = {
                "prix_m2_actuel": current.get("prix_m2_median"),
                "prix_m2_commune": evo["evolution"][-1]["prix_m2_median"] if evo["evolution"] else None,
                "nb_transactions": current.get("nb_transactions", 0),
                "tendance": evo.get("tendance", "stable"),
            }
    except Exception as e:
        logger.warning(f"Impossible de récupérer les stats marché pour le PDF : {e}")

    pdf_buffer = generate_bank_report_pdf(
        session_id=req.session_id,
        adresse=req.adresse or "N/A",
        decision_bancaire=db,
        stats_marche=stats_marche,
    )

    return StreamingResponse(
        content=pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=rapport-credit-{req.session_id}.pdf",
            "Content-Type": "application/pdf",
        }
    )


# ─── Helpers ───────────────────────────────────────────────────────

def _build_legacy_response(final_state: dict, session_id: str, adresse: str, form_data: dict) -> dict:
    dt = final_state.get("digital_twin", {})
    bank = final_state.get("bank_decision", {})
    rs = final_state.get("risk_scores", {})
    bg = final_state.get("building_data", {})
    zones = dt.get("zones", {})
    proj = dt.get("projection_2050", {})
    score = dt.get("score_global", 0)
    niveau = "critique" if score >= 70 else "eleve" if score >= 55 else "modere" if score >= 35 else "faible"
    nb_recos = sum(len(z.get("recommandations", [])) for z in zones.values())

    return {
        "session_id": session_id,
        "adresse": adresse,
        "status": "completed",
        "date_analyse": datetime.now(timezone.utc).isoformat(),
        "coordonnees": {"latitude": bg.get("adresse", {}).get("lat", 0), "longitude": bg.get("adresse", {}).get("lon", 0)},
        "formulaire_client": {
            "adresse": form_data.get("adresse", ""),
            "type_bien": form_data.get("type_bien", ""),
            "surface": form_data.get("surface", 0),
            "nb_etages": form_data.get("nb_etages", 1),
            "annee_construction": form_data.get("annee_construction", 2000),
            "type_structure": form_data.get("type_structure", ""),
            "type_toiture": form_data.get("type_toiture", ""),
            "presence_sous_sol": form_data.get("presence_sous_sol", False),
            "presence_cave": form_data.get("presence_cave", False),
        },
        "analyse_risques": {
            "score": {"global": score, "weights": {}, "perils": {}},
            "scores_par_alea": _extract_alea_scores(zones),
            "profil_bien": {"disponible": True},
        },
        "recommandations": {
            "zones": zones,
            "projection_2050": proj,
            "synthese_financiere": {"cout_brut_total": "0 EUR", "aides_mobilisables": "0 EUR", "reste_a_charge_net": "0 EUR"},
            "nb_recommandations": nb_recos,
        },
        "decision_bancaire": bank,
        "resume": {
            "score_global": score,
            "niveau_risque": niveau,
            "nb_recommandations": nb_recos,
            "cout_total_travaux": "0 EUR",
            "aides_mobilisables": "0 EUR",
            "reste_a_charge_net": "0 EUR",
        },
        "donnees_api": {"code_insee": bg.get("adresse", {}).get("citycode", ""), "georisques": bg.get("georisques", {})},
        "_performance": {"mode": "typhoon_v2"},
    }


def _extract_alea_scores(zones: dict) -> dict:
    mapping = {"inondation": "sous_sol", "rga": "fondations", "tempete": "murs_nord", "incendie": "toiture"}
    scores = {}
    for alea, zone in mapping.items():
        z = zones.get(zone, {})
        scores[alea] = {"score": z.get("risque", 0), "niveau": z.get("niveau", "faible"), "label": z.get("alea_principal", alea)}
    return scores


def _parse_cost(cost_str: str) -> int:
    try:
        return int("".join(c for c in cost_str if c.isdigit()))
    except (ValueError, TypeError):
        return 0


def _build_fallback(session_id: str, adresse: str, error: str) -> dict:
    return {
        "session_id": session_id,
        "adresse": adresse,
        "status": "completed",
        "date_analyse": datetime.now(timezone.utc).isoformat(),
        "coordonnees": {"latitude": 0, "longitude": 0},
        "formulaire_client": {"adresse": adresse},
        "analyse_risques": {"score": {"global": 0}, "scores_par_alea": {}, "profil_bien": {"disponible": False}},
        "recommandations": {"zones": {}, "projection_2050": {}, "synthese_financiere": {}, "nb_recommandations": 0},
        "decision_bancaire": {},
        "resume": {"score_global": 0, "niveau_risque": "non_evalue", "nb_recommandations": 0, "cout_total_travaux": "0 EUR", "aides_mobilisables": "0 EUR", "reste_a_charge_net": "0 EUR"},
        "donnees_api": {"code_insee": ""},
        "erreur": error,
    }


def _dashboard_from_analysis(analysis: dict) -> dict:
    zone_scores = analysis.get("analyse_risques", {}).get("scores_par_alea", {})
    return {
        "session_id": analysis.get("session_id", ""),
        "score_global": analysis.get("resume", {}).get("score_global", 0),
        "niveau_risque": analysis.get("resume", {}).get("niveau_risque", "non_evalue"),
        "adresse": analysis.get("adresse", ""),
        "coordonnees": analysis.get("coordonnees", {"lat": 0, "lng": 0}),
        "scores_par_alea": zone_scores,
        "risques_dominants": sorted(zone_scores.keys(), key=lambda k: zone_scores[k]["score"], reverse=True)[:3],
        "projections_2050": {k: v.get("score", 0) for k, v in zone_scores.items()},
        "recommandations": analysis.get("recommandations", {}).get("zones", {}),
        "synthese": f"Diagnostic climatique terminé. Score global : {analysis.get('resume', {}).get('score_global', 0)}/100.",
    }
