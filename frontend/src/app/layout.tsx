import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-body",
});

const sourceSerif = Source_Serif_4({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-head",
  weight: ["500", "600", "700"],
});

export const metadata: Metadata = {
  title: "Typhoon — Diagnostic Climatique Immobilier",
  description:
    "Analyse multi-agents de résilience climatique pour biens immobiliers. Jumeau numérique 3D, scoring des risques, décision bancaire.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fr" className={`${inter.variable} ${sourceSerif.variable}`}>
      <body style={{ fontFamily: "var(--font-body)" }}>
        <div className="app">
          <header className="app-header">
            <a href="/" style={{ textDecoration: "none" }}>
              <div className="app-logo">
                <div className="mark">
                  <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 2 4 5v6c0 5 3.5 9 8 11 4.5-2 8-6 8-11V5z"/>
                    <path d="m9 12 2 2 4-4"/>
                  </svg>
                </div>
                <div>
                  <div className="name">Typhoon</div>
                  <div className="baseline">Diagnostic Climatique</div>
                </div>
              </div>
            </a>
            <nav style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <a href="/" className="btn-ghost" style={{ fontSize: 13 }}>
                Dashboard
              </a>
              <a href="/bank" className="btn-ghost" style={{ fontSize: 13 }}>
                Accès Banquier
              </a>
            </nav>
          </header>
          <main style={{ flex: 1 }}>{children}</main>
        </div>
      </body>
    </html>
  );
}
