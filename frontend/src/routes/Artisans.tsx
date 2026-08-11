// =============================================================================
//   TYPHOON — /artisans : recherche d'artisans RGE / métiers locaux pour les
//   travaux recommandés par le diagnostic.
//
//   Source des recommandations (deux chemins) :
//     1. sessionStorage 'typhoon_artisan_handoff' — écrit par le moteur du
//        /jumeau (panneau zone → bouton « Rechercher des artisans »), qui
//        regroupe adresse + recommandations structurées par zone, puis
//        redirige ici. C'est le flux normal prévu par le routing existant.
//     2. Formulaire d'adresse sur place : POST /diagnostic/fast puis
//        /diagnostic/recommandations (même chaîne que /jumeau) pour les
//        visites directes sans handoff.
//
//   Le matching réutilise matchArtisans() exporté par scene-engine.js (même
//   requête /artisans/match, zones en tableau de dicts, rendu des groupes et
//   des cartes entreprises avec contact).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { API } from '../zone/config';
import '../styles/artisans.css';
// Les classes artisan-* injectées par matchArtisans sont stylées dans
// jumeau.css (dark M3) ; on l'importe pour ces classes (scopage via
// .artisans-app pour les tokens).
import '../styles/jumeau.css';

interface HandoffReco {
  mesure?: string;
  zone?: string;
  risques?: string[];
  travaux?: string;
}

interface ZoneSearch {
  zone: string;
  alea: string;
  recommandations: { mesure?: string; travaux?: string }[];
}

interface GeocodeSuggestion {
  label: string;
  context?: string;
}

