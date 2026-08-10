// =============================================================================
//   TYPHOON — /zone : export PDF du rapport d'analyse IA (jsPDF)
//   Génère un PDF A4 « façon product » sans aucun appel réseau :
//     · bande d'en-tête de marque (logo Typhoon, liseré accent)
//     · métadonnées d'adresse (INSEE, GPS, date)
//     · score de risque global (jauge D03 + pastille)
//     · tableau des aléas recensés (statut · niveau · score)
//     · fiche du bien BDNB (si disponible)
//     · sections du rapport Mistral + synthèse encadrée + obligations
//     · pied de page paginé (sources, page X/Y)
// =============================================================================

import { jsPDF } from 'jspdf';
import { D03, bandForKey, aleaScore, type RisqueReport, type RapportNarratif } from './config';

/* ── Palette PDF (alignée sur la marque Typhoon) ── */
const NAVY = '#0C2233';
const NAVY_LIGHT = '#16374F';
const ACCENT = '#4386B1';
const INK = '#1A2733';
const MUTED = '#5B6B7A';
const LINE = '#C9D6E0';
const TINT = '#EDF4F9';
const ROW_ALT = '#F6FAFD';
const OK = '#2E7D5B';
const WARN_TINT = '#FBF6EA';
const WARN_INK = '#8A6D1F';
const WHITE_60 = '#B9CCDA';

const PAGE_W = 210;
const PAGE_H = 297;
const M = 16; // marge gauche/droite
const CW = PAGE_W - 2 * M; // largeur utile
const FOOTER_TOP = PAGE_H - 12;
const SAFE_BOTTOM = PAGE_H - 16;

/* Logo Typhoon (blanc, fond transparent) encodé en dur pour un export 100 %
   hors-ligne. viewBox 766.43 × 140.93 (aspect ≈ 5.438). */
