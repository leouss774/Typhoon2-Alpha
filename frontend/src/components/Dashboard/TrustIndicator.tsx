interface TrustItem {
  label: string;
  value: string | number;
  trust: number; // 0-100
  source: string;
  detail?: string;
  isExpired?: boolean;
}

interface TrustIndicatorProps {
  items: TrustItem[];
}

function trustColor(score: number): string {
  if (score >= 80) return "#22c55e";
  if (score >= 50) return "#eab308";
  return "#ef4444";
}

function trustLabel(score: number): string {
  if (score >= 80) return "Elevee";
  if (score >= 50) return "Moyenne";
  return "Faible";
}

export default function TrustIndicator({ items }: TrustIndicatorProps) {
  if (!items || items.length === 0) return null;

  const avgTrust = Math.round(items.reduce((s, i) => s + i.trust, 0) / items.length);

  return (
    <div className="bank-section">
      <h3 className="bank-section-title" style={{ color: "var(--color-primary)", marginBottom: "4px" }}>
        Fiabilite des Donnees
      </h3>
      <p style={{ fontSize: "0.65rem", color: "var(--color-text-secondary)", marginBottom: "12px" }}>
        Indice de confiance par source de donnees — chaque donnee est tracee jusqu'a sa source officielle
      </p>

      {/* Score global */}
      <div style={{
        display: "flex", alignItems: "center", gap: "12px",
        padding: "10px 14px", borderRadius: "8px",
        background: `${trustColor(avgTrust)}11`,
        border: `1px solid ${trustColor(avgTrust)}33`,
        marginBottom: "12px",
      }}>
        <span style={{ width: "12px", height: "12px", borderRadius: "50%", flexShrink: 0, background: trustColor(avgTrust) }} />
        <div>
          <div style={{ fontSize: "0.8rem", fontWeight: 700, color: trustColor(avgTrust) }}>
            Confiance globale : {avgTrust}% — {trustLabel(avgTrust)}
          </div>
          <div style={{ fontSize: "0.65rem", color: "var(--color-text-secondary)", marginTop: "2px" }}>
            {avgTrust >= 80
              ? "Toutes les sources sont verifiees et a jour"
              : avgTrust >= 50
                ? "Certaines sources necessitent une verification manuelle"
                : "Plusieurs sources sont indisponibles ou incoherentes — vigilance renforcee"}
          </div>
        </div>
      </div>

      {/* Détail par source */}
      <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
        {items.map((item, idx) => {
          const color = trustColor(item.trust);
          return (
            <div
              key={idx}
              title={item.detail || `${item.source} — Confiance ${item.trust}%`}
              style={{
                display: "flex", alignItems: "center", gap: "8px",
                padding: "6px 10px", borderRadius: "6px",
                background: `${color}08`, cursor: "help",
                transition: "all 0.2s",
                border: item.isExpired ? "1px solid #ef444444" : "none",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = `${color}15`; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = `${color}08`; }}
            >
              <span style={{ width: "8px", height: "8px", borderRadius: "50%", flexShrink: 0, background: color }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.7rem", fontWeight: 600, color: "var(--color-text)" }}>
                    {item.label}
                  </span>
                  <span style={{ fontSize: "0.6rem", color, fontWeight: 700 }}>
                    {item.trust}%
                  </span>
                </div>
                <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", marginTop: "1px" }}>
                  {item.source} — {item.value}
                </div>
                {/* Barre de confiance */}
                <div style={{ height: "3px", background: "#30363d", borderRadius: "2px", marginTop: "3px", overflow: "hidden" }}>
                  <div style={{ width: `${item.trust}%`, height: "100%", background: color, borderRadius: "2px", transition: "width 0.5s" }} />
                </div>
                {/* Avertissement expiration */}
                {item.isExpired && (
                  <div style={{ fontSize: "0.55rem", color: "#ef4444", marginTop: "2px", fontWeight: 600 }}>
                    Donnees expirees — executer python scripts/update_dvf.py
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}