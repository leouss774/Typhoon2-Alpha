"""
pdf_generator.py
-----------------
Génère un rapport d'analyse de risque crédit au format PDF 
via reportlab — rendu professionnel type "rapport bancaire".
"""

from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)

logger = logging.getLogger(__name__)

# ── Couleurs du thème bancaire ───────────────────────────────────────────────
TEAL = "#0f766e"
TEAL_DARK = "#0d5e57"
TEAL_LIGHT = "#14b8a6"
TEAL_BG = "#eef9f8"
RED = "#ef4444"
RED_LIGHT = "#fef2f2"
ORANGE = "#f97316"
ORANGE_LIGHT = "#fff7ed"
YELLOW = "#eab308"
YELLOW_LIGHT = "#fefce8"
GREEN = "#22c55e"
GREEN_LIGHT = "#f0fdf4"
GRAY = "#64748b"
GRAY_LIGHT = "#f1f5f9"
GRAY_MED = "#cbd5e1"
DARK = "#1e293b"
WHITE = "#ffffff"

RISK_COLORS = {
    "faible": GREEN, "modere": YELLOW, "eleve": ORANGE, "critique": RED,
    "Faible": GREEN, "Modéré": YELLOW, "Élevé": RED,
}


def _color_for_score(score: int) -> str:
    if score >= 60: return RED
    if score >= 35: return YELLOW
    return GREEN


def _build_styles():
    """Construit et retourne un dictionnaire de styles PDF."""
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("TitleBank", fontName="Helvetica-Bold", fontSize=18,
                          textColor=colors.HexColor(TEAL), spaceAfter=3 * mm, alignment=TA_CENTER))
    ss.add(ParagraphStyle("Subtitle", fontName="Helvetica", fontSize=9,
                          textColor=colors.HexColor(GRAY), alignment=TA_CENTER, spaceAfter=6 * mm))
    ss.add(ParagraphStyle("SectionTitle", fontName="Helvetica-Bold", fontSize=12,
                          textColor=colors.HexColor(TEAL_DARK), spaceBefore=5 * mm, spaceAfter=3 * mm))
    ss.add(ParagraphStyle("SectionTitleRed", fontName="Helvetica-Bold", fontSize=12,
                          textColor=colors.HexColor(RED), spaceBefore=5 * mm, spaceAfter=3 * mm))
    ss.add(ParagraphStyle("SectionTitleOrange", fontName="Helvetica-Bold", fontSize=12,
                          textColor=colors.HexColor(ORANGE), spaceBefore=5 * mm, spaceAfter=3 * mm))
    ss.add(ParagraphStyle("Body", fontName="Helvetica", fontSize=9, leading=13,
                          textColor=colors.HexColor(DARK), alignment=TA_JUSTIFY))
    ss.add(ParagraphStyle("BodySmall", fontName="Helvetica", fontSize=8, leading=11,
                          textColor=colors.HexColor(GRAY)))
    ss.add(ParagraphStyle("RiskName", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(DARK)))
    ss.add(ParagraphStyle("ScoreValue", fontName="Helvetica-Bold", fontSize=16,
                          textColor=colors.HexColor(TEAL), alignment=TA_CENTER))
    ss.add(ParagraphStyle("ScoreLabel", fontName="Helvetica", fontSize=7, textColor=colors.HexColor(GRAY), alignment=TA_CENTER))
    ss.add(ParagraphStyle("AvisText", fontName="Helvetica-Oblique", fontSize=9, leading=13,
                          textColor=colors.HexColor(DARK), alignment=TA_JUSTIFY))
    ss.add(ParagraphStyle("Footer", fontName="Helvetica", fontSize=7, textColor=colors.HexColor(GRAY), alignment=TA_CENTER))
    ss.add(ParagraphStyle("HardStop", fontName="Helvetica-Bold", fontSize=9,
                          textColor=colors.HexColor(RED), alignment=TA_LEFT))
    ss.add(ParagraphStyle("Positive", fontName="Helvetica", fontSize=9, textColor=colors.HexColor(GREEN)))
    ss.add(ParagraphStyle("Warning", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(ORANGE)))
    return ss