const TYPHOON_WORDMARK_SVG = `<?xml version="1.0" encoding="UTF-8"?>
<svg id="Layer_2" data-name="Layer 2" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 766.43 140.93">
  <defs>
    <style>
      .cls-1 {
        fill: #fff;
      }
    </style>
  </defs>
  <g id="Layer_1-2" data-name="Layer 1">
    <g>
      <g>
        <path class="cls-1" d="M4.13,95.28c.44-.96,1.78-.96,2.26-.02,3.78,7.5,11.49,12.97,19.38,15.37,31.98,9.71,85.44-16.17,104.32-42.5,7.24-10.1,12.74-24.32-2.11-30.37-.06-.02-.11-.04-.17-.06l-.9-.24c-1.39-.37-1.17-2.4.27-2.46,10.63-.41,23.48.57,28.55,9.56,8.54,15.15-10.87,38.18-21.37,48.13-22.35,21.17-56.43,37.62-87,41.77-20.21,2.74-50.95.26-47.01-27.69.12-.85,2.21-8.02,3.79-11.5Z"/>
        <path class="cls-1" d="M96.93,138.58l9.11-5.31s.04-.02.06-.04c21.48-14.09,60.76-48.23,63.77-74.87,1.66-14.67-7.14-25.8-21.25-29-23.79-5.39-52.46,7.23-70,22.94-.37.08-.34-.52-.24-.73.19-.42,5.35-5.86,6.19-6.69,14.47-14.33,36.02-24.41,56.11-27.59,60.67-9.62,75.65,34.69,38.23,76.86-20.45,23.05-50.8,39.64-81.07,46.73-1.4.33-2.15-1.58-.91-2.3Z"/>
        <path class="cls-1" d="M69.22,78.57c-2.46-.21-6.29-.93-8.65-1.75-19.68-6.91-.25-28.36,8.39-36.14,16.85-15.19,42.68-27.8,64.4-34.17,26.54-7.78,77.23-15.9,79.66,22.56.08,1.23-1.45,1.83-2.22.87-2.91-3.65-6.17-6.82-10.23-9.41-34.56-22.08-94.81-2.61-122.69,23.62-7.5,7.06-19.02,20.82-9.3,30.33.09.09.2.17.32.23l3.04,1.57c1.16.6.75,2.35-.56,2.36-.73.01-1.45,0-2.16-.06Z"/>
        <path class="cls-1" d="M87.54,70.16c.91,3.59.96,4.74,4.9,4.39,5.85-.52,31.46-15.51,31.46-15.51,1.53-1.19,1.93-3.33.96-5.01-11.21-19.54-43.3-7.44-37.32,16.13Z"/>
        <path class="cls-1" d="M76.99,85.86c-14.01,2.79-36.37,1.89-32.17-18.3,4.27-20.56,37.32-41.86,54.84-51.15l12.93-6.27c.49-.24.2-.98-.32-.82-30.34,9.5-63.34,27.62-80.66,54.45-20.11,31.15.48,45.25,31.92,38.85,18.27-3.71,38.59-15.91,51.01-29.72,1.11-1.24,4.61-5.71,6.8-8.57.3-.39-.18-.91-.59-.63,0,0-31.45,19.71-43.76,22.16Z"/>
      </g>
      <g>
        <path class="cls-1" d="M279.38,26.5v80.89c0,1.04-.84,1.88-1.88,1.88h-16.6c-1.04,0-1.88-.84-1.88-1.88V26.5c0-1.04-.84-1.88-1.88-1.88h-29.05c-1.04,0-1.88-.84-1.88-1.88V7.32c0-1.04.84-1.88,1.88-1.88h82.21c1.04,0,1.88.84,1.88,1.88v15.43c0,1.04-.84,1.88-1.88,1.88h-29.05c-1.04,0-1.88.84-1.88,1.88Z"/>
        <path class="cls-1" d="M314.55,135.03l15.42-34.04c.23-.51.22-1.09-.02-1.59l-28.91-59.48c-.61-1.25.3-2.7,1.69-2.7h17.61c.74,0,1.4.43,1.71,1.1l16.91,37.17c.68,1.49,2.8,1.46,3.44-.05l15.57-37.07c.29-.7.97-1.15,1.73-1.15h16.64c1.36,0,2.27,1.41,1.71,2.65l-43.56,96.7c-.3.67-.97,1.11-1.71,1.11h-16.52c-1.36,0-2.27-1.41-1.71-2.65Z"/>
        <path class="cls-1" d="M383.79,135.22V39.1c0-1.04.84-1.88,1.88-1.88h15.14c1.04,0,1.88.84,1.88,1.88v1.72c0,1.62,1.92,2.49,3.12,1.4,1.4-1.28,3.1-2.46,5.08-3.53,3.81-2.05,8.44-3.07,13.91-3.07s9.96.95,14.06,2.85c4.1,1.9,7.59,4.54,10.47,7.91,2.88,3.37,5.05,7.32,6.52,11.86,1.46,4.54,2.2,9.49,2.2,14.86s-.81,10.52-2.42,15.16c-1.61,4.64-3.91,8.64-6.88,12.01-2.98,3.37-6.57,6-10.76,7.91-4.2,1.9-8.84,2.85-13.91,2.85s-9.25-.86-12.81-2.56c-1.89-.91-3.53-1.92-4.91-3.03-1.24-1-3.07-.15-3.07,1.44v28.34c0,1.04-.84,1.88-1.88,1.88h-15.72c-1.04,0-1.88-.84-1.88-1.88ZM438.85,73.24c0-6.44-1.73-11.42-5.2-14.94-3.47-3.51-7.69-5.27-12.67-5.27-2.54,0-4.88.46-7.03,1.39-2.15.93-4.05,2.25-5.71,3.95-1.66,1.71-2.95,3.81-3.88,6.3-.93,2.49-1.39,5.34-1.39,8.57s.46,6.08,1.39,8.57c.93,2.49,2.22,4.61,3.88,6.37,1.66,1.76,3.56,3.1,5.71,4.03,2.61,1.13,5.51,1.57,8.7,1.33,1.76-.13,3.5-.57,5.12-1.28,7.38-3.27,11.07-9.6,11.07-19.01Z"/>
        <path class="cls-1" d="M483.68,109.27h-15.72c-1.04,0-1.88-.84-1.88-1.88V5.12c0-1.04.84-1.88,1.88-1.88h15.72c1.04,0,1.88.84,1.88,1.88v33.68c0,1.54,1.77,2.46,2.98,1.51,1.74-1.36,3.72-2.42,5.95-3.17,3.61-1.22,7.12-1.83,10.54-1.83,4.59,0,8.57.76,11.93,2.27,3.37,1.51,6.15,3.54,8.35,6.08,2.2,2.54,3.83,5.56,4.91,9.08,1.07,3.51,1.61,7.23,1.61,11.13v43.52c0,1.04-.84,1.88-1.88,1.88h-15.72c-1.04,0-1.88-.84-1.88-1.88v-40.15c0-4.1-1.05-7.52-3.15-10.25-2.1-2.73-5.49-4.1-10.18-4.1-4.1,0-7.32,1.34-9.67,4.03-2.34,2.69-3.61,6.03-3.81,10.03v40.44c0,1.04-.84,1.88-1.88,1.88Z"/>
        <path class="cls-1" d="M576.64,35.02c5.37,0,10.37.95,15.01,2.86,4.64,1.9,8.64,4.54,12.01,7.91,3.37,3.37,6,7.39,7.91,12.08,1.9,4.69,2.86,9.81,2.86,15.38s-.95,10.67-2.86,15.3c-1.9,4.64-4.54,8.66-7.91,12.08-3.37,3.42-7.37,6.08-12.01,7.98-4.64,1.9-9.64,2.86-15.01,2.86s-10.37-.95-15.01-2.86c-4.64-1.9-8.64-4.56-12.01-7.98-3.37-3.42-6-7.44-7.91-12.08-1.9-4.64-2.86-9.74-2.86-15.3s.95-10.69,2.86-15.38c1.9-4.69,4.54-8.71,7.91-12.08,3.37-3.37,7.37-6.01,12.01-7.91,4.64-1.9,9.64-2.86,15.01-2.86ZM576.64,93.75c2.34,0,4.64-.44,6.88-1.32,2.24-.88,4.2-2.17,5.86-3.88,1.66-1.71,3-3.83,4.03-6.37,1.03-2.54,1.54-5.51,1.54-8.93s-.51-6.39-1.54-8.93c-1.02-2.54-2.37-4.66-4.03-6.37-1.66-1.71-3.61-3-5.86-3.88-2.25-.88-4.54-1.32-6.88-1.32s-4.64.44-6.88,1.32c-2.25.88-4.2,2.17-5.86,3.88-1.66,1.71-3,3.83-4.03,6.37-1.03,2.54-1.54,5.52-1.54,8.93s.51,6.4,1.54,8.93c1.02,2.54,2.37,4.66,4.03,6.37,1.66,1.71,3.61,3,5.86,3.88,2.24.88,4.54,1.32,6.88,1.32Z"/>
        <path class="cls-1" d="M654.84,35.02c5.37,0,10.37.95,15.01,2.86,4.64,1.9,8.64,4.54,12.01,7.91s6,7.39,7.91,12.08c1.9,4.69,2.86,9.81,2.86,15.38s-.95,10.67-2.86,15.3c-1.9,4.64-4.54,8.66-7.91,12.08-3.37,3.42-7.37,6.08-12.01,7.98-4.64,1.9-9.64,2.86-15.01,2.86s-10.37-.95-15.01-2.86c-4.64-1.9-8.64-4.56-12.01-7.98-3.37-3.42-6-7.44-7.91-12.08-1.9-4.64-2.86-9.74-2.86-15.3s.95-10.69,2.86-15.38c1.9-4.69,4.54-8.71,7.91-12.08,3.37-3.37,7.37-6.01,12.01-7.91,4.64-1.9,9.64-2.86,15.01-2.86ZM654.84,93.75c2.34,0,4.64-.44,6.88-1.32,2.24-.88,4.2-2.17,5.86-3.88,1.66-1.71,3-3.83,4.03-6.37,1.03-2.54,1.54-5.51,1.54-8.93s-.51-6.39-1.54-8.93c-1.02-2.54-2.37-4.66-4.03-6.37-1.66-1.71-3.61-3-5.86-3.88-2.25-.88-4.54-1.32-6.88-1.32s-4.64.44-6.88,1.32c-2.25.88-4.2,2.17-5.86,3.88-1.66,1.71-3,3.83-4.03,6.37-1.03,2.54-1.54,5.52-1.54,8.93s.51,6.4,1.54,8.93c1.02,2.54,2.37,4.66,4.03,6.37,1.66,1.71,3.61,3,5.86,3.88,2.24.88,4.54,1.32,6.88,1.32Z"/>
        <path class="cls-1" d="M718.28,109.27h-15.72c-1.04,0-1.88-.84-1.88-1.88V39.1c0-1.04.84-1.88,1.88-1.88h15.14c1.04,0,1.88.84,1.88,1.88v1.64c0,1.68,2.02,2.49,3.22,1.3,1.7-1.69,3.68-3.06,5.94-4.08,3.86-1.76,7.73-2.64,11.64-2.64,4.49,0,8.37.76,11.64,2.27,3.27,1.51,5.98,3.54,8.13,6.08,2.15,2.54,3.73,5.56,4.76,9.08,1.02,3.51,1.54,7.23,1.54,11.13v43.52c0,1.04-.84,1.88-1.88,1.88h-15.72c-1.04,0-1.88-.84-1.88-1.88v-40.15c0-4.1-1.05-7.52-3.15-10.25-2.1-2.73-5.49-4.1-10.18-4.1-4.3,0-7.61,1.44-9.96,4.32-2.34,2.88-3.51,6.42-3.51,10.62v39.57c0,1.04-.84,1.88-1.88,1.88Z"/>
      </g>
    </g>
  </g>
</svg>`;

