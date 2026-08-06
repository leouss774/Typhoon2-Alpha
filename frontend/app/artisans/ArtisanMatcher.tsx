"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { rechercherArtisans, getDiagnosticMatchingData, getDomaines } from "./api";
import { parserRecommandations, formatContact } from "./utils";
import type {
  ArtisanMatchingResponse,
  DomaineInfo,
  Entreprise,
  RecommandationTraitee,
} from "./types";
import styles from "./ArtisanMatcher.module.css";

/* ── Presets ── */
const PRESETS = [
  { label: "Rénovation thermique + RGA", recos: "isolation_combles\nventilation\nisolation_murs_exterieur\nrga_geotechnique" },
  { label: "Isolation + Menuiseries", recos: "isolation_combles\nmenuiseries\naudit_energetique" },
  { label: "Risques sismique + radon", recos: "sismique_structure\nruissellement_drainage\nradon_etancheite" },
  { label: "Tous non-RGE", recos: "rga_geotechnique\nsismique_structure\nruissellement_drainage" },
];

type Tri = "score" | "distance" | "nom";
type Filtre = "all" | "rge" | "non_rge";

/* ── Score helpers ── */
const scoreColor = (s: number | undefined | null) =>
  s == null ? "var(--muted)" : s >= 80 ? "var(--success)" : s >= 50 ? "var(--warning)" : "var(--danger)";

const scoreStars = (s: number | undefined | null) => {
  if (s == null) return "☆☆☆☆☆";
  const filled = Math.round(s / 20);
  return "★".repeat(filled) + "☆".repeat(5 - filled);
};

function ScoreBadge({ score }: { score: number | undefined | null }) {
  const color = scoreColor(score);
  const pct = score != null ? Math.min(score, 100) : 0;
  return (
    <div className={styles.scoreBadge}>
      <div className={styles.scoreBar}>
        <div
          className={styles.scoreBarFill}
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <div className={styles.scoreRow}>
        <span className={styles.scoreStars} style={{ color }}>{scoreStars(score)}</span>
        <span className={styles.scoreNum} style={{ color }}>
          {score != null ? score : "N/A"}<span className={styles.scoreTotal}>/100</span>
        </span>
      </div>
    </div>
  );
}

function AncienneteBadge({ ans }: { ans: number | undefined | null }) {
  if (ans == null) return <span className={styles.naBadge}>—</span>;
  const color = ans >= 10 ? "var(--success)" : ans >= 5 ? "var(--warning)" : "var(--muted)";
  return (
    <span className={styles.ancienneteBadge} style={{ background: color }}>
      {ans} an{ans > 1 ? "s" : ""}
    </span>
  );
}

function SiteBadge({ url }: { url?: string | null }) {
  if (!url) return <span className={styles.naBadge}>—</span>;
  return (
    <a href={url} target="_blank" rel="noopener" className={styles.siteBadge} title={url}>
      ✅ Site pro
    </a>
  );
}

