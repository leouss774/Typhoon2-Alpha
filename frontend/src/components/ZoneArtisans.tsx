import { useState } from 'react';
import { API } from '../zone/config';
import type { ZoneRecommendation } from '../jumeau/recommendations';

// =============================================================================
//   TYPHOON — ZoneArtisans : accordéon « Trouver des artisans » par carte de
//   recommandation (étape Recommandations du wizard /zone).
//
//   Consomme POST /api/v1/artisans/matching (backend app/matching/service.py) :
//   une seule recommandation -> `recommandations_traitees[]` (un groupe par
//   métier associé, chacun avec sa liste `entreprises[]`).
//
//   Style : même langage M3 que ZoneRecommendations (tokens --accent /
//   --md-sys-color-*, classes zone-artisans-*). Aucune valeur inventée :
//   score, distance, ancienneté, qualification et détails viennent de l'API.
// =============================================================================

export interface MatchingEntreprise {
  nom_entreprise?: string | null;
  siret?: string | null;
  siren?: string | null;
  adresse?: string | null;
  code_postal?: string | null;
  commune?: string | null;
  telephone?: string | null;
  email?: string | null;
  site_officiel?: string | null;
  site_internet?: string | null;
  lien_fiche_officielle?: string | null;
  qualification_valide?: boolean | null;
  score_objectif_sur_100?: number | null;
  details_score?: string[];
  distance_km?: number | null;
  anciennete_rge_ans?: number | null;
  activite_principale?: string | null;
}

export interface MatchingGroupe {
  cle?: string | null;
  categorie?: 'rge' | 'non_rge' | 'inconnue' | string | null;
  libelle?: string | null;
  domaine_recherche?: string | null;
  priorite?: string | null;
  erreur?: string | null;
  entreprises?: MatchingEntreprise[];
  annuaire_reference?: { organisme?: string; url?: string } | null;
}

export interface MatchingResponse {
  adresse: string;
  code_postal: string;
  recommandations_traitees: MatchingGroupe[];
  resume?: {
    total_recommandations_traitees?: number;
    total_entreprises_trouvees?: number;
    details_categories?: Record<string, number>;
  };
  geocoding?: unknown;
}

type Props = {
  adresse: string;
  zone: string;
  aleaPrincipal?: string;
  recommendation: ZoneRecommendation;
};

function scoreTone(score: number | null | undefined): string {
  if (score === null || score === undefined) return '';
  if (score >= 80) return ' high';
  if (score >= 60) return ' mid';
  return ' low';
}

function formatDistance(km: number | null | undefined): string | null {
  if (km === null || km === undefined) return null;
  return km < 1 ? `à ${Math.round(km * 1000)} m` : `à ${km.toLocaleString('fr-FR')} km`;
}