/** Rasterise un SVG (blob local) en PNG data-URL via canvas — nécessaire pour
    que jsPDF puisse embarquer le logo (il ne lit pas les SVG). */
async function svgToPngDataUrl(svg: string, aspect: number): Promise<string | null> {
  try {
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const img = new Image();
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('svg load'));
      img.src = url;
    });
    const w = 900;
    const h = Math.round(w / aspect);
    const canvas = document.createElement('canvas');
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('no canvas 2d context');
    ctx.drawImage(img, 0, 0, w, h);
    URL.revokeObjectURL(url);
    return canvas.toDataURL('image/png');
  } catch {
    return null;
  }
}

/* Nettoyage des caractères hors encodage WinAnsi (les polices standards jsPDF
   ne dessinent pas les flèches, ≥, ✓…) — on les remplace sans les inventer. */
function sanitizePdfText(input: string): string {
  return String(input ?? '')
    .replace(/\*\*/g, '')
    .replace(/→/g, ' — ')
    .replace(/←/g, ' — ')
    .replace(/[⇒⇔↔↑↓]/g, ' ')
    .replace(/≥/g, '>= ')
    .replace(/≤/g, '<= ')
    .replace(/⚠️|⚠/g, '')
    .replace(/✅/g, '')
    .replace(/❌/g, '')
    .trim();
}

