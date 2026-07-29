import { useEffect, useState } from "react";

interface MarketData {
  evolution: Array<{ annee: number; prix_m2_median: number; nb_transactions: number }>;
  tendance: string;
  prix_m2_bien: number | null;
  prix_m2_commune: number | null;
  ecart_vs_commune_pct: number | null;
  nb_transactions: number;
  volume_total_transactions: number;
  indice_confiance_dvf: number;
  valeur_actuelle: number | null;
}

interface MarketComparisonProps {
  adresse: string;
  type_bien?: string;
  surface?: number;
}

export default function MarketComparison({ adresse, type_bien = "Maison", surface = 100 }: MarketComparisonProps) {
  const [data, setData] = useState<MarketData | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!adresse || adresse === "Adresse inconnue") return;
    setLoading(true);
    fetch("/api/bank/market-trends", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ adresse, type_bien, surface }),
    })
      .then((r) => r.json())
      .then((json) => setData(json))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [adresse, type_bien, surface]);

  if (loading) {
    return (
      <div className="bank-section" style={{ textAlign: "center", padding: "20px", color: "var(--color-text-secondary)" }}>            Analyse du marche...
      </div>
    );
  }

  if (!data || !data.prix_m2_bien) return null;

  const { prix_m2_bien, prix_m2_commune, ecart_vs_commune_pct, tendance, nb_transactions, indice_confiance_dvf } = data;
  const maxPm2 = Math.max(prix_m2_bien, prix_m2_commune || 0) * 1.3;

  const ecartLabel = ecart_vs_commune_pct != null
    ? (ecart_vs_commune_pct >= 0 ? `+${ecart_vs_commune_pct}% au-dessus` : `${ecart_vs_commune_pct}% en dessous`)
    : "";

  const ecartColor = ecart_vs_commune_pct != null
    ? (ecart_vs_commune_pct <= -5 ? "var(--color-risk-faible)"
      : ecart_vs_commune_pct <= 5 ? "var(--color-text)"
      : "var(--color-risk-critique)")
    : "var(--color-text-secondary)";

  const confianceColor = indice_confiance_dvf >= 80 ? "var(--color-risk-faible)"
    : indice_confiance_dvf >= 50 ? "#eab308"
    : "var(--color-risk-critique)";

  return (
    <div className="bank-section">
      <h3 className="bank-section-title" style={{ color: "var(--color-primary)", marginBottom: "4px" }}>
        Comparaison de Marché
        <span style={{ marginLeft: "8px", fontSize: "0.65rem", fontWeight: 400, color: "var(--color-text-secondary)" }}>
          — Donnees DVF reelles
        </span>
      </h3>

      {/* Barre de comparaison horizontale */}
      <div style={{ margin: "16px 0 12px" }}>
        {/* Barre prix/m² du bien */}
        <div style={{ marginBottom: "10px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "4px" }}>
            <span style={{ fontWeight: 600, color: "var(--color-text)" }}>
              {type_bien} ({surface}m²)
            </span>
            <span style={{ fontWeight: 700, color: "var(--color-primary)" }}>
              {new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(prix_m2_bien)}/m²
            </span>
          </div>
          <div style={{ height: "10px", background: "var(--color-bg)", borderRadius: "5px", overflow: "hidden" }}>
            <div style={{
              width: `${(prix_m2_bien / maxPm2) * 100}%`, height: "100%",
              background: "linear-gradient(90deg, var(--color-primary), var(--color-primary-light))",
              borderRadius: "5px", transition: "width 0.5s",
            }} />
          </div>
        </div>

        {/* Barre moyenne commune */}
        {prix_m2_commune != null && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.75rem", marginBottom: "4px" }}>
              <span style={{ color: "var(--color-text-secondary)" }}>
                Moyenne commune
              </span>
              <span style={{ fontWeight: 600, color: "var(--color-text-secondary)" }}>
                {new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }).format(prix_m2_commune)}/m²
              </span>
            </div>
            <div style={{ height: "10px", background: "var(--color-bg)", borderRadius: "5px", overflow: "hidden" }}>
              <div style={{
                width: `${(prix_m2_commune / maxPm2) * 100}%`, height: "100%",
                background: "var(--color-text-secondary)", opacity: 0.5,
                borderRadius: "5px", transition: "width 0.5s",
              }} />
            </div>
          </div>
        )}
      </div>

      {/* Métriques */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
        {/* Écart */}
        <div style={{
          padding: "10px", borderRadius: "8px", textAlign: "center",
          background: ecart_vs_commune_pct != null && ecart_vs_commune_pct <= -5
            ? "rgba(34,197,94,0.08)" : "var(--color-bg)",
          border: `1px solid ${ecartColor}30`,
        }}>
          <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Écart marché
          </div>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: ecartColor }}>
            {ecartLabel || "N/A"}
          </div>
          <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", marginTop: "2px" }}>
            vs moyenne locale
          </div>
        </div>

        {/* Transactions */}
        <div style={{ padding: "10px", borderRadius: "8px", textAlign: "center", background: "var(--color-bg)", border: "1px solid #30363d" }}>
          <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Transactions
          </div>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--color-text)" }}>
            {nb_transactions}
          </div>
          <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", marginTop: "2px" }}>
            ventes récentes
          </div>
        </div>

        {/* Confiance */}
        <div style={{
          padding: "10px", borderRadius: "8px", textAlign: "center",
          background: `rgba(${indice_confiance_dvf >= 80 ? "34,197,94" : "234,179,8"},0.08)`,
          border: `1px solid ${confianceColor}30`,
        }}>
          <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Confiance DVF
          </div>
          <div style={{ fontSize: "1rem", fontWeight: 700, color: confianceColor }}>
            {indice_confiance_dvf}%
          </div>
          <div style={{ fontSize: "0.6rem", color: "var(--color-text-secondary)", marginTop: "2px" }}>
            Tendance : {tendance}
          </div>
        </div>
      </div>

      {/* Légende interprétation */}
      <div style={{ marginTop: "10px", padding: "8px 12px", background: "var(--color-bg)", borderRadius: "6px", fontSize: "0.65rem", color: "var(--color-text-secondary)", display: "flex", gap: "16px", alignItems: "center", flexWrap: "wrap" }}>
        {ecart_vs_commune_pct != null && (
          <span>
            <strong>Interpretation :</strong>{" "}
            {ecart_vs_commune_pct <= -10 ? "Bien sous-evalue par rapport au marche local"
              : ecart_vs_commune_pct <= 5 ? "Bien dans la moyenne du marche"
              : ecart_vs_commune_pct <= 15 ? "Bien legerement au-dessus du marche"
              : "Bien significativement au-dessus du marche"}
          </span>
        )}
        <span style={{ marginLeft: "auto" }}>
          Donnees DGFiP (Demandes de Valeurs Foncieres)
        </span>
      </div>
    </div>
  );
}