/* ── Sous-composant : Ligne entreprise ── */
function EntrepriseRow({ ent, idx, subIdx }: { ent: Entreprise; idx: number; subIdx: number }) {
  const [showDetails, setShowDetails] = useState(false);
  const contact = formatContact(ent.telephone, ent.email);
  const sc = ent.score_objectif_sur_100;
  const adr = ent.adresse || "Adresse non communiquée";
  const distKm = ent.distance_km;

  let distClass = "";
  let distLabel = "";
  if (distKm != null) {
    if (distKm < 10) { distClass = styles.distanceClose; distLabel = `${distKm.toFixed(1)} km`; }
    else if (distKm < 30) { distClass = styles.distanceMid; distLabel = `${distKm.toFixed(1)} km`; }
    else { distClass = styles.distanceFar; distLabel = `${distKm.toFixed(1)} km`; }
  }

  const NB_COLS = 7;

  return (
    <>
      <tr className={styles.entRow}>
        <td className={styles.entName}>
          {ent.nom_entreprise || "—"}
          {distKm != null && <span className={`${styles.distBadge} ${distClass}`}>{distLabel}</span>}
        </td>
        <td className={styles.scoreCell}>
          <ScoreBadge score={sc} />
          {ent.details_score && ent.details_score.length > 0 && (
            <button className={styles.expandBtn} onClick={() => setShowDetails(!showDetails)} aria-label="Détails" title="Détails du score">
              {showDetails ? "▲" : "▼"}
            </button>
          )}
        </td>
        <td className={styles.adrCell}>
          {adr}<br /><small className={styles.commune}>{ent.code_postal || ""} {ent.commune || ""}</small>
        </td>
        <td className={styles.ancienneteCell}>
          <AncienneteBadge ans={ent.anciennete_rge_ans} />
        </td>
        <td className={styles.siteCell}>
          <SiteBadge url={ent.site_internet || ent.lien_fiche_officielle} />
        </td>
        <td className={styles.contactCell}>
          {contact.isEmail && contact.href ? <a href={contact.href}>{contact.text}</a> : contact.text}
        </td>
        <td className={styles.telCell}>
          {ent.telephone ? (
            <a href={`tel:${ent.telephone.replace(/\s/g, '')}`} className={styles.telLink}>
              📞 {ent.telephone}
            </a>
          ) : <span className={styles.naBadge}>—</span>}
        </td>
      </tr>
      {showDetails && ent.details_score && (
        <tr className={styles.detailRow}>
          <td colSpan={NB_COLS}>
            <div className={styles.scoreDetail}>
              <strong>Détail du score :</strong>
              <ul>{ent.details_score.map((d, j) => <li key={j}>{d}</li>)}</ul>
            </div>
          </td>
        </tr>
      )}
      {/* Carte mobile (visible <768px) */}
      <tr className={styles.mobileCard}>
        <td colSpan={NB_COLS}>
          <div className={styles.mobileEnt}>
            <div className={styles.mobileEntHeader}>
              <strong>{ent.nom_entreprise || "—"}</strong>
              <div className={styles.mobileScore}>
                <ScoreBadge score={sc} />
                {distKm != null && <span className={`${styles.distBadge} ${distClass}`}>{distLabel}</span>}
              </div>
            </div>
            <div className={styles.mobileEntBody}>
              <div>{adr}</div>
              <div className={styles.mobileMetaRow}>
                <span><strong>Ancienneté RGE :</strong> <AncienneteBadge ans={ent.anciennete_rge_ans} /></span>
                <span><strong>Site :</strong> <SiteBadge url={ent.site_internet || ent.lien_fiche_officielle} /></span>
              </div>
              <div className={styles.mobileMetaRow}>
                <span className={styles.contactCell}>{contact.isEmail ? <a href={contact.href!}>{contact.text}</a> : contact.text}</span>
                {ent.telephone && (
                  <span><a href={`tel:${ent.telephone.replace(/\s/g, '')}`} className={styles.telLink}>📞 {ent.telephone}</a></span>
                )}
              </div>
            </div>
            {ent.details_score && ent.details_score.length > 0 && (
              <button className={styles.expandBtn} onClick={() => setShowDetails(!showDetails)}>
                {showDetails ? "▲" : "▼"} Détails du score
              </button>
            )}
            {showDetails && ent.details_score && (
              <div className={styles.scoreDetail}>
                <ul>{ent.details_score.map((d, j) => <li key={j}>{d}</li>)}</ul>
              </div>
            )}
          </div>
        </td>
      </tr>
    </>
  );
}

/* ── Sous-composant : Carte recommandation ── */
function RecoCard({ item, idx, animDelay }: { item: RecommandationTraitee; idx: number; animDelay: number }) {
  const isRge = item.categorie === "rge";
  const badgeClass = isRge ? "badge-rge" : item.categorie === "non_rge" ? "badge-non-rge" : "badge-inconnue";
  const titre = item.libelle || item.domaine_recherche || item.cle || "Recommandation";
  const entreprises = item.entreprises || [];
  const annuaire = item.annuaire_reference;

  return (
    <div className={`${styles.recoCard}`} style={{ animationDelay: `${animDelay}ms` }}>
      <div className={styles.cardHead}>
        <h3 className={styles.recoTitle}>{titre}</h3>
        <span className={`badge ${badgeClass}`}>{isRge ? "RGE" : "Non-RGE"}</span>
      </div>
      <div className={styles.recoMeta}>
        <strong>Clé :</strong> {item.cle || "—"} · <strong>Priorité :</strong> {item.priorite || "Non renseignée"}
        {item.zone_origine && <> · <strong>Zone :</strong> {item.zone_origine}</>}
        {item.risques_origine?.length ? <> · <strong>Risques :</strong> {item.risques_origine.join(", ")}</> : null}
      </div>

      {annuaire?.url && (
        <div className="annuaire-info">
          <strong>Annuaire :</strong> {annuaire.organisme}<br />
          <a href={annuaire.url} target="_blank" rel="noopener">{annuaire.url}</a>
          {annuaire.note && <span className="note">{annuaire.note}</span>}
        </div>
      )}

      {item.erreur && (
        <div className="error-card"><div className="err-title">⚠️ {item.erreur}</div></div>
      )}

      {entreprises.length > 0 ? (
        <>
          {/* Desktop table */}
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead><tr><th>Entreprise</th><th>Score</th><th>Adresse</th><th>Ancienneté RGE</th><th>Site web</th><th>Contact</th><th>Tél.</th></tr></thead>
              <tbody>{entreprises.map((ent, i) => <EntrepriseRow key={`${ent.siret || ent.siren || ''}-${i}`} ent={ent} idx={idx} subIdx={i} />)}</tbody>
            </table>
          </div>
        </>
      ) : !item.erreur ? (
        <div className="empty-state">Aucune entreprise trouvée pour cette recommandation.</div>
      ) : null}

      {item.mesure_originale && (
        <div className={styles.recoExtra}>
          <strong>Mesure :</strong> <em>{item.mesure_originale}</em>
        </div>
      )}
      {item.cout_estime && (
        <div className={styles.recoExtra}>
          💰 <strong>Coût estimé :</strong>{" "}
          {item.cout_estime.montant_min != null && item.cout_estime.montant_max != null
            ? `${item.cout_estime.montant_min.toLocaleString()}€ – ${item.cout_estime.montant_max.toLocaleString()}€`
            : "Non estimé"}
          {item.cout_estime.fiabilite && <em> ({item.cout_estime.fiabilite})</em>}
        </div>
      )}
    </div>
  );
}