export async function exportRapportPdf(report: RisqueReport, rapport: RapportNarratif): Promise<void> {
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4', compress: true });
  const wordmark = await svgToPngDataUrl(TYPHOON_WORDMARK_SVG, 766.43 / 140.93);

  let y = 0;

  /* ── Helpers de mise en page (mutent `y` partagé) ── */
  const ensureSpace = (h: number) => {
    if (y + h > SAFE_BOTTOM) {
      doc.addPage();
      y = 18;
    }
  };

  /** Titre de section : barre accent à gauche + texte navy. */
  const sectionTitle = (title: string) => {
    ensureSpace(10);
    doc.setFillColor(ACCENT);
    doc.rect(M, y - 3.4, 1.7, 5.6, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12.5);
    doc.setTextColor(NAVY);
    doc.text(title, M + 4.6, y);
    y += 5.6;
  };

  /** Paragraphe justifié à gauche, avec passage à la page automatique. */
  const paragraph = (text: string, size = 10, lineH = 4.9, color = INK, style: 'normal' | 'italic' = 'normal') => {
    doc.setFont('helvetica', style);
    doc.setFontSize(size);
    doc.setTextColor(color);
    const lines = doc.splitTextToSize(sanitizePdfText(text), CW);
    for (const ln of lines) {
      if (y > SAFE_BOTTOM) {
        doc.addPage();
        y = 18;
      }
      doc.text(ln, M, y);
      y += lineH;
    }
  };

  const divider = () => {
    doc.setDrawColor(LINE);
    doc.setLineWidth(0.35);
    doc.line(M, y, PAGE_W - M, y);
    y += 7;
  };

  /* ══ Bande d'en-tête de marque ══ */
  doc.setFillColor(NAVY);
  doc.rect(0, 0, PAGE_W, 46, 'F');
  doc.setFillColor(NAVY_LIGHT);
  doc.rect(0, 0, PAGE_W, 3, 'F');
  doc.setFillColor(ACCENT);
  doc.rect(0, 46, PAGE_W, 2.2, 'F');

  if (wordmark) {
    doc.addImage(wordmark, 'PNG', M, 15, 52, 52 / (766.43 / 140.93));
  } else {
    /* Repli : si la rasterisation du SVG a échoué, la marque reste présente. */
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(24);
    doc.setTextColor('#FFFFFF');
    doc.text('TYPHOON', M, 23);
  }
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(15);
  doc.setTextColor('#FFFFFF');
  doc.text('Rapport d’analyse IA', PAGE_W - M, 17, { align: 'right' });
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(8.5);
  doc.setTextColor(WHITE_60);
  doc.text('Diagnostic géo-risque · Résilience climatique du bâtiment', PAGE_W - M, 23, { align: 'right' });

  y = 56;

  /* ══ Métadonnées d'adresse ══ */
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(15.5);
  doc.setTextColor(NAVY);
  const adresseLines = doc.splitTextToSize(sanitizePdfText(report.adresse_normalisee || report.adresse_saisie), CW);
  doc.text(adresseLines, M, y);
  y += adresseLines.length * 6.4;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  doc.setTextColor(MUTED);
  doc.text(
    `Code INSEE ${report.code_insee} · GPS ${report.lat.toFixed(5)}°N, ${report.lon.toFixed(5)}°E · ${report.alea_count} aléa(s) recensé(s) · Données Géorisques (BRGM/MTE)`,
    M,
    y
  );
  y += 4.6;
  doc.text(`Rapport généré par Typhoon le ${report.date_generation} — analyse IA (Mistral)`, M, y);
  y += 4;
  divider();

  /* ══ Score de risque global (jauge D03) ══ */
  const presentAleas = (report.aleas || []).filter((a) => a.present === true);
  const maxScore = presentAleas.length ? Math.max(...presentAleas.map((a) => aleaScore(a))) : null;
  const globalBand = maxScore != null ? D03.find((b) => maxScore < b.max) || D03[D03.length - 1] : null;

  doc.setFont('helvetica', 'bold');
  doc.setFontSize(11.5);
  doc.setTextColor(NAVY);
  doc.text('Score de risque global', M, y);
  y += 3;

  const gap = 0.9;
  const segW = (CW - 4 * gap) / 5;
  const gy = y;
  D03.forEach((b, i) => {
    doc.setFillColor(b.color);
    doc.rect(M + i * (segW + gap), gy, segW, 4.6, 'F');
  });
  if (maxScore != null) {
    const pct = Math.min(1, maxScore / 100);
    doc.setFillColor('#FFFFFF');
    doc.circle(M + CW * pct, gy + 2.3, 2.6, 'F');
    doc.setFillColor(INK);
    doc.circle(M + CW * pct, gy + 2.3, 1.7, 'F');
  }
  y += 8;

  if (maxScore != null && globalBand) {
    const label = `${maxScore}/100 · ${globalBand.label}`;
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(10);
    const tw = doc.getTextWidth(label) + 8;
    doc.setFillColor(globalBand.color);
    doc.roundedRect(M, y - 3.4, tw, 6.4, 3.2, 3.2, 'F');
    doc.setTextColor('#FFFFFF');
    doc.text(label, M + 4, y + 0.5);
    y += 10;
  } else {
    y += 3;
  }

  /* ══ Tableau des aléas recensés ══ */
  const rows = (report.aleas || []).filter((a) => a.present !== false);
  if (rows.length) {
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(NAVY);
    doc.text('Aléas recensés — Géorisques', M, y);
    y += 4.6;

    const xB = M + 88;
    const xC = M + 116;
    const xD = PAGE_W - M;
    const rowH = 6.6;

    /* En-tête du tableau (redessiné après chaque saut de page). */
    const drawTableHeader = () => {
      doc.setFillColor(NAVY);
      doc.rect(M, y, CW, 6.4, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(8.5);
      doc.setTextColor('#FFFFFF');
      doc.text('Aléa', M + 1.5, y + 4.4);
      doc.text('Statut', xB + 1.5, y + 4.4);
      doc.text('Niveau', xC + 1.5, y + 4.4);
      doc.text('Score /100', xD, y + 4.4, { align: 'right' });
      y += 6.4;
    };
    drawTableHeader();

    const shown = rows.slice(0, 14);
    shown.forEach((a, i) => {
      if (y + rowH > SAFE_BOTTOM) {
        doc.addPage();
        y = 18;
        drawTableHeader();
      }
      if (i % 2 === 1) {
        doc.setFillColor(ROW_ALT);
        doc.rect(M, y, CW, rowH, 'F');
      }
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(9);
      doc.setTextColor(INK);
      const name = doc.splitTextToSize(sanitizePdfText(a.libelle), 84)[0];
      doc.text(name, M + 1.5, y + 4.3);

      let status: string;
      let statusColor: string;
      if (a.present === true) {
        status = 'Concerné';
        statusColor = OK;
      } else if (a.present === false) {
        status = 'Non concerné';
        statusColor = MUTED;
      } else {
        status = 'Source indisponible';
        statusColor = MUTED;
      }
      doc.setTextColor(statusColor);
      doc.text(status, xB + 1.5, y + 4.3);

      const b = bandForKey(a.niveau);
      if (a.present === true) {
        if (b) {
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(8.5);
          const tw = doc.getTextWidth(b.label) + 4.5;
          doc.setFillColor(b.color);
          doc.roundedRect(xC + 1, y + 1.6, tw, 5.2, 2.6, 2.6, 'F');
          doc.setTextColor('#FFFFFF');
          doc.text(b.label, xC + 3.2, y + 4.8);
        } else {
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(MUTED);
          doc.text('—', xC + 1.5, y + 4.3);
        }
      } else {
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(MUTED);
        doc.text('—', xC + 1.5, y + 4.3);
      }

      doc.setFont('helvetica', 'bold');
      doc.setFontSize(9);
      doc.setTextColor(INK);
      doc.text(a.present === true ? String(aleaScore(a)) : '—', xD, y + 4.3, { align: 'right' });
      y += rowH;
    });

    if (rows.length > 14) {
      doc.setFont('helvetica', 'italic');
      doc.setFontSize(8.5);
      doc.setTextColor(MUTED);
      doc.text(`+ ${rows.length - 14} autre(s) aléa(s) — détail complet sur Géorisques`, M, y + 3.5);
      y += 8;
    } else {
      y += 2;
    }
    divider();
  }

  /* ══ Fiche du bien (BDNB) ══ */
  const batiment = report.bdnb?.batiment;
  if (batiment) {
    const fields: Array<[string, string]> = (
      [
        ['Année de construction', batiment.annee_construction != null ? String(batiment.annee_construction) : null],
        ['Murs', batiment.mat_mur_txt],
        ['Toiture', batiment.mat_toit_txt],
        ['Niveaux', batiment.nb_niveau != null ? String(batiment.nb_niveau) : null],
        ['Hauteur', batiment.hauteur_mean != null ? `${batiment.hauteur_mean} m` : null],
        ['Surface au sol', batiment.surface_emprise_sol != null ? `${batiment.surface_emprise_sol} m²` : null],
        ['Usage', batiment.usage_niveau_1_txt],
        ['Aléa argile (BDNB)', batiment.alea_argile],
      ] as Array<[string, string | null]>
    ).filter(([, v]) => v != null && v.trim() !== '') as Array<[string, string]>;

    if (fields.length) {
      sectionTitle('Fiche du bien — BDNB');
      const line = fields.map(([l, v]) => `${l} : ${v}`).join('   ·   ');
      paragraph(line);
      y += 1;
      divider();
    }
  }

  /* ══ Sections du rapport IA ══ */
  if (rapport.introduction) {
    sectionTitle('Introduction');
    paragraph(rapport.introduction);
    y += 2;
  }

  (rapport.sections || []).forEach((s) => {
    if (!s.contenu) return;
    sectionTitle(s.titre || 'Analyse');
    paragraph(s.contenu);
    y += 2;
  });

  /* ══ Synthèse finale (encadrée) ══ */
  if (rapport.synthese_finale) {
    const synLines = doc.splitTextToSize(sanitizePdfText(rapport.synthese_finale), CW - 14);
    const boxH = synLines.length * 4.9 + 17;
    ensureSpace(boxH);
    doc.setFillColor(TINT);
    doc.roundedRect(M, y - 1, CW, boxH, 2.5, 2.5, 'F');
    doc.setFillColor(ACCENT);
    doc.rect(M, y - 1, 2.2, boxH, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(12);
    doc.setTextColor(ACCENT);
    doc.text('Synthèse finale', M + 6, y + 5);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.setTextColor(INK);
    let ty = y + 11;
    for (const ln of synLines) {
      doc.text(ln, M + 6, ty);
      ty += 4.9;
    }
    y += boxH + 8;
  }

  /* ══ Obligations réglementaires ══ */
  const obligations = (rapport.obligations_reglementaires || []).filter((o) => o && o.trim());
  if (obligations.length) {
    sectionTitle('Obligations réglementaires');
    obligations.forEach((o) => {
      const lines = doc.splitTextToSize(sanitizePdfText(o), CW - 6);
      const h = lines.length * 4.8 + 2;
      ensureSpace(h);
      doc.setFillColor(ACCENT);
      doc.circle(M + 1.4, y - 1.8, 0.9, 'F');
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(10);
      doc.setTextColor(INK);
      let ly = y;
      for (const ln of lines) {
        doc.text(ln, M + 5, ly);
        ly += 4.8;
      }
      y = ly + 1.5;
    });
    y += 2;
  }

  /* ══ Avertissement ══ */
  const avert = rapport.avertissement_ia;
  if (avert) {
    const warnLines = doc.splitTextToSize(sanitizePdfText(avert), CW - 8);
    const boxH = warnLines.length * 3.8 + 11;
    ensureSpace(boxH);
    doc.setFillColor(WARN_TINT);
    doc.roundedRect(M, y - 1, CW, boxH, 2, 2, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8.5);
    doc.setTextColor(WARN_INK);
    doc.text('Avertissement', M + 4, y + 3.6);
    doc.setFont('helvetica', 'italic');
    doc.setFontSize(8);
    doc.setTextColor(MUTED);
    let wy = y + 7;
    for (const ln of warnLines) {
      doc.text(ln, M + 4, wy);
      wy += 3.8;
    }
    y = wy + 5;
  }

  /* ══ Pied de page (toutes pages) ══ */
  const total = doc.getNumberOfPages();
  for (let i = 1; i <= total; i++) {
    doc.setPage(i);
    doc.setDrawColor(LINE);
    doc.setLineWidth(0.3);
    doc.line(M, FOOTER_TOP, PAGE_W - M, FOOTER_TOP);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.setTextColor(MUTED);
    doc.text('Généré par Typhoon · Sources : Géorisques (BRGM/MTE), BDNB, Mistral', M, FOOTER_TOP + 5);
    doc.text(`Page ${i} / ${total}`, PAGE_W - M, FOOTER_TOP + 5, { align: 'right' });
  }

  const datePart = (report.date_generation || '').slice(0, 10);
  doc.save(`rapport_typhoon_${report.code_insee || 'adresse'}_${datePart}.pdf`);
}
