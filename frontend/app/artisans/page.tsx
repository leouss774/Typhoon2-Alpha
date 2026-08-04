import type { Metadata } from "next";
import ArtisanMatcher from "./ArtisanMatcher";

export const metadata: Metadata = {
  title: "Typhoon — Matching Artisans RGE & Professionnels",
  description:
    "Trouvez des entreprises RGE (Reconnu Garant de l'Environnement) et des professionnels spécialisés pour chaque recommandation de travaux.",
};

export default function ArtisansPage() {
  return <ArtisanMatcher />;
}