/* ＝＝＝＝＝＝＝＝＝  COMPOSANT PRINCIPAL  ＝＝＝＝＝＝＝＝＝ */
export default function ArtisanMatcher() {
  const [adresse, setAdresse] = useState("");
  const [codePostal, setCodePostal] = useState("");
  const [recosRaw, setRecosRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingStep, setLoadingStep] = useState(0);
  const [results, setResults] = useState<ArtisanMatchingResponse | null>(null);
  const [domaines, setDomaines] = useState<Record<string, DomaineInfo> | null>(null);
  const [showDomaines, setShowDomaines] = useState(false);
  const [filtre, setFiltre] = useState<Filtre>("all");
  const [tri, setTri] = useState<Tri>("score");
  const [error, setError] = useState<string | null>(null);
  const [showTips, setShowTips] = useState(false);
  const resultsRef = useRef<HTMLDivElement>(null);
  const autoSearchStarted = useRef(false);

  /* Charger resultat_enrichi.json et lancer immédiatement le matching. */
  useEffect(() => {
    if (autoSearchStarted.current) return;
    autoSearchStarted.current = true;

    const loadAndSearch = async () => {
      setLoading(true);
      setError(null);
      try {
        const diagnostic = await getDiagnosticMatchingData();
        const raw = diagnostic.recommandations
          .map((reco) => reco.cle || reco.mesure || "")
          .filter(Boolean)
          .join("\n");

        setAdresse(diagnostic.adresse);
        setCodePostal(diagnostic.code_postal);
        setRecosRaw(raw);

        const data = await rechercherArtisans(
          diagnostic.adresse,
          diagnostic.recommandations,
          10,
          diagnostic.code_postal || undefined
        );
        setResults(data);
        setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 200);
      } catch (err: any) {
        setError(err.message || "Impossible de charger resultat_enrichi.json.");
      } finally {
        setLoading(false);
      }
    };

    void loadAndSearch();
  }, []);

  /* Charger domaines */
  useEffect(() => { getDomaines().then(setDomaines).catch(() => {}); }, []);

  /* Auto CP */
  const handleAdresseChange = useCallback((val: string) => {
    setAdresse(val);
    const m = val.match(/\b(\d{5})\b/);
    if (m) setCodePostal(m[1]);
  }, []);

  /* Loading animation steps */
  useEffect(() => {
    if (!loading) { setLoadingStep(0); return; }
    const steps = [
      "Géocodage de l'adresse…",
      "Recherche RGE (ADEME)…",
      "Recherche non-RGE (api.gouv.fr)…",
      "Calcul des scores et distances…",
      "Génération du rapport…",
    ];
    const interval = setInterval(() => {
      setLoadingStep((s) => Math.min(s + 1, steps.length - 1));
    }, 1800);
    return () => clearInterval(interval);
  }, [loading]);

  /* Recherche */
  const handleSearch = useCallback(async () => {
    const adr = adresse.trim(), cp = codePostal.trim(), raw = recosRaw.trim();
    if (!adr && !cp) { setError("Saisissez une adresse ou un code postal."); return; }
    if (!raw) { setError("Saisissez au moins une recommandation."); return; }

    const codePostalFinal = cp || (adr.match(/\b(\d{5})\b/) || [""])[1];
    const adresseFinale = adr || `${codePostalFinal} France`;
    const recommandations = parserRecommandations(raw.split("\n"), domaines);

    /* Sauvegarder */
    try { localStorage.setItem("typhoon_last_search", JSON.stringify({ adresse: adr, codePostal: cp, recosRaw: raw })); } catch { /* */ }

    setLoading(true);
    setError(null);
    setResults(null);

    try {
      const data = await rechercherArtisans(adresseFinale, recommandations, 10, codePostalFinal || undefined);
      setResults(data);
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 200);
    } catch (err: any) {
      const msg = err.message?.includes("fetch") || err.message?.includes("NetworkError")
        ? "Impossible de contacter le serveur backend. Lancer le backend : cd backend && python -m uvicorn app.main:app --reload --port 8765"
        : err.message || "Erreur inconnue";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [adresse, codePostal, recosRaw, domaines]);

  /* Raccourci clavier Ctrl+Enter */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { handleSearch(); }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [handleSearch]);

  /* Reset */
  const reset = useCallback(() => {
    setAdresse(""); setCodePostal(""); setRecosRaw(""); setResults(null); setError(null); setFiltre("all");
    try { localStorage.removeItem("typhoon_last_search"); } catch { /* */ }
  }, []);

  /* Ajouter domaine */
  const addDomaine = useCallback((cle: string) => {
    const lines = recosRaw.split("\n").map(l => l.trim());
    if (!lines.includes(cle)) setRecosRaw([...lines, cle].filter(Boolean).join("\n"));
    setShowDomaines(false);
  }, [recosRaw]);

  /* Export JSON */
  const exportJSON = useCallback(() => {
    if (!results) return;
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "artisans_match.json"; a.click();
    URL.revokeObjectURL(url);
  }, [results]);

  /* Export CSV */
  const exportCSV = useCallback(() => {
    if (!results) return;
    const rows = [["Recommandation", "Catégorie", "Entreprise", "Score", "Distance (km)", "Adresse", "Contact", "Site"]];
    for (const r of results.recommandations_traitees) {
      for (const e of r.entreprises) {
        rows.push([
          r.libelle || r.domaine_recherche || r.cle || "",
          r.categorie,
          e.nom_entreprise || "",
          String(e.score_objectif_sur_100 ?? ""),
          e.distance_km != null ? String(e.distance_km) : "",
          `${e.adresse || ""} ${e.code_postal || ""} ${e.commune || ""}`,
          e.telephone || e.email || "",
          e.lien_fiche_officielle || "",
        ]);
      }
    }
    const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "artisans_match.csv"; a.click();
    URL.revokeObjectURL(url);
  }, [results]);

  /* Filtrer et trier */
  const recosFiltrees = (results?.recommandations_traitees ?? [])
    .filter(r => filtre === "all" ? true : r.categorie === filtre)
    .map(r => ({
      ...r,
      entreprises: [...r.entreprises].sort((a, b) => {
        if (tri === "score") return (b.score_objectif_sur_100 ?? 0) - (a.score_objectif_sur_100 ?? 0);
        if (tri === "distance") return (a.distance_km ?? 999) - (b.distance_km ?? 999);
        return (a.nom_entreprise ?? "").localeCompare(b.nom_entreprise ?? "");
      }),
    }));

  const compteur = results?.resume.details_categories ?? {};

  const loadingSteps = [
    "Géocodage de l'adresse…",
    "Recherche RGE (ADEME)…",
    "Recherche non-RGE (api.gouv.fr)…",
    "Calcul des scores et distances…",
    "Génération du rapport…",
  ];

  return (
    <div className={styles.page}>
      {/* Hero */}
      <section className={styles.hero}>
        <h1 className={styles.heroTitle}>🔨 Matching Artisans optimisé</h1>
        <p className={styles.heroDesc}>
          Recherche intelligente avec <strong>scoring par distance réelle</strong>, cache, parallélisation.
          Données ADEME + Recherche d&apos;Entreprises.
        </p>
      </section>

      {/* Loading */}
      {loading && (
        <div className={styles.loadingSection}>
          <div className="loading-bar-track"><div className="loading-bar-fill" style={{ width: `${(loadingStep / (loadingSteps.length - 1)) * 90}%` }} /></div>
          <div className={styles.loadingText}>
            <span className={styles.spinner} />
            {loadingSteps[Math.min(loadingStep, loadingSteps.length - 1)]}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className={styles.errorSection}>
          <div className="error-card"><div className="err-title">❌ {error}</div></div>
        </div>
      )}

      {/* Skeleton pendant le loading */}
      {loading && (
        <div className={styles.skeletonSection}>
          {[1, 2, 3].map(i => (
            <div key={i} className={styles.skeletonCard}>
              <div className={styles.skelLine} style={{ width: "60%" }} />
              <div className={styles.skelLine} style={{ width: "40%" }} />
              <div className={styles.skelLine} style={{ width: "80%" }} />
              <div className={styles.skelTable}>
                {[1, 2, 3].map(j => <div key={j} className={styles.skelRow} />)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Résultats */}
      {results && !loading && (
        <div ref={resultsRef}>
          {/* Info géocodage */}
          {results.geocoding && (
            <div className={styles.geoInfo}>
              📍 {results.geocoding.label} · {results.geocoding.city} ({results.geocoding.postcode})
              · <code>{results.geocoding.lat.toFixed(5)}, {results.geocoding.lon.toFixed(5)}</code>
              {results.geocoding.score < 0.5 && <span className={styles.geoWarn}> ⚠️ Précision: {Math.round(results.geocoding.score * 100)}%</span>}
            </div>
          )}

          {/* Summary */}
          <section className={styles.summary}>
            <div className={styles.summaryCard}>
              <span className={styles.summaryNum}>{results.resume.total_recommandations_traitees}</span>
              <span className={styles.summaryDesc}>Recommandations</span>
            </div>
            <div className={styles.summaryCard}>
              <span className={styles.summaryNum}>{results.resume.total_entreprises_trouvees}</span>
              <span className={styles.summaryDesc}>Entreprises trouvées</span>
            </div>
            <div className={styles.summaryCard}>
              <span className={`${styles.summaryNum} ${styles.rgeCount}`}>{compteur.rge || 0}</span>
              <span className={styles.summaryDesc}>RGE</span>
            </div>
            <div className={styles.summaryCard}>
              <span className={`${styles.summaryNum} ${styles.nonrgeCount}`}>{compteur.non_rge || 0}</span>
              <span className={styles.summaryDesc}>Non-RGE</span>
            </div>
          </section>

          {/* Toolbar */}
          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              {(["all", "rge", "non_rge"] as const).map(f => (
                <button key={f} className={`${styles.toolBtn} ${filtre === f ? styles.toolActive : ""}`}
                  onClick={() => setFiltre(f)}>
                  {f === "all" ? "Tout" : f === "rge" ? "RGE" : "Non-RGE"}
                  <span className={styles.toolCount}>
                    {f === "all" ? results.recommandations_traitees.length
                      : results.recommandations_traitees.filter(r => r.categorie === f).length}
                  </span>
                </button>
              ))}
            </div>
            <div className={styles.toolbarRight}>
              <label className={styles.sortLabel}>Trier par :</label>
              <select className={styles.sortSelect} value={tri} onChange={e => setTri(e.target.value as Tri)}>
                <option value="score">Score</option>
                <option value="distance">Distance</option>
                <option value="nom">Nom A-Z</option>
              </select>
              <button className="btn btn-ghost btn-sm" onClick={exportJSON} title="Exporter en JSON">📄 JSON</button>
              <button className="btn btn-ghost btn-sm" onClick={exportCSV} title="Exporter en CSV">📊 CSV</button>
            </div>
          </div>

          {/* Navigation rapide */}
          <div className={styles.quickNav}>
            <span className={styles.quickNavLabel}>📋 Aller à :</span>
            {recosFiltrees.map((item, idx) => (
              <a key={item.cle || idx} href={`#reco-${idx}`} className={styles.quickNavLink}>
                {idx + 1}. {item.libelle || item.domaine_recherche || item.cle || "Recommandation"}
              </a>
            ))}
          </div>

          {/* Cards */}
          {recosFiltrees.length > 0 ? (
            recosFiltrees.map((item, idx) => (
                <RecoCard key={`${item.cle || "recommandation"}-${idx}`} item={item} idx={idx} animDelay={idx * 80} />
            ))
          ) : (
            <div className="empty-state">Aucune recommandation ne correspond à ce filtre.</div>
          )}

          {/* Footer info */}
          <div className={styles.resultFooter}>
            {results.recommandations_traitees.length} recommandation(s) · {results.resume.total_entreprises_trouvees} entreprise(s)
            {results.adresse && <> · {results.adresse}</>}
          </div>
        </div>
      )}
    </div>
  );
}
