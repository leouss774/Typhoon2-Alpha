import type { Metadata } from "next";
import EconomieDashboard from "./EconomieDashboard";

export const metadata: Metadata = {
  title: "Typhoon — Retour sur investissement des travaux de résilience",
  description:
    "Le volet économique du diagnostic : coût sourcé des travaux, bénéfices assurantiels, perte annuelle moyenne et temps de retour — aucun montant inventé.",
};

export default function EconomiePage() {
  return <EconomieDashboard />;
}
