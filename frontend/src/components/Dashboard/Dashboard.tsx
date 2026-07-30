import { useMemo, useEffect, useState, useCallback, useRef, lazy, Suspense } from "react";
import DigitalTwin from "../DigitalTwin/DigitalTwin";
import BankDecisionPanel from "./BankDecisionPanel";
import ScoreGauge from "./ScoreGauge";
import RiskCards from "./RiskCards";

// Chargement différé de PropertyMap (react-leaflet peut causer des conflits d'import)
const PropertyMap = lazy(() => import("./PropertyMap"));

// Fallback : le JSON statique de démo (UNIQUEMENT pour la route publique)
import demoData from "../../../assessment_complet.json";

interface DashboardProps {
  sessionId: string | null;
  isBankRoute?: boolean;
}

export default function Dashboard({ sessionId, isBankRoute }: DashboardProps) {
  const [apiData, setApiData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCountRef = useRef(0);
  const MAX_POLLING_RETRIES = 40; // ~2 minutes (40 × 3s)

  // Nettoie le polling au démontage ou changement de session
  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }
    retryCountRef.current = 0;
  }, []);

  // Fonction de chargement (utilisée au montage et pour le retry)
  const loadAnalysis = useCallback(() => {
    // Nettoyer tout polling en cours
    if (pollingRef.current !== null) {
      clearTimeout(pollingRef.current);
      pollingRef.current = null;
    }

    if (!sessionId || sessionId === "demo-session-001") {
      setLoading(false);
      setError(null);
      setApiData(null);
      return;
    }

    // 1. Essayer le sessionStorage (cache rapide, vidé à la fermeture de l'onglet)
    const bankCacheKey = "typhoon_bank_" + sessionId;
    const cachedSession = sessionStorage.getItem(bankCacheKey);
    if (cachedSession) {
      try {
        const parsed = JSON.parse(cachedSession);
        // Ignorer les caches "processing" (ne pas afficher de vieilles données périmées)
        if (parsed && parsed.status !== "processing") {
          setApiData(parsed);
          setError(null);
          setLoading(false);
          retryCountRef.current = 0;
          return;
        }
      } catch { sessionStorage.removeItem(bankCacheKey); }
    }

    // 2. Essayer le localStorage (persistant — stocké par le formulaire)
    const localCacheKey = "typhoon_analysis_" + sessionId;
    const cachedLocal = localStorage.getItem(localCacheKey);
    if (cachedLocal) {
      try {
        const parsed = JSON.parse(cachedLocal);
        if (parsed && parsed.status !== "processing") {
          setApiData(parsed);
          sessionStorage.setItem(bankCacheKey, cachedLocal);
          setError(null);
          setLoading(false);
          retryCountRef.current = 0;
          return;
        }
      } catch { localStorage.removeItem(localCacheKey); }
    }

    // 3. Appel API si le préfixe est valide
    if (!sessionId.startsWith("session-")) return;

    setLoading(true);
    setError(null);
    fetch(`/api/analysis/${sessionId}`)
      .then(async res => {
        if (!res.ok) {
          if (res.status === 404) {
            // 404 au premier appel = analyse pas encore créée ou backend redémarré
            // On garde le statut "processing" du sessionStorage si présent
            throw new Error("Analyse introuvable sur le serveur (404).");
          }
          throw new Error(`Erreur serveur ${res.status}`);
        }
        return res.json();
      })
      .then(data => {
        if (data.status === "processing") {
          // Analyse encore en cours → programmer un polling dans 3 secondes
          retryCountRef.current += 1;
          if (retryCountRef.current > MAX_POLLING_RETRIES) {
            setError("L'analyse a dépassé le temps d'attente maximal. Veuillez réessayer.");
            setLoading(false);
            return;
          }
          setError(null);
          pollingRef.current = setTimeout(() => {
            loadAnalysis();
          }, 3000);
          return;
        }

        if (data.status === "error") {
          setError(data.error || "Erreur lors de l'analyse.");
          setApiData(null);
          setLoading(false);
          retryCountRef.current = 0;
          return;
        }

        // Analyse terminée avec données complètes
        setApiData(data);
        sessionStorage.setItem(bankCacheKey, JSON.stringify(data));
        localStorage.setItem(localCacheKey, JSON.stringify(data));
        setError(null);
        setLoading(false);
        retryCountRef.current = 0;
      })
      .catch(err => {
        console.warn("Erreur chargement session :", err.message);
        retryCountRef.current += 1;
        if (retryCountRef.current > MAX_POLLING_RETRIES) {
          setError("Impossible de charger l'analyse après plusieurs tentatives. Le serveur est peut-être indisponible.");
          setLoading(false);
          return;
        }
        // Si erreur : réessayer dans 5s
        pollingRef.current = setTimeout(() => {
          loadAnalysis();
        }, 5000);
      });
  }, [sessionId]); // stopPolling retiré des deps — appelé directement dans la fonction

  useEffect(() => {
    setApiData(null);
    setError(null);
    setLoading(true);
    retryCountRef.current = 0;
    loadAnalysis();

    // Nettoyage au démontage
    return () => {
      stopPolling();
    };
  }, [loadAnalysis]); // stopPolling retiré des deps — stable, pas besoin de le déclencher

  // Données effectives
  // - Mode Banque : UNIQUEMENT les données de l'API (pas de fallback démo)
  // - Mode Public : résultat API > JSON démo statique
  const data = isBankRoute ? apiData : (apiData || demoData);

  // Hook useMemo placé AVANT tout early return (Règles des Hooks React)
  const jumeauPayload = useMemo(() => {
    if (!data) return null;
    const zonesBackend = data.recommandations?.zones || {};
    const projectionsBackend = data.recommandations?.projection_2050?.zones || {};

    const defaultZone = { 
      risque: 20, 
      niveau: "faible", 
      alea_principal: "Sain", 
      justification: "Aucun risque majeur identifié pour cette exposition.", 
      recommandations: [] 
    };

    const zones2025 = {
      fondations: zonesBackend.fondations || defaultZone,
      murs_nord: zonesBackend.murs_nord || defaultZone,
      murs_sud: zonesBackend.murs_sud || defaultZone,
      murs_est: zonesBackend.murs_est || defaultZone,
      murs_ouest: zonesBackend.murs_ouest || defaultZone,
      toiture: zonesBackend.toiture || defaultZone,
      sous_sol: zonesBackend.sous_sol || defaultZone,
    };

    const zones2050: Record<string, any> = {};
    Object.keys(zones2025).forEach((key) => {
      const base = zones2025[key as keyof typeof zones2025];
      const proj = projectionsBackend[key as keyof typeof projectionsBackend];
      zones2050[key] = {
        ...base,
        risque: proj ? proj.risque_projete : base.risque,
        justification: proj ? proj.evolution : base.justification,
        niveau: proj ? (proj.risque_projete >= 60 ? "eleve" : "modere") : base.niveau,
      };
    });

    return {
      score_global: data.analyse_risques?.score?.global || 0,
      zones: zones2025,
      projection_2050: {
        score_global: data.recommandations?.projection_2050?.score_global || 0,
        zones: zones2050
      },
      geometrie: { largeur_m: 8.5, profondeur_m: 6.0, orientation_deg: 15 }
    };
  }, [data]);

  // Écran de chargement
  if (loading) {
    return (
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: "80vh", color: "#4da6ff", gap: 16 }}>
        <div style={{ fontSize: 40 }}>⏳</div>
        <div style={{ fontSize: 20, fontWeight: 700 }}>Analyse en cours...</div>
        <div style={{ fontSize: 14, color: "#7fb4e8" }}>Consultation Géorisques, DVF, ADEME et génération de la décision bancaire...</div>
      </div>
    );
  }

  // Écran d'erreur (avec bouton de retry)
  if (error) {
    return (
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: "70vh", gap: 20, color: "#8b949e", padding: "0 20px" }}>
        <div style={{ fontSize: 60 }}>⚠️</div>
        <h2 style={{ color: "#ff4d4f", margin: 0 }}>Erreur de chargement</h2>
        <p style={{ fontSize: 15, color: "#f0b2b2", textAlign: "center", maxWidth: 500, lineHeight: 1.5 }}>{error}</p>
        <div style={{ display: "flex", gap: 12 }}>
          <button
            onClick={() => {
              retryCountRef.current = 0;
              loadAnalysis();
            }}
            style={{
              padding: "10px 24px", borderRadius: 8, border: "none",
              background: "#4da6ff", color: "#04070c", fontSize: 14, fontWeight: 700,
              cursor: "pointer",
            }}
          >
            🔄 Réessayer
          </button>
          {isBankRoute && (
            <button
              onClick={() => window.location.href = "/bank"}
              style={{
                padding: "10px 24px", borderRadius: 8, border: "1px solid #30363d",
                background: "transparent", color: "#cfe8ff", fontSize: 14,
                cursor: "pointer",
              }}
            >
              Nouvelle analyse
            </button>
          )}
        </div>
      </div>
    );
  }

  // Mode Banque : pas de données disponibles (pas de sessionId)
  if (isBankRoute && !data) {
    return (
      <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", height: "70vh", gap: 20, color: "#8b949e" }}>
        <div style={{ fontSize: 60 }}>🏦</div>
        <h2 style={{ color: "#d29922", margin: 0 }}>Portail Bancaire — Analyse Crédit</h2>
        <p style={{ fontSize: 16, color: "#8b949e", textAlign: "center", maxWidth: 420 }}>
          Aucun dossier chargé. Lancez une nouvelle analyse via le formulaire pour générer une décision bancaire certifiée.
        </p>
        <button
          onClick={() => window.location.href = "/bank"}
          style={{
            padding: "12px 28px", borderRadius: 8, border: "1px solid #d29922",
            background: "rgba(210,153,34,0.15)", color: "#d29922",
            fontSize: 15, fontWeight: 700, cursor: "pointer",
          }}
        >
          📝 Nouvelle analyse
        </button>
        <div style={{ display: "flex", gap: 12 }}>
          <div style={{ padding: "8px 16px", borderRadius: 6, background: "rgba(210,153,34,0.1)", border: "1px solid #d29922", color: "#d29922", fontSize: 13 }}>✅ Données gouvernementales (BAN, ADEME, DVF)</div>
          <div style={{ padding: "8px 16px", borderRadius: 6, background: "rgba(77,166,255,0.1)", border: "1px solid #4da6ff", color: "#4da6ff", fontSize: 13 }}>✅ Score Climatique (Géorisques)</div>
        </div>
      </div>
    );
  }

  if (isBankRoute) {
    return (
      <div className="dashboard" style={{ padding: "30px", maxWidth: "1000px", margin: "0 auto" }}>
        <header style={{ marginBottom: "30px", borderBottom: "2px solid #30363d", paddingBottom: "20px" }}>
          <h2 style={{ color: "#d29922", margin: "0 0 8px 0", fontSize: "24px" }}>🏦 Espace Agent Analyse Crédit</h2>
          <p style={{ color: "#8b949e", margin: 0, fontSize: "16px" }}>
            Évaluation automatisée du risque pour : <strong style={{ color: "#e6edf3" }}>{data.adresse}</strong>
          </p>
        </header>

        {data.decision_bancaire ? (
          <BankDecisionPanel
            decision={data.decision_bancaire}
            adresse={data.adresse || ""}
            typeBien={data.formulaire_client?.type_bien || "Maison"}
            surface={data.formulaire_client?.surface || 100}
            sessionId={sessionId || undefined}
          />
        ) : (
          <div style={{ padding: "20px", background: "rgba(210,153,34,0.1)", border: "1px solid #d29922", borderRadius: "8px", color: "#d29922", textAlign: "center" }}>
            Aucune décision bancaire générée pour ce dossier.
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="dashboard" style={{ padding: "20px" }}>
      <header className="dashboard-header" style={{ marginBottom: "20px" }}>
        <h2 style={{ color: "#4da6ff", margin: "0 0 5px 0" }}>Diagnostic de résilience climatique</h2>
        <p className="dashboard-address" style={{ color: "#e8f4ff", margin: 0, fontSize: "16px" }}>
          📍 {data.adresse}
        </p>
      </header>

      <div className="dashboard-grid" style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
        
        {/* Ligne 1 : Résumé rapide (Scores statiques) */}
        <div className="dashboard-row" style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
          <div style={{ flex: "1 1 280px", minWidth: 280 }}>
            <ScoreGauge score={data.resume.score_global} niveau={data.resume.niveau_risque} />
          </div>
          <div style={{ flex: "1 1 400px", minWidth: 320 }}>
            <Suspense fallback={<div style={{ height: 250, background: "var(--color-bg)", borderRadius: "var(--radius-sm)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-text-secondary)", fontSize: 14 }}>Chargement de la carte...</div>}>
              <PropertyMap lat={data.coordonnees.latitude} lng={data.coordonnees.longitude} adresse={data.adresse} />
            </Suspense>
          </div>
        </div>

        {/* Ligne 2 : LE JUMEAU NUMÉRIQUE 3D */}
        <div className="dashboard-row" style={{ display: "flex", gap: "20px", height: "600px" }}>
          <RiskCards scores={data.analyse_risques.scores_par_alea} dominants={data.risques_dominants || []} />
          
          <div style={{ flex: 1, background: "#04070c", borderRadius: "12px", border: "1px solid #1c5a9c", overflow: "hidden" }}>
            {/* On injecte l'adaptateur dans la 3D */}
            <DigitalTwin payload={jumeauPayload} />
          </div>
        </div>

        {/* Ligne 3 : Synthèse financière */}
        <div style={{ background: "rgba(6, 14, 26, 0.8)", padding: "20px", borderRadius: "12px", border: "1px solid #1c5a9c", color: "white" }}>
          <h3 style={{ color: "#4da6ff", marginTop: 0 }}>Synthèse de la Rénovation</h3>
          <p>Coût total estimé : <strong>{data.resume.cout_total_travaux}</strong></p>
          <p>Aides mobilisables (Anah, Fonds Barnier) : <strong style={{ color: "#3fb950" }}>{data.resume.aides_mobilisables}</strong></p>
          <p style={{ fontSize: "18px" }}>Reste à charge net : <strong>{data.resume.reste_a_charge_net}</strong></p>
        </div>

      </div>
    </div>
  );
}