def _make_table(data, col_widths, header_bg=TEAL_DARK):
    """Helper: crée un tableau stylisé avec en-tête."""
    t = Table(data, colWidths=col_widths)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def _section_header(text, style):
    """Helper: retourne le titre de section + séparateur."""
    return [
        Paragraph(text, style),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=3 * mm),
    ]


def _fmt_eur(val: float) -> str:
    """Formate un montant en euros: 400660 → '400 660 €'."""
    if not val:
        return "0 €"
    return f"{val:,.0f} €".replace(",", " ")


def generate_bank_report_pdf(
    session_id: str,
    adresse: str,
    decision_bancaire: dict[str, Any],
    stats_marche: dict[str, Any] | None = None,
) -> io.BytesIO:
    """
    Génère un PDF professionnel du rapport d'analyse de risque crédit.

    Args:
        session_id: Identifiant de session
        adresse: Adresse du bien
        decision_bancaire: Dictionnaire complet BankDecision
        stats_marche: Statistiques de marché DVF optionnelles (évolution prix/m²)

    Returns:
        BytesIO contenant le PDF
    """
    db = decision_bancaire
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=1.8 * cm, bottomMargin=1.8 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    s = _build_styles()
    el: list = []

    # ════════════════════════════════════════════════════════════════════════
    # EN-TÊTE
    # ════════════════════════════════════════════════════════════════════════
    el.append(Paragraph("RAPPORT D'ANALYSE DE RISQUE CRÉDIT", s["TitleBank"]))
    el.append(Paragraph("Outil d'aide à la décision — Aucune décision automatique", s["Subtitle"]))
    el.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor(TEAL_LIGHT),
                         spaceAfter=3 * mm, spaceBefore=1 * mm))

    header_data = [
        [Paragraph("<b>Bien</b>", s["BodySmall"]), Paragraph(adresse, s["Body"])],
        [Paragraph("<b>Session</b>", s["BodySmall"]), Paragraph(session_id, s["Body"])],
        [Paragraph("<b>Date</b>", s["BodySmall"]), Paragraph(datetime.now().strftime("%d/%m/%Y à %H:%M"), s["Body"])],
        [Paragraph("<b>Type</b>", s["BodySmall"]), Paragraph("Analyse crédit bancaire — Résilience climatique", s["Body"])],
    ]
    el.append(_make_table(header_data, [3.5 * cm, 11.5 * cm]))
    el.append(Spacer(1, 4 * mm))

    # ════════════════════════════════════════════════════════════════════════
    # FICHE DÉCISION — RÉCAPITULATIF (NOUVEAU !)
    # ════════════════════════════════════════════════════════════════════════
    score_bancaire = db.get("score_risque_bancaire", 0)
    niveau = db.get("niveau_risque_global", "N/A")
    v_marche = db.get("valeur_marche", 0)
    v_ajustee = db.get("valeur_ajustee", 0)
    taux = db.get("taux_propose", 0)
    confiance = db.get("indice_confiance", 0)
    hard_stops = db.get("hard_stops", [])

    el.append(Paragraph("📋 FICHE D'AIDE À LA DÉCISION", s["SectionTitle"]))
    el.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=3 * mm))

    # Ligne 1: score + valeur + taux
    fiche_l1 = [
        [Paragraph(f"{score_bancaire}/100", ParagraphStyle("FS", fontName="Helvetica-Bold", fontSize=20,
                    textColor=colors.HexColor(_color_for_score(score_bancaire)), alignment=TA_CENTER)),
         Paragraph(f"{_fmt_eur(v_marche)}", ParagraphStyle("FV", fontName="Helvetica-Bold", fontSize=16,
                    textColor=colors.HexColor(TEAL), alignment=TA_CENTER)),
         Paragraph(f"{taux:.2f}%" if taux else "N/A", ParagraphStyle("FT", fontName="Helvetica-Bold", fontSize=16,
                    textColor=colors.HexColor(TEAL), alignment=TA_CENTER)),
         Paragraph(f"{_fmt_eur(v_ajustee)}", ParagraphStyle("FG", fontName="Helvetica-Bold", fontSize=14,
                    textColor=colors.HexColor(TEAL), alignment=TA_CENTER)),
        ],
        [Paragraph("Score bancaire", s["ScoreLabel"]),
         Paragraph("Valeur DVF", s["ScoreLabel"]),
         Paragraph("Taux proposé", s["ScoreLabel"]),
         Paragraph("Garantie finale", s["ScoreLabel"]),
        ],
    ]
    # Couleur de fond pour la ligne des valeurs
    fiche_t = Table(fiche_l1, colWidths=[3.5 * cm, 4 * cm, 3.5 * cm, 4 * cm])
    fiche_t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TEAL_BG)),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor(GRAY_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(TEAL_LIGHT)),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5 * mm),
    ]))
    el.append(fiche_t)

    # Ligne 2: niveau + confiance + interprétation
    confiance_color = GREEN if confiance >= 80 else (YELLOW if confiance >= 50 else RED)
    el.append(Spacer(1, 2 * mm))
    fiche_l2_data = [
        [Paragraph(f"<b>Niveau de risque :</b> <font color='{_color_for_score(score_bancaire)}'>{niveau}</font>", s["Body"]),
         Paragraph(f"<b>Confiance :</b> <font color='{confiance_color}'>{confiance}%</font>", s["Body"]),
         Paragraph(f"<b>Interprétation :</b> {_interpreter_score(score_bancaire)}", s["Body"]),
        ],
    ]
    el.append(_make_table(fiche_l2_data, [5.5 * cm, 3.5 * cm, 6 * cm], TEAL_DARK))

    # Hard Stops — alerte rouge si présents
    if hard_stops and len(hard_stops) > 0:
        el.append(Spacer(1, 2 * mm))
        hs_bg = TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(RED_LIGHT)),
                            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(RED))])
        hs_data = [[Paragraph(f"🚫 <b>POINTS BLOQUANTS DÉTECTÉS ({len(hard_stops)})</b>",
                              ParagraphStyle("HSH", fontName="Helvetica-Bold", fontSize=10,
                                             textColor=colors.HexColor(RED), alignment=TA_LEFT))]]
        for h in hard_stops:
            hs_data.append([Paragraph(f"• {h}", s["HardStop"])])
        hs_t = Table(hs_data, colWidths=[14 * cm])
        hs_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(RED_LIGHT)),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor(RED)),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor(RED)),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        el.append(hs_t)

    el.append(Spacer(1, 4 * mm))

    # ════════════════════════════════════════════════════════════════════════
    # 1. SCORE DE RISQUE
    # ════════════════════════════════════════════════════════════════════════
    score_climatique = db.get("score_climatique", 0)
    esg = db.get("impact_esg", "N/A")

    el.extend(_section_header("1. 📊 Score de risque du bien", s["SectionTitle"]))

    score_data = [
        [Paragraph(f"{score_bancaire}<br/><font size='7' color='{GRAY}'>/100</font>", s["ScoreValue"]),
         Paragraph(f"{score_climatique}<br/><font size='7' color='{GRAY}'>/100</font>", s["ScoreValue"]),
         Paragraph(esg, ParagraphStyle("ESG", fontName="Helvetica-Bold", fontSize=9,
                   textColor=colors.HexColor(GREEN), alignment=TA_CENTER)),
        ],
        [Paragraph("Score bancaire", s["ScoreLabel"]),
         Paragraph("Score climatique", s["ScoreLabel"]),
         Paragraph("Impact ESG", s["ScoreLabel"]),
        ],
        [Paragraph(f"Niveau : <b>{niveau}</b>",
                   ParagraphStyle("Niv", fontName="Helvetica", fontSize=8,
                   textColor=colors.HexColor(_color_for_score(score_bancaire)), alignment=TA_CENTER)),
         Paragraph("Source : Géorisques (BRGM)", s["BodySmall"]),
         Paragraph("Outil d'aide à la décision", s["BodySmall"]),
        ],
    ]
    st = Table(score_data, colWidths=[5 * cm, 5 * cm, 5 * cm])
    st.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor(GRAY_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    el.append(st)
    el.append(Spacer(1, 2 * mm))
    el.append(Paragraph(
        f"Indice de confiance des données : <b><font color='{confiance_color}'>{confiance}%</font></b> — "
        f"Validation croisée BAN / ADEME / DVF / Géorisques", s["Body"]))
    el.append(Paragraph(f"Interprétation : {_interpreter_score(score_bancaire)}", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # 2. RISQUES IDENTIFIÉS
    # ════════════════════════════════════════════════════════════════════════
    risques = db.get("risques_identifies", [])
    el.extend(_section_header("2. ⚠️ Principaux risques identifiés", s["SectionTitleRed"]))

    if risques:
        rows = [[Paragraph("<b>Risque</b>", s["BodySmall"]),
                 Paragraph("<b>Score</b>", s["BodySmall"]),
                 Paragraph("<b>Niveau</b>", s["BodySmall"]),
                 Paragraph("<b>Zone impactée</b>", s["BodySmall"])]]
        for r in risques[:6]:
            c = RISK_COLORS.get(r.get("niveau", ""), GRAY)
            rows.append([
                Paragraph(r.get("nom", "N/A"), s["RiskName"]),
                Paragraph(f"{r.get('score', 0)}/100",
                          ParagraphStyle("SR", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(c))),
                Paragraph(r.get("niveau", "N/A"),
                          ParagraphStyle("Lv", fontName="Helvetica", fontSize=8, textColor=colors.HexColor(c))),
                Paragraph(r.get("zone_impactee", "N/A"), s["Body"]),
            ])
        el.append(_make_table(rows, [4.5 * cm, 2.5 * cm, 2.5 * cm, 5.5 * cm]))
    else:
        el.append(Paragraph("Aucun risque majeur identifié.", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # 3. VALEUR AJUSTÉE + COMPARAISON MARCHÉ (NOUVEAU !)
    # ════════════════════════════════════════════════════════════════════════
    decote = db.get("decote_pct", 0)
    source_val = db.get("source_valorisation", "N/A")

    el.extend(_section_header("3. 💰 Valeur ajustée du bien", s["SectionTitle"]))

    vd = [
        [Paragraph(_fmt_eur(v_marche), s["ScoreValue"]),
         Paragraph(f"-{decote}%",
                   ParagraphStyle("Dec", fontName="Helvetica-Bold", fontSize=16,
                   textColor=colors.HexColor(RED), alignment=TA_CENTER)),
         Paragraph(_fmt_eur(v_ajustee),
                   ParagraphStyle("FG", fontName="Helvetica-Bold", fontSize=16,
                   textColor=colors.HexColor(TEAL), alignment=TA_CENTER)),
        ],
        [Paragraph("Valeur de marché (DVF)", s["ScoreLabel"]),
         Paragraph("Décote risque climatique", s["ScoreLabel"]),
         Paragraph("Valeur de garantie finale", s["ScoreLabel"]),
        ],
    ]
    vt = Table(vd, colWidths=[5 * cm, 5 * cm, 5 * cm])
    vt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GRAY_LIGHT)),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
    ]))
    el.append(vt)
    el.append(Paragraph(f"Source : {source_val}", s["BodySmall"]))
    el.append(Paragraph(f"Calcul : Valeur retenue = {_fmt_eur(v_marche)} × (1 - {decote}%) = {_fmt_eur(v_ajustee)}",
                        s["BodySmall"]))

    # Comparaison marché (si données disponibles)
    if stats_marche:
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph("Comparaison de marché", ParagraphStyle("SubSection", fontName="Helvetica-Bold",
                            fontSize=10, textColor=colors.HexColor(TEAL_DARK), spaceBefore=3 * mm, spaceAfter=2 * mm)))
        prix_m2 = stats_marche.get("prix_m2_actuel")
        prix_m2_commune = stats_marche.get("prix_m2_commune")
        nb_tx = stats_marche.get("nb_transactions", 0)
        tendance = stats_marche.get("tendance", "N/A")

        cmp_data = [
            [Paragraph(f"<b>Prix/m² estimé</b>", s["BodySmall"]),
             Paragraph(f"<b>Prix/m² commune</b>", s["BodySmall"]),
             Paragraph(f"<b>Transactions</b>", s["BodySmall"]),
             Paragraph(f"<b>Tendance</b>", s["BodySmall"]),
            ],
            [Paragraph(f"{_fmt_eur(prix_m2)}/m²" if prix_m2 else "N/A", s["Body"]),
             Paragraph(f"{_fmt_eur(prix_m2_commune)}/m²" if prix_m2_commune else "N/A", s["Body"]),
             Paragraph(f"{nb_tx} ventes", s["Body"]),
             Paragraph(tendance, s["Body"]),
            ],
        ]
        el.append(_make_table(cmp_data, [3.5 * cm, 3.5 * cm, 3.5 * cm, 3.5 * cm], TEAL_DARK))

    # ════════════════════════════════════════════════════════════════════════
    # 4. GARANTIES ASSURANCE
    # ════════════════════════════════════════════════════════════════════════
    garanties = db.get("garanties_assurance", [])
    el.extend(_section_header("4. 🛡️ Garanties d'assurance recommandées", s["SectionTitle"]))

    if garanties:
        gar_rows = [[Paragraph("<b>Type</b>", s["BodySmall"]),
                     Paragraph("<b>Oblig.</b>", s["BodySmall"]),
                     Paragraph("<b>Détail</b>", s["BodySmall"])]]
        for g in garanties:
            gar_rows.append([
                Paragraph(g.get("type", "N/A"), s["RiskName"]),
                Paragraph("Oui" if g.get("obligatoire") else "Non",
                          ParagraphStyle("Ob", fontName="Helvetica-Bold", fontSize=8,
                          textColor=colors.HexColor(RED if g.get("obligatoire") else GRAY))),
                Paragraph(g.get("detail", ""), s["Body"]),
            ])
        el.append(_make_table(gar_rows, [4.5 * cm, 1.5 * cm, 9 * cm]))
    else:
        el.append(Paragraph("Aucune garantie recommandée.", s["Body"]))

    reco_garantie = db.get("recommandation_garantie", "")
    if reco_garantie:
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(f"🏛️ <b>Montage juridique recommandé :</b> {reco_garantie}", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # 5. PRÉVENTION
    # ════════════════════════════════════════════════════════════════════════
    recos = db.get("prevention_recommandations", [])
    cout_total = db.get("cout_total_prevention", "N/A")

    el.extend(_section_header("5. 🏗️ Recommandations de prévention", s["SectionTitle"]))

    if recos:
        pr_rows = [[Paragraph("<b>#</b>", s["BodySmall"]),
                    Paragraph("<b>Zone</b>", s["BodySmall"]),
                    Paragraph("<b>Travaux</b>", s["BodySmall"]),
                    Paragraph("<b>Coût</b>", s["BodySmall"]),
                    Paragraph("<b>Gain</b>", s["BodySmall"])]]
        for r in recos[:8]:
            pr_rows.append([
                Paragraph(str(r.get("priorite", "-")), s["Body"]),
                Paragraph(r.get("zone", ""), s["Body"]),
                Paragraph(r.get("travaux", ""), s["Body"]),
                Paragraph(r.get("cout_estime", ""), s["Body"]),
                Paragraph(f"+{r.get('gain_resilience', 0)}%", s["Body"]),
            ])
        el.append(_make_table(pr_rows, [1 * cm, 2 * cm, 6 * cm, 2.5 * cm, 1.5 * cm]))
        el.append(Spacer(1, 2 * mm))
        el.append(Paragraph(f"💰 Coût total estimé : <b>{cout_total}</b>", s["Body"]))
    else:
        el.append(Paragraph("Aucune recommandation de prévention spécifique.", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # 6. PROJECTION 2050
    # ════════════════════════════════════════════════════════════════════════
    proj = db.get("projection_risque") or {}
    el.extend(_section_header("6. 📈 Projection de l'évolution du risque", s["SectionTitleOrange"]))

    if proj:
        pj_data = [
            [Paragraph(f"{proj.get('score_actuel', 'N/A')}", s["ScoreValue"]),
             Paragraph(f"{proj.get('score_projete', 'N/A')}", s["ScoreValue"]),
             Paragraph(f"+{proj.get('aggravation', 0)} pts",
                       ParagraphStyle("Agg", fontName="Helvetica-Bold", fontSize=16,
                       textColor=colors.HexColor(RED), alignment=TA_CENTER)),
            ],
            [Paragraph("Score actuel", s["ScoreLabel"]),
             Paragraph("Projection 2050", s["ScoreLabel"]),
             Paragraph("Aggravation", s["ScoreLabel"]),
            ],
        ]
        pjt = Table(pj_data, colWidths=[5 * cm, 5 * cm, 5 * cm])
        pjt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(GRAY_LIGHT)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        el.append(pjt)
        scenario = proj.get("scenario", "")
        if scenario:
            el.append(Spacer(1, 2 * mm))
            el.append(Paragraph(f"📊 Scénario : <b>{scenario}</b>", s["Body"]))
        zones_proj = proj.get("zones_projetees", {})
        if zones_proj:
            zp_text = "Zones projetées : " + " | ".join(
                f"{z}: {zp.get('risque_projete', '?')}/100 ({zp.get('evolution', '?')})"
                for z, zp in zones_proj.items()
            )
            el.append(Paragraph(zp_text, s["BodySmall"]))
    else:
        el.append(Paragraph("Données de projection non disponibles.", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # [NOUVEAU] 7. SYNTHÈSE DÉCISIONNELLE (taux, mensualité, points)
    # ════════════════════════════════════════════════════════════════════════
    el.extend(_section_header("7. 💳 Synthèse décisionnelle du financement", s["SectionTitle"]))

    taux_propose = db.get("taux_propose", 0)
    majoration = db.get("majoration_taux", 0)
    exigences = db.get("exigences", [])
    points_forts = db.get("points_forts", [])
    points_faibles = db.get("points_faibles", [])

    # Tableau taux
    taux_rows = [
        [Paragraph("<b>Indicateur</b>", s["BodySmall"]),
         Paragraph("<b>Valeur</b>", s["BodySmall"]),
         Paragraph("<b>Détail</b>", s["BodySmall"])],
        [Paragraph("Taux de base", s["Body"]),
         Paragraph(f"{(taux_propose - majoration):.2f}%", s["Body"]),
         Paragraph("Taux directeur banque (20 ans)", s["BodySmall"])],
        [Paragraph("Majoration risque", s["Body"]),
         Paragraph(f"{majoration:+.2f}%",
                   ParagraphStyle("Majo", fontName="Helvetica-Bold", fontSize=9,
                   textColor=colors.HexColor(RED if majoration > 0 else GREEN))),
         Paragraph("Prime de risque climatique", s["BodySmall"])],
        [Paragraph("Taux proposé", s["RiskName"]),
         Paragraph(f"<b>{taux_propose:.2f}%</b>" if taux_propose else "<b>N/A</b>",
                   ParagraphStyle("TauxP", fontName="Helvetica-Bold", fontSize=10,
                   textColor=colors.HexColor(TEAL))),
         Paragraph("Tout compris", s["BodySmall"])],
    ]
    # Mensualité estimée
    if taux_propose > 0 and v_ajustee > 0:
        mens = _calculer_mensualite(v_ajustee, taux_propose, 20)
        total_int = round(mens * 240 - v_ajustee)
        taux_rows.append([
            Paragraph("Mensualité estimée (20 ans)", s["RiskName"]),
            Paragraph(f"<b>{_fmt_eur(mens)}/mois</b>",
                      ParagraphStyle("Mens", fontName="Helvetica-Bold", fontSize=10,
                      textColor=colors.HexColor(DARK))),
            Paragraph(f"Total intérêts : {_fmt_eur(total_int)}", s["BodySmall"]),
        ])
    el.append(_make_table(taux_rows, [5 * cm, 3.5 * cm, 6.5 * cm]))

    # Points forts / points faibles
    if points_forts or points_faibles:
        el.append(Spacer(1, 3 * mm))
        pf_data = [[Paragraph("<b>✅ Points forts du dossier</b>", s["Positive"]),
                     Paragraph("<b>⚠️ Points de vigilance</b>", s["Warning"])]]
        max_len = max(len(points_forts), len(points_faibles), 1)
        for i in range(max_len):
            pf = points_forts[i] if i < len(points_forts) else ""
            pfb = points_faibles[i] if i < len(points_faibles) else ""
            pf_data.append([Paragraph(f"• {pf}" if pf else "", s["Body"]),
                            Paragraph(f"• {pfb}" if pfb else "", s["Body"])])
        el.append(_make_table(pf_data, [7 * cm, 7 * cm], TEAL_DARK))

    # Exigences bancaires
    if exigences:
        el.append(Spacer(1, 2 * mm))
        ex_text = " • ".join(exigences)
        el.append(Paragraph(f"<b>🏦 Exigences bancaires :</b> {ex_text}", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # [NOUVEAU] 8. CONDITIONS SUSPENSIVES + VÉRIFICATIONS
    # ════════════════════════════════════════════════════════════════════════
    conditions = db.get("conditions_suspensives", [])
    points_a_verifier = db.get("points_a_verifier", [])

    if conditions or points_a_verifier:
        el.extend(_section_header("8. ⚖️ Conditions et vérifications requises", s["SectionTitle"]))
    elif hard_stops and len(hard_stops) > 0:
        # Si pas de conditions mais hard stops, on refait un rappel
        pass

    if conditions:
        cond_rows = [[Paragraph(f"⚖️ {c}", s["Body"])] for c in conditions]
        cond_t = Table(cond_rows, colWidths=[14 * cm])
        cond_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(ORANGE_LIGHT)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(ORANGE)),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        el.append(cond_t)
        el.append(Spacer(1, 2 * mm))

    if points_a_verifier:
        pav_text = " • ".join(points_a_verifier)
        el.append(Paragraph(f"<b>⚠️ Vérifications KYC requises :</b> {pav_text}", s["Body"]))

    # ════════════════════════════════════════════════════════════════════════
    # 9. RAPPORT SYNTHÉTIQUE
    # ════════════════════════════════════════════════════════════════════════
    el.extend(_section_header("9. 📄 Rapport d'analyse synthétique", s["SectionTitle"]))

    points_cles = db.get("synthese_points_cles", [])
    if points_cles:
        pc_text = " • ".join(points_cles)
        el.append(Paragraph(f"<b>Points clés :</b> {pc_text}", s["Body"]))
        el.append(Spacer(1, 2 * mm))

    rapport = db.get("rapport_synthetique", "")
    if rapport:
        for line in rapport.split("\n"):
            line = line.strip()
            if line:
                el.append(Paragraph(line, s["Body"]))
                el.append(Spacer(1, 1 * mm))

    avis = db.get("avis_analyste", "")
    if avis:
        el.append(Spacer(1, 3 * mm))
        el.append(Paragraph("<b>Avis du Comité de Crédit (IA) :</b>", s["Body"]))
        el.append(Paragraph(f"« {avis} »", s["AvisText"]))

    # ════════════════════════════════════════════════════════════════════════
    # PIED DE PAGE
    # ════════════════════════════════════════════════════════════════════════
    el.append(Spacer(1, 8 * mm))
    el.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor(TEAL_LIGHT), spaceAfter=3 * mm))
    el.append(Paragraph(
        "Document généré automatiquement — Outil d'aide à la décision<br/>"
        "Aucune décision d'acceptation ou de refus n'est contenue dans ce rapport.<br/>"
        "Sources : DVF DGFiP, Géorisques (BRGM), IGN, ADEME",
        s["Footer"],
    ))

    doc.build(el)
    buf.seek(0)
    return buf


def _interpreter_score(score: int) -> str:
    """Interprétation textuelle du score bancaire."""
    if score >= 60:
        return "Expertise humaine approfondie nécessaire — vigilance maximale"
    if score >= 35:
        return "Vigilance renforcée — documents supplémentaires requis"
    return "Profil standard — vérifications de routine"


def _calculer_mensualite(capital: float, taux_annuel: float, annees: int) -> float:
    """Calcule la mensualité d'un prêt amortissable (formule classique)."""
    if taux_annuel <= 0 or capital <= 0 or annees <= 0:
        return 0
    n = annees * 12
    tm = taux_annuel / 100 / 12
    if tm <= 0:
        return round(capital / n)
    mens = capital * (tm * (1 + tm) ** n) / ((1 + tm) ** n - 1)
    return round(mens)