export function Artisans() {
  const [zones, setZones] = useState<ZoneSearch[]>([]);
  const [adresse, setAdresse] = useState('');
  const [ready, setReady] = useState(false);

  // Formulaire (repli : visite directe sans handoff)
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const banTimeout = useRef<number | null>(null);

  /* ── Lecture du handoff (flux /jumeau → /artisans) ── */
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('typhoon_artisan_handoff');
      if (!raw) return;
      const handoff = JSON.parse(raw);
      const grouped = new Map<string, { alea: string; recos: { mesure?: string; travaux?: string }[] }>();
      (handoff.recommandationsStructurees || []).forEach((r: HandoffReco) => {
        const key = String(r.zone || 'zone').toLowerCase();
        if (!grouped.has(key)) grouped.set(key, { alea: (r.risques || []).join(' '), recos: [] });
        grouped.get(key)!.recos.push({ mesure: r.mesure, travaux: r.travaux });
      });
      const zoneList: ZoneSearch[] = Array.from(grouped.entries()).map(([zone, v]) => ({
        zone,
        alea: v.alea || zone,
        recommandations: v.recos.filter((r) => r.mesure || r.travaux),
      }));
      if (zoneList.length) {
        setAdresse(handoff.adresse || '');
        setZones(zoneList);
        setReady(true);
      }
    } catch (e) {
      console.warn('Handoff artisans illisible :', e);
    }
  }, []);

  /* ── BAN autocomplétion (même pattern que /zone et /jumeau) ── */
  function fetchSuggestions(q: string) {
    fetch(`${API}/api/geocode/search?q=${encodeURIComponent(q)}&limit=5`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error(`HTTP ${resp.status}`))))
      .then((data) => {
        setSuggestions(data.results || []);
        setSuggestionsOpen(true);
      })
      .catch(() => setSuggestionsOpen(false));
  }

  function onQueryChange(value: string) {
    setQuery(value);
    setError(null);
    if (banTimeout.current) window.clearTimeout(banTimeout.current);
    if (value.trim().length < 3) {
      setSuggestionsOpen(false);
      return;
    }
    banTimeout.current = window.setTimeout(() => fetchSuggestions(value.trim()), 220);
  }

  /* ── Diagnostic sur place (visite directe) : fast puis recommandations ── */
  async function runDiagnostic(address: string) {
    const value = address.trim();
    if (!value) {
      setError('Saisissez une adresse.');
      return;
    }
    setSuggestionsOpen(false);
    setError(null);
    setLoading(true);
    try {
      const resp = await fetch(`${API}/diagnostic/fast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ adresse: value }),
      });
      if (!resp.ok) {
        let detail = `Erreur ${resp.status}`;
        try {
          const err = await resp.json();
          detail = err.detail?.detail || err.detail?.error || JSON.stringify(err.detail) || detail;
        } catch {
          /* corps non-JSON */
        }
        throw new Error(detail);
      }
      const fast = await resp.json();
      // Les recommandations nécessitent le second appel (RAG + LLM) ; on
      // garde la liste des zones de risque dès maintenant pour afficher les
      // sections, et on complète zone par zone.
      const resume = fast._resume;
      const recoResp = await fetch(`${API}/diagnostic/recommandations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          building_data: resume.building_data,
          risk_scores: resume.risk_scores,
          formulaire: resume.formulaire,
        }),
      });
      if (!recoResp.ok) {
        let detail = `Erreur ${recoResp.status}`;
        try {
          const err = await recoResp.json();
          detail = err.detail?.detail || err.detail?.error || JSON.stringify(err.detail) || detail;
        } catch {
          /* corps non-JSON */
        }
        throw new Error(detail);
      }
      const contract = await recoResp.json();
      const zoneList: ZoneSearch[] = Object.entries(contract.zones || {})
        .map(([zone, z]) => {
          const zd = z as {
            alea_principal?: string;
            recommandations?: { mesure?: string; travaux?: string }[];
          };
          return {
            zone,
            alea: zd.alea_principal || zone,
            recommandations: (zd.recommandations || []).filter((r) => r.mesure || r.travaux),
          };
        })
        .filter((z) => z.recommandations.length > 0);
      setAdresse(contract.adresse || value);
      setZones(zoneList);
      setReady(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function pickSuggestion(s: GeocodeSuggestion) {
    setQuery(s.label);
    setSuggestionsOpen(false);
    void runDiagnostic(s.label);
  }

  /* ── Lancement d'une recherche par zone (réutilise matchArtisans) ── */
  function searchZone(zone: ZoneSearch, container: HTMLDivElement, button: HTMLButtonElement) {
    void import('../jumeau/scene-engine').then(({ matchArtisans }) =>
      matchArtisans({
        apiBase: API,
        adresse,
        zoneName: zone.zone,
        data: { alea_principal: zone.alea, recommandations: zone.recommandations },
        container,
        button,
      }),
    );
  }

  return (
    <main className="artisans-app">
      <header className="artisans-header">
        <Link to="/jumeau" className="artisans-back" aria-label="Retour au jumeau numérique">
          <md-icon aria-hidden="true">arrow_back</md-icon>
        </Link>
        <div className="artisans-title">
          <md-icon aria-hidden="true">handyman</md-icon>
          <div>
            <h1>Artisans RGE &amp; métiers locaux</h1>
            <p>Professionnels qualifiés pour réaliser les travaux recommandés par le diagnostic.</p>
          </div>
        </div>
        {adresse && <div className="artisans-addr">Bien : {adresse}</div>}
      </header>

      {!ready ? (
        /* ── État initial : formulaire (ou renvoi vers /jumeau) ── */
        <section className="artisans-empty">
          <md-icon>search</md-icon>
          <h2>Lancez un diagnostic pour trouver des artisans</h2>
          <p>
            Le matching associe des entreprises qualifiées aux travaux recommandés. Saisissez une
            adresse pour générer le diagnostic, ou passez par le{' '}
            <Link to="/jumeau">jumeau numérique 3D</Link>.
          </p>

          <div className="artisans-form">
            <div className={`artisans-pill${error ? ' artisans-pill-error' : ''}`}>
              <md-icon className="artisans-pill-icon" aria-hidden="true">search</md-icon>
              <input
                type="search"
                placeholder="Adresse du bien…"
                autoComplete="off"
                spellCheck={false}
                inputMode="search"
                aria-label="Adresse du bien"
                value={query}
                onChange={(e) => onQueryChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') void runDiagnostic(query);
                }}
                onBlur={() => window.setTimeout(() => setSuggestionsOpen(false), 180)}
              />
              {loading ? (
                <span className="artisans-spinner" aria-hidden="true" />
              ) : (
                <md-icon-button
                  className="artisans-send"
                  aria-label="Diagnostiquer cette adresse"
                  onClick={() => void runDiagnostic(query)}
                >
                  <md-icon>arrow_forward</md-icon>
                </md-icon-button>
              )}
            </div>

            {suggestionsOpen && suggestions.length > 0 && (
              <div className="artisans-suggestions">
                <md-list>
                  {suggestions.map((s, i) => (
                    <md-list-item
                      key={i}
                      onMouseDown={(e: { preventDefault: () => void }) => e.preventDefault()}
                      onClick={() => pickSuggestion(s)}
                    >
                      <span slot="headline">{s.label}</span>
                      {s.context ? <span slot="supporting-text">{s.context}</span> : null}
                    </md-list-item>
                  ))}
                </md-list>
              </div>
            )}

            {loading && (
              <div className="artisans-loading" role="status">
                <md-linear-progress indeterminate></md-linear-progress>
                <span>Diagnostic + recommandations en cours (RAG Mistral)…</span>
              </div>
            )}
            {error && (
              <div className="artisans-error" role="alert">
                <md-icon>error</md-icon>
                <span>{error}</span>
              </div>
            )}
          </div>
        </section>
      ) : zones.length === 0 ? (
        /* ── Handoff vide : aucune recommandation exploitable ── */
        <section className="artisans-empty">
          <md-icon>info</md-icon>
          <h2>Aucune recommandation à mettre en correspondance</h2>
          <p>
            Le diagnostic n'a produit aucune recommandation exploitable pour un matching
            d'artisans. Relancez un diagnostic sur une autre adresse.
          </p>
          <button
            type="button"
            className="artisans-reset"
            onClick={() => {
              setReady(false);
              setZones([]);
              setAdresse('');
              sessionStorage.removeItem('typhoon_artisan_handoff');
            }}
          >
            Nouvelle recherche
          </button>
        </section>
      ) : (
        /* ── Résultats : une section par zone à risque ── */
        <div className="artisans-zones">
          {zones.map((zone) => (
            <ArtisanZoneSection key={zone.zone} zone={zone} onSearch={searchZone} />
          ))}
        </div>
      )}
    </main>
  );
}

function ArtisanZoneSection({
  zone,
  onSearch,
}: {
  zone: ZoneSearch;
  onSearch: (zone: ZoneSearch, container: HTMLDivElement, button: HTMLButtonElement) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  return (
    <section className="artisan-zone">
      <div className="artisan-zone-head">
        <span className="artisan-zone-name">
          {zone.zone.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
        </span>
        {zone.alea && <span className="artisan-zone-alea">{zone.alea}</span>}
      </div>

      {zone.recommandations.length > 0 && (
        <ul className="artisan-zone-recos">
          {zone.recommandations.slice(0, 4).map((r, i) => (
            <li key={i}>{r.mesure || r.travaux}</li>
          ))}
          {zone.recommandations.length > 4 && (
            <li className="more">+ {zone.recommandations.length - 4} autre(s)…</li>
          )}
        </ul>
      )}

      <button
        ref={buttonRef}
        type="button"
        className="artisan-search-btn"
        onClick={() => {
          if (containerRef.current && buttonRef.current) {
            onSearch(zone, containerRef.current, buttonRef.current);
          }
        }}
      >
        Rechercher des artisans correspondants
      </button>
      <div ref={containerRef} className="artisan-results" />
    </section>
  );
}
