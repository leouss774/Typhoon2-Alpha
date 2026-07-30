import { useState } from "react";

interface LoanSimulatorProps {
  valeur_ajustee: number;
  taux_propose: number;
  majoration_taux?: number;
  source_taux?: string;
  date_taux?: string;
  confiance_taux?: number;
}

function calculerMensualite(capital: number, tauxAnnuel: number, dureeAns: number): number {
  if (tauxAnnuel <= 0 || capital <= 0) return 0;
  const n = dureeAns * 12;
  const tm = tauxAnnuel / 100 / 12;
  if (tm <= 0) return Math.round(capital / n);
  return Math.round(capital * (tm * Math.pow(1 + tm, n)) / (Math.pow(1 + tm, n) - 1));
}

function formatEur(val: number): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency", currency: "EUR", maximumFractionDigits: 0,
  }).format(val);
}

export default function LoanSimulator({
  valeur_ajustee, taux_propose, majoration_taux, source_taux, date_taux, confiance_taux,
}: LoanSimulatorProps) {
  const [duree, setDuree] = useState(20);
  const [apport, setApport] = useState(20);

  if (!taux_propose || !valeur_ajustee) return null;

  const montantEmprunt = valeur_ajustee * (1 - apport / 100);
  const mensualite = calculerMensualite(montantEmprunt, taux_propose, duree);
  const totalRembourse = mensualite * duree * 12;
  const totalInterets = totalRembourse - montantEmprunt;
  const ltv = (montantEmprunt / valeur_ajustee) * 100;
  const revenuNecessaire = Math.round(mensualite * 3); // Règle des 33% d'endettement

  return (
    <div className="bank-section">
      <h3 className="bank-section-title" style={{ color: "var(--color-primary)", marginBottom: "4px" }}>
        Simulation de Financement
      </h3>
      <p style={{ fontSize: "0.7rem", color: "var(--color-text-secondary)", marginBottom: "14px" }}>
        Base sur la valeur de garantie et le taux propose
      </p>

      {/* Explication du taux */}
      <div style={{
        marginBottom: "14px", padding: "10px 14px",
        background: "rgba(255,107,74,0.04)", borderRadius: "8px",
        border: "1px solid rgba(255,107,74,0.12)",
      }}>
        <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--color-brand)", marginBottom: "6px", textTransform: "uppercase", letterSpacing: "0.5px" }}>
          Decomposition du taux propose
        </div>
        <div style={{ fontSize: "0.7rem", color: "var(--color-text-secondary)", lineHeight: 1.6 }}>
          <strong>Taux de base :</strong> {((taux_propose || 0) - (majoration_taux || 0)).toFixed(2)}% (20 ans, {date_taux || "N/A"})<br />
          <strong>Majoration risque :</strong> +{(majoration_taux || 0).toFixed(2)}% (selon score climatique)<br />
          <strong>Taux propose :</strong> {taux_propose.toFixed(2)}% (tout compris)<br />
          <span style={{ fontStyle: "italic", fontSize: "0.6rem" }}>
            Source : {source_taux || "Banque de France"} — Confiance {confiance_taux ?? 90}%
          </span>
        </div>
      </div>

      {/* Contrôles */}
      <div style={{ display: "flex", gap: "20px", marginBottom: "16px", flexWrap: "wrap" }}>
        <div style={{ flex: 1, minWidth: "140px" }}>
          <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: "4px" }}>
            Durée : {duree} ans
          </label>
          <input
            type="range"
            min={10}
            max={30}
            step={5}
            value={duree}
            onChange={(e) => setDuree(Number(e.target.value))}
            className="slider"
            style={{ width: "100%" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--color-text-secondary)" }}>
            <span>10 ans</span><span>30 ans</span>
          </div>
        </div>
        <div style={{ flex: 1, minWidth: "140px" }}>
          <label style={{ fontSize: "0.65rem", fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px", display: "block", marginBottom: "4px" }}>
            Apport : {apport}%
          </label>
          <input
            type="range"
            min={5}
            max={50}
            step={5}
            value={apport}
            onChange={(e) => setApport(Number(e.target.value))}
            className="slider"
            style={{ width: "100%" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--color-text-secondary)" }}>
            <span>5%</span><span>50%</span>
          </div>
        </div>
      </div>

      {/* KPIs Simulation */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))", gap: "8px" }}>
        <SimKPICard
          label="Mensualité"
          value={`${mensualite > 0 ? formatEur(mensualite) : "N/A"}/mois`}
          color="var(--color-primary)"
          tooltip="Mensualité estimée hors assurance"
        />
        <SimKPICard
          label="Total Intérêts"
          value={formatEur(totalInterets)}
          color={totalInterets > 50000 ? "#ef4444" : "var(--color-text)"}
          tooltip="Total des intérêts sur toute la durée du prêt"
        />
        <SimKPICard
          label="LTV Ratio"
          value={`${Math.round(ltv)}%`}
          color={ltv > 80 ? "#eab308" : "#22c55e"}
          tooltip="Loan-to-Value : ratio prêt / valeur du bien. Idéalement ≤ 80%"
        />
        <SimKPICard
          label="Revenu nécessaire"
          value={`${formatEur(revenuNecessaire)}/mois`}
          color="var(--color-text-secondary)"
          tooltip="Revenu minimum estimé (taux d'endettement 33%)"
        />
        <SimKPICard
          label="Capital emprunté"
          value={formatEur(montantEmprunt)}
          color="var(--color-text)"
          tooltip="Montant total du prêt"
        />
      </div>

      {/* Barre LTV visuelle */}
      <div style={{ marginTop: "12px", padding: "10px 14px", background: "var(--color-bg)", borderRadius: "8px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--color-text-secondary)", marginBottom: "4px" }}>
          <span>LTV : {Math.round(ltv)}% du bien</span>
          <span>Seuil risque : 80%</span>
        </div>
        <div style={{ height: "8px", background: "var(--color-border)", borderRadius: "4px", overflow: "hidden", position: "relative" }}>
          {/* Seuil 80% */}
          <div style={{ position: "absolute", left: "80%", top: 0, width: "2px", height: "100%", background: "#ef4444", zIndex: 1 }} />
          {/* Barre LTV */}
          <div style={{
            width: `${Math.min(ltv, 100)}%`, height: "100%",
            background: ltv > 80
              ? "linear-gradient(90deg, #22c55e, #eab308, #ef4444)"
              : "linear-gradient(90deg, #22c55e, #FF9269)",
            borderRadius: "4px",
            transition: "width 0.3s",
          }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.6rem", color: "var(--color-text-secondary)", marginTop: "4px" }}>
          <span>{ltv > 80 ? "Ratio eleve — risque de surendettement" : "Ratio sain — risque maitrise"}</span>
          <span>Valeur : {formatEur(valeur_ajustee)}</span>
        </div>
      </div>

      {/* Résumé textuel */}
      <div style={{ marginTop: "8px", padding: "8px 12px", fontSize: "0.65rem", color: "var(--color-text-secondary)", background: "rgba(255,107,74,0.04)", borderRadius: "6px", border: "1px solid rgba(255,107,74,0.1)" }}>
        <strong>Resume :</strong> Pour un pret de <strong>{formatEur(montantEmprunt)}</strong> sur <strong>{duree} ans</strong>
        {" "}à <strong>{taux_propose.toFixed(2)}%</strong>, la mensualité est de <strong>{formatEur(mensualite)}/mois</strong>.
        {" "}Total des intérêts : <strong>{formatEur(totalInterets)}</strong>.
        {" "}Revenu minimum recommandé : <strong>{formatEur(revenuNecessaire)}/mois</strong>.
      </div>
    </div>
  );
}

function SimKPICard({
  label, value, color, tooltip,
}: {
  label: string; value: string; color: string; tooltip: string;
}) {
  return (
    <div
      style={{
        padding: "10px", borderRadius: "8px", textAlign: "center",
        background: "var(--color-bg)",        border: "1px solid var(--color-border)",
        cursor: "help", transition: "all 0.2s",
      }}
      title={tooltip}
    >
      <div style={{ fontSize: "0.55rem", color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px", marginBottom: "4px" }}>
        {label}

      </div>
      <div style={{ fontSize: "0.85rem", fontWeight: 700, color }}>
        {value}
      </div>
    </div>
  );
}
