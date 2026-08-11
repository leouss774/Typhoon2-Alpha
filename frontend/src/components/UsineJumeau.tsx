// =============================================================================
//   TYPHOON — UsineJumeau : viewer 3D isométrique réaliste de l'usine
//   Représentation bâtiment / zones / équipements avec coloration par risque.
//   Aucune dépendance externe : SVG inline + dégradés/ombres CSS.
// =============================================================================

import { useMemo } from 'react';

export type Equipement = {
  id: string;
  nom: string;
  type: string;
  zone: string;
  valeur_remplacement_eur?: number;
  matieres_dangereuses?: boolean;
  critique_production?: boolean;
  score_risque?: number;
};

export type ZonePlan = {
  id: string;
  nom: string;
  type: string;
  surface_m2?: number;
  score_risque?: number;
  niveau?: 'faible' | 'modere' | 'eleve' | 'critique';
};

const RISK_COLORS: Record<string, { fill: string; stroke: string; glow: string }> = {
  critique: { fill: '#ef4444', stroke: '#b91c1c', glow: '#fca5a5' },
  eleve: { fill: '#f97316', stroke: '#c2410c', glow: '#fdba74' },
  modere: { fill: '#eab308', stroke: '#a16207', glow: '#fde047' },
  faible: { fill: '#22c55e', stroke: '#15803d', glow: '#86efac' },
  inconnu: { fill: '#94a3b8', stroke: '#475569', glow: '#cbd5e1' },
};

function riskMeta(score?: number) {
  if (score == null) return RISK_COLORS.inconnu;
  if (score >= 80) return RISK_COLORS.critique;
  if (score >= 60) return RISK_COLORS.eleve;
  if (score >= 40) return RISK_COLORS.modere;
  return RISK_COLORS.faible;
}

function riskLevel(score?: number): ZonePlan['niveau'] {
  if (score == null) return 'faible';
  if (score >= 80) return 'critique';
  if (score >= 60) return 'eleve';
  if (score >= 40) return 'modere';
  return 'faible';
}

type Props = {
  zones: ZonePlan[];
  equipements: Equipement[];
  width?: number;
  height?: number;
};