export function ZoneArtisans({ adresse, zone, aleaPrincipal, recommendation }: Props) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<MatchingResponse | null>(null);

  async function load() {
    if (data || loading) return;
    setLoading(true);
    setError(null);
    try {
      const mesure = recommendation.mesure || recommendation.travaux || '';
      const risques = aleaPrincipal ? [aleaPrincipal.toLowerCase()] : [];
      const resp = await fetch(`${API}/api/v1/artisans/matching`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adresse,
          recommandations: [
            { zone, risques, mesure, priorite: recommendation.priorite || null },
          ],
        }),
      });
      const payload = await resp.json().catch(() => null);
      if (!resp.ok) {
        const detail =
          payload && typeof payload.detail === 'string'
            ? payload.detail
            : `Erreur HTTP ${resp.status}`;
        throw new Error(detail);
      }
      setData(payload as MatchingResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function toggle() {
    if (!open && !data && !loading) void load();
    setOpen((o) => !o);
  }

  const groupes = data?.recommandations_traitees || [];
  const totalEntreprises = data?.resume?.total_entreprises_trouvees ?? 0;

  return (
    <div className="zone-artisans">
      <button
        type="button"
        className={`zone-artisans-toggle${open ? ' open' : ''}`}
        aria-expanded={open}
        onClick={toggle}
      >
        <md-icon aria-hidden="true">handyman</md-icon>
        <span>
          {open ? 'Masquer les artisans' : 'Trouver des artisans pour ce chantier'}
        </span>
        <md-icon className="zone-artisans-chevron" aria-hidden="true">expand_more</md-icon>
      </button>

      {open && (
        <div className="zone-artisans-body">
          {loading && (
            <div className="zone-artisans-loading" role="status">
              <md-circular-progress indeterminate aria-hidden="true"></md-circular-progress>
              <span>Recherche dans les annuaires officiels (RGE France&nbsp;Rénov' + Registre National)…</span>
            </div>
          )}

          {!loading && error && (
            <div className="zone-artisans-error" role="alert">
              <md-icon aria-hidden="true">cloud_off</md-icon>
              <div>
                <strong>Recherche indisponible</strong>
                <span>{error}</span>
              </div>
              <md-text-button onClick={() => void load()}>
                <md-icon slot="icon">refresh</md-icon> Réessayer
              </md-text-button>
            </div>
          )}

          {!loading && !error && data && groupes.length === 0 && (
            <div className="zone-artisans-empty">
              <md-icon aria-hidden="true">search_off</md-icon>
              <span>
                Aucun artisan n’a pu être associé automatiquement à cette
                recommandation. Réessayez avec une adresse plus précise.
              </span>
            </div>
          )}

          {!loading && !error && data && groupes.length > 0 && (
            <div className="zone-artisans-groups">
              <div className="zone-artisans-summary">
                {totalEntreprises > 0
                  ? `${groupes.length} métier(s) associé(s) · ${totalEntreprises} entreprise(s) trouvée(s)`
                  : `${groupes.length} métier(s) associé(s)`}
              </div>

              {groupes.map((groupe, gi) => (
                <section className="zone-artisans-group" key={gi}>
                  <header className="zone-artisans-group-head">
                    <h5>
                      {groupe.libelle || groupe.domaine_recherche || groupe.cle || 'Métier associé'}
                    </h5>
                    <span
                      className={`zone-artisans-badge ${
                        groupe.categorie === 'rge' ? 'rge' : 'local'
                      }`}
                    >
                      {groupe.categorie === 'rge' ? 'RGE' : 'Métier local'}
                    </span>
                  </header>

                  {groupe.erreur && (
                    <p className="zone-artisans-group-erreur">{groupe.erreur}</p>
                  )}

                  {(!groupe.entreprises || groupe.entreprises.length === 0) && (
                    <p className="zone-artisans-group-empty">
                      Aucune entreprise trouvée pour ce métier dans le secteur.
                    </p>
                  )}

                  {(groupe.entreprises || []).map((entreprise, ei) => {
                    const fullAdresse = [
                      entreprise.adresse,
                      entreprise.code_postal,
                      entreprise.commune,
                    ]
                      .filter(Boolean)
                      .join(' ');
                    const site =
                      entreprise.site_officiel ||
                      entreprise.site_internet ||
                      entreprise.lien_fiche_officielle;
                    const distance = formatDistance(entreprise.distance_km);
                    const score = entreprise.score_objectif_sur_100;
                    const rge = groupe.categorie === 'rge';

                    return (
                      <article className="zone-artisans-card" key={ei}>
                        <div className="zone-artisans-card-top">
                          <div className="zone-artisans-card-title">
                            <strong>{entreprise.nom_entreprise || 'Entreprise'}</strong>
                            {rge ? (
                              entreprise.qualification_valide ? (
                                <span className="zone-artisans-rge valid">
                                  <md-icon aria-hidden="true">verified</md-icon> RGE valide
                                </span>
                              ) : (
                                <span className="zone-artisans-rge expired">
                                  <md-icon aria-hidden="true">warning</md-icon> RGE expirée
                                </span>
                              )
                            ) : (
                              <span className="zone-artisans-rge none">
                                <md-icon aria-hidden="true">storefront</md-icon> non certifié RGE
                              </span>
                            )}
                          </div>
                          <div className={`zone-artisans-score${scoreTone(score)}`}>
                            <strong>{score ?? '—'}</strong>
                            <small>/100</small>
                          </div>
                        </div>

                        <div className="zone-artisans-card-meta">
                          {fullAdresse && (
                            <span>
                              <md-icon aria-hidden="true">location_on</md-icon>
                              {fullAdresse}
                              {distance ? ` · ${distance}` : ''}
                            </span>
                          )}
                          {rge && entreprise.anciennete_rge_ans !== null && entreprise.anciennete_rge_ans !== undefined && (
                            <span>
                              <md-icon aria-hidden="true">history</md-icon>
                              Certifié RGE depuis {entreprise.anciennete_rge_ans} an(s)
                            </span>
                          )}
                          {(entreprise.telephone || entreprise.email) && (
                            <span>
                              <md-icon aria-hidden="true">contact_phone</md-icon>
                              {[entreprise.telephone, entreprise.email]
                                .filter(Boolean)
                                .join(' · ')}
                            </span>
                          )}
                          {entreprise.siret && (
                            <span>
                              <md-icon aria-hidden="true">badge</md-icon>
                              SIRET {entreprise.siret}
                            </span>
                          )}
                        </div>

                        {entreprise.details_score && entreprise.details_score.length > 0 && (
                          <details className="zone-artisans-details">
                            <summary>
                              <md-icon aria-hidden="true">info</md-icon> Pourquoi ce score
                            </summary>
                            <ul>
                              {entreprise.details_score.map((d, di) => (
                                <li key={di}>{d}</li>
                              ))}
                            </ul>
                          </details>
                        )}

                        <div className="zone-artisans-card-actions">
                          {entreprise.telephone && (
                            <a
                              className="zone-artisans-action primary"
                              href={`tel:${String(entreprise.telephone).replace(/[^\d+]/g, '')}`}
                            >
                              <md-icon aria-hidden="true">call</md-icon> Appeler
                            </a>
                          )}
                          {entreprise.email && (
                            <a
                              className="zone-artisans-action"
                              href={`mailto:${entreprise.email}`}
                            >
                              <md-icon aria-hidden="true">mail</md-icon> E-mail
                            </a>
                          )}
                          {site && (
                            <a
                              className="zone-artisans-action"
                              href={site}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <md-icon aria-hidden="true">open_in_new</md-icon> Site officiel
                            </a>
                          )}
                          {fullAdresse && (
                            <a
                              className="zone-artisans-action"
                              href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(fullAdresse)}`}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <md-icon aria-hidden="true">map</md-icon> Itinéraire
                            </a>
                          )}
                        </div>

                        {groupe.annuaire_reference?.organisme && (
                          <p className="zone-artisans-annuaire">
                            Source : {groupe.annuaire_reference.organisme}
                            {groupe.annuaire_reference.url ? (
                              <>
                                {' '}
                                ·{' '}
                                <a
                                  href={groupe.annuaire_reference.url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  voir l’annuaire
                                </a>
                              </>
                            ) : null}
                          </p>
                        )}
                      </article>
                    );
                  })}
                </section>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