export function UsineJumeau({ zones, equipements, width = 900, height = 620 }: Props) {
  const equipByZone = useMemo(() => {
    const m = new Map<string, Equipement[]>();
    for (const e of equipements) {
      const list = m.get(e.zone) || [];
      list.push(e);
      m.set(e.zone, list);
    }
    return m;
  }, [equipements]);

  const layout = useMemo(() => {
    const n = zones.length || 1;
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);
    const cellW = Math.min(220, Math.floor(width / cols));
    const cellH = Math.min(180, Math.floor(height / rows));
    const originX = Math.floor((width - cols * cellW) / 2) + cellW / 2;
    const originY = Math.floor((height - rows * cellH) / 2) + cellH / 2;

    return zones.map((z, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      const cx = originX + col * cellW + cellW / 2;
      const cy = originY + row * cellH + cellH / 2;
      return { zone: z, cx, cy, w: cellW - 20, h: cellH - 20 };
    });
  }, [zones, width, height]);

  function isoBox(cx: number, cy: number, w: number, h: number, depth = 28) {
    const hw = w / 2;
    const hh = h / 2;
    const dx = 14;
    const dy = 10;
    return {
      top: `${cx - hw},${cy - hh}`,
      right: `${cx + hw},${cy - hh}`,
      bottom: `${cx + hw},${cy + hh}`,
      left: `${cx - hw},${cy + hh}`,
      side: `${cx - hw},${cy + hh} ${cx + hw},${cy + hh} ${cx + hw + dx},${cy + hh - dy} ${cx - hw + dx},${cy + hh - dy}`,
      roof: `${cx - hw + dx},${cy - hh - dy} ${cx + hw + dx},${cy - hh - dy} ${cx + hw + dx},${cy + hh - dy} ${cx - hw + dx},${cy + hh - dy}`,
      front: `${cx - hw},${cy - hh} ${cx + hw},${cy - hh} ${cx + hw},${cy + hh} ${cx - hw},${cy + hh}`,
      leftBack: `${cx - hw + dx},${cy + hh - dy}`,
      bottomBack: `${cx + hw + dx},${cy + hh - dy}`,
      rightBack: `${cx + hw + dx},${cy - hh - dy}`,
      topBack: `${cx - hw + dx},${cy - hh - dy}`,
    };
  }

  return (
    <div className="usine-jumeau-wrap">
      <div className="usine-jumeau-toolbar">
        <strong>Jumeau réaliste</strong>
        <span className="usine-jumeau-hint">Vue isométrique · coloré par risque</span>
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height="100%"
        xmlns="http://www.w3.org/2000/svg"
        className="usine-jumeau-svg"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <filter id="jumeau-shadow" x="-40%" y="-40%" width="180%" height="180%">
            <feDropShadow dx="0" dy="18" stdDeviation="12" floodColor="#000" floodOpacity="0.35" />
          </filter>
          <filter id="jumeau-glow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="ground-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1f2937" />
            <stop offset="100%" stopColor="#0b1220" />
          </linearGradient>
          <linearGradient id="wall-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#475569" />
            <stop offset="100%" stopColor="#1e293b" />
          </linearGradient>
        </defs>

        <rect x="0" y="0" width={width} height={height} fill="url(#ground-grad)" />

        <g opacity="0.12">
          {Array.from({ length: Math.floor(width / 60) }).map((_, i) => (
            <line key={`gx-${i}`} x1={i * 60} y1="0" x2={i * 60} y2={height} stroke="#e5e7eb" strokeWidth="1" />
          ))}
          {Array.from({ length: Math.floor(height / 60) }).map((_, i) => (
            <line key={`gy-${i}`} x1="0" y1={i * 60} x2={width} y2={i * 60} stroke="#e5e7eb" strokeWidth="1" />
          ))}
        </g>

        {zones.map((zone, idx) => {
          const cx = (width / (zones.length + 1)) * (idx + 1);
          const cy = height / 2;
          const w = Math.min(220, Math.floor(width / zones.length) - 20);
          const h = Math.min(180, Math.floor(height / 2) - 20);
          const box = isoBox(cx, cy, w, h, 28);
          const meta = riskMeta(zone.score_risque);
          const niveau = zone.niveau || riskLevel(zone.score_risque);
          const equipements = equipByZone.get(zone.id) || [];
          const count = equipements.length;
          const surface = zone.surface_m2 ? `${zone.surface_m2.toLocaleString('fr-FR')} m²` : '';

          return (
            <g key={zone.id} className="jumeau-zone" filter="url(#jumeau-shadow)">
              <polygon
                points={`${box.left} ${box.bottom} ${box.right} ${box.bottom} ${box.bottomBack} ${box.leftBack}`}
                fill="#000"
                opacity="0.35"
              />
              <polygon
                points={`${box.left} ${box.bottom} ${box.bottomBack} ${box.leftBack}`}
                fill="#0f172a"
                stroke={meta.stroke}
                strokeWidth="1.2"
              />
              <polygon
                points={`${box.left} ${box.bottom} ${box.right} ${box.bottom} ${box.right} ${box.top} ${box.left} ${box.top}`}
                fill="url(#wall-grad)"
                stroke={meta.stroke}
                strokeWidth="1.2"
              />
              <polygon
                points={`${box.topBack} ${box.rightBack} ${box.bottomBack} ${box.leftBack}`}
                fill={meta.fill}
                stroke={meta.stroke}
                strokeWidth="1.2"
                filter="url(#jumeau-glow)"
              />
              <polygon
                points={`${box.top} ${box.right} ${box.bottom} ${box.left}`}
                fill={meta.fill}
                opacity="0.85"
                stroke={meta.stroke}
                strokeWidth="1.2"
              />

              <line x1={box.left} y1={box.bottom} x2={box.right} y2={box.bottom} stroke="#000" opacity="0.25" />
              <rect
                x={cx - w * 0.18}
                y={cy - h * 0.28}
                width={w * 0.36}
                height={h * 0.22}
                rx="3"
                fill="#0b1220"
                opacity="0.55"
                stroke={meta.stroke}
                strokeWidth="1"
              />
              <rect
                x={cx + w * 0.08}
                y={cy - h * 0.08}
                width={w * 0.18}
                height={h * 0.18}
                rx="3"
                fill="#0b1220"
                opacity="0.55"
                stroke={meta.stroke}
                strokeWidth="1"
              />

              <text x={cx - w * 0.45} y={cy + h * 0.48} fill="#e5e7eb" fontSize="12" fontWeight="700" opacity="0.95">
                {zone.nom}
              </text>
              <text x={cx - w * 0.45} y={cy + h * 0.48 + 14} fill="#cbd5e1" fontSize="11" opacity="0.85">
                {zone.type} · {surface} · {count} équip.
              </text>
              <text x={cx - w * 0.45} y={cy + h * 0.48 + 28} fill={meta.glow} fontSize="11" fontWeight="700">
                Risque : {niveau} {zone.score_risque != null ? `(${zone.score_risque})` : ''}
              </text>

              {equipements.map((eq, idx) => {
                const ex = cx - w * 0.35 + (idx % 3) * 18;
                const ey = cy - h * 0.22 + Math.floor(idx / 3) * 18;
                const eqColor = eq.score_risque != null ? riskMeta(eq.score_risque).fill : '#cbd5e1';
                return (
                  <g key={eq.id} transform={`translate(${ex}, ${ey})`}>
                    <circle r="6" fill={eqColor} stroke="#0b1220" strokeWidth="1.5" />
                    <circle r="2.2" fill="#fff" opacity="0.9" />
                    <title>{`${eq.nom} (${eq.type})`}</title>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}