import { useMemo, useState } from 'react';
import { API, type RisqueReport } from '../zone/config';
import { aggregateRecommendations, formatZoneLabel, type RecommendationZone } from '../jumeau/recommendations';

type Entreprise = {
  nom_entreprise?: string;
  adresse?: string;
  code_postal?: string;
  commune?: string;
  telephone?: string;
  email?: string;
  site_officiel?: string;
  site_annuaire?: string;
  qualification_valide?: boolean | null;
  distance_km?: number | null;
  anciennete_rge_ans?: number | null;
};

type Groupe = {
  cle?: string;
  categorie?: string;
  libelle?: string;
  domaine_recherche?: string;
  recommendation_id?: string;
  mesure_originale?: string;
  notice?: string;
  erreur?: string;
  entreprises?: Entreprise[];
};

type MatchingResponse = {
  recommandations_traitees?: Groupe[];
  resume?: { total_entreprises_trouvees?: number; total_recommandations_traitees?: number };
};

type Props = {
  report: RisqueReport | null;
  zones: Record<string, RecommendationZone>;
  loading: boolean;
  error: string | null;
};

function addressOf(entreprise: Entreprise) {
  return [entreprise.adresse, entreprise.code_postal, entreprise.commune].filter(Boolean).join(' ');
}

function distanceOf(distance?: number | null) {
  if (distance === null || distance === undefined) return null;
  return distance < 1 ? `${Math.round(distance * 1000)} m` : `${distance.toLocaleString('fr-FR')} km`;
}

function initialsOf(name?: string) {
  if (!name) return '?';
  const words = name.trim().replace(/^(sarl|sas|sasu|ei|eurl|scop)\s+/i, '').split(/\s+/).filter((w) => Boolean(w) && !w.startsWith('('));
  const first = (words[0] || '')[0] || '';
  const second = words.length > 1 ? (words[1] || '')[0] : ((words[0] || '')[1] || '');
  return (first + second).toUpperCase() || '?';
}

export function ZoneArtisans({ report, zones, loading: recommendationsLoading, error: recommendationsError }: Props) {
  const recommendations = useMemo(() => aggregateRecommendations(zones), [zones]);
  const [matching, setMatching] = useState<MatchingResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const groups = matching?.recommandations_traitees || [];
  const total = groups.reduce((sum, group) => sum + (group.entreprises?.length || 0), 0);

  async function search() {
    if (!report || !recommendations.length || searching) return;
    setSearching(true);
    setSearchError(null);
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 30_000);
    try {
      const response = await fetch(`${API}/api/v1/artisans/matching`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          adresse: report.adresse_normalisee,
          limite_entreprises: 5,
          recommandations: recommendations.map((recommendation) => {
            const aleaPrincipal = zones[recommendation.zone]?.alea_principal;
            return {
              id: recommendation.id,
              zone: recommendation.zone,
              risques: aleaPrincipal ? [aleaPrincipal.toLowerCase()] : [],
              mesure: recommendation.mesure || recommendation.travaux || '',
              priorite: recommendation.priorite || null,
            };
          }),
        }),
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof payload?.detail === 'string' ? payload.detail : `Erreur HTTP ${response.status}`);
      setMatching(payload as MatchingResponse);
    } catch (cause) {
      setSearchError(
        cause instanceof DOMException && cause.name === 'AbortError'
          ? 'La recherche prend trop de temps. Réessayez dans quelques instants.'
          : cause instanceof Error ? cause.message : 'La recherche est indisponible pour le moment.',
      );
    } finally {
      window.clearTimeout(timeout);
      setSearching(false);
    }
  }

  if (!report) return <div className="zone-artisans-empty-state"><md-icon>handyman</md-icon><h2>Aucun diagnostic</h2><p>Diagnostiquez une adresse pour trouver les professionnels adaptés.</p></div>;

  return (
    <div className="zone-artisans-view">
      <header className="zone-artisans-hero">
        <div>
          <span className="zone-artisans-eyebrow">Étape 6 · Passer à l’action</span>
          <h2>Trouvez les bons artisans</h2>
          <p>Une recherche unique associe les professionnels qualifiés aux travaux recommandés pour votre bien.</p>
          <span className="zone-artisans-address"><md-icon>location_on</md-icon>{report.adresse_normalisee}</span>
        </div>
        <div className="zone-artisans-hero-stat"><strong>{recommendations.length}</strong><span>travaux à couvrir</span></div>
      </header>

      {recommendationsLoading ? (
        <div className="zone-artisans-status"><md-circular-progress indeterminate></md-circular-progress><span>Préparation des travaux recommandés…</span></div>
      ) : recommendationsError ? (
        <div className="zone-artisans-status error"><md-icon>cloud_off</md-icon><span>Les recommandations détaillées ne sont pas disponibles : {recommendationsError}</span></div>
      ) : recommendations.length === 0 ? (
        <div className="zone-artisans-status"><md-icon>verified</md-icon><span>Aucun travail prioritaire à mettre en relation pour cette adresse.</span></div>
      ) : (
        <>
          <section className="zone-artisans-brief">
            <div><md-icon>assignment</md-icon><span><strong>Votre sélection est prête.</strong> Les {recommendations.length} mesures issues du diagnostic seront transmises aux annuaires partenaires.</span></div>
            <button type="button" className="zone-artisans-search" onClick={() => void search()} disabled={searching}>
              {searching ? <md-circular-progress indeterminate></md-circular-progress> : <md-icon>search</md-icon>}
              {searching ? 'Recherche des artisans…' : matching ? 'Actualiser la recherche' : 'Rechercher des artisans'}
            </button>
          </section>

          {!matching && !searchError && <section className="zone-artisans-plan"><h3>Travaux pris en compte</h3><div>{recommendations.map((recommendation) => <span key={recommendation.id}><md-icon>build</md-icon>{formatZoneLabel(recommendation.zone)} · {recommendation.mesure || recommendation.travaux}</span>)}</div></section>}

          {searchError && <div className="zone-artisans-status error"><md-icon>cloud_off</md-icon><span>{searchError}</span><button type="button" onClick={() => void search()}>Réessayer</button></div>}

          {matching && <section className="zone-artisans-results">
            <header><div><span className="zone-artisans-eyebrow">Résultats</span><h3>{total} professionnel{total > 1 ? 's' : ''} identifié{total > 1 ? 's' : ''}</h3></div><p>Classement fondé sur la qualification et la proximité.</p></header>
            {groups.length === 0 ? <div className="zone-artisans-status"><md-icon>search_off</md-icon><span>Aucun artisan n’a été trouvé automatiquement. Essayez à nouveau plus tard.</span></div> : <div className="zone-artisans-groups">{groups.map((group, index) => <section className="zone-artisans-result-group" key={group.recommendation_id || `${group.cle || group.libelle}-${index}`}><header><div><span className="zone-artisans-recommendation">Pour la recommandation</span><h4>{group.mesure_originale || group.libelle || group.domaine_recherche || 'Métier associé'}</h4><span className={group.categorie === 'rge' ? 'rge' : ''}>{group.categorie === 'rge' ? 'Professionnels RGE' : 'Professionnels locaux'}</span></div><small>Top {group.entreprises?.length || 0} artisan{(group.entreprises?.length || 0) > 1 ? 's' : ''}</small></header>{group.erreur ? <p className="zone-artisans-group-error">{group.erreur}</p> : (group.entreprises?.length || 0) === 0 ? <p className="zone-artisans-group-error">{group.notice || 'Aucun professionnel vérifié n’a été trouvé pour cette recommandation.'}</p> : <>{group.notice && <p className="zone-artisans-group-notice">{group.notice}</p>}<div className="zone-artisans-company-grid">{(group.entreprises || []).map((company, companyIndex) => { const address = addressOf(company); const distance = distanceOf(company.distance_km); return <article className="zone-artisans-company" key={companyIndex}><div className="zone-artisans-company-head"><div><h5>{company.nom_entreprise || 'Entreprise'}</h5>{group.categorie === 'rge' && <span className={company.qualification_valide ? 'qualified' : 'unqualified'}><md-icon>{company.qualification_valide ? 'verified' : 'info'}</md-icon>{company.qualification_valide ? 'RGE valide' : 'RGE à vérifier'}</span>}</div><span className="zone-artisans-company-avatar" aria-hidden="true">{initialsOf(company.nom_entreprise)}{company.site_officiel && <img className="zone-artisans-company-logo" src={`${API}/api/v1/artisans/logo?url=${encodeURIComponent(company.site_officiel)}`} alt="" loading="lazy" referrerPolicy="no-referrer" onError={(event) => { event.currentTarget.style.display = 'none'; }} />}</span></div><div className="zone-artisans-company-meta">{address && <span><md-icon>location_on</md-icon>{address}{distance && ` · ${distance}`}</span>}{company.telephone && <span><md-icon>call</md-icon>{company.telephone}</span>}{company.email && <span><md-icon>mail</md-icon>{company.email}</span>}{company.anciennete_rge_ans != null && <span><md-icon>history</md-icon>RGE depuis {company.anciennete_rge_ans} an(s)</span>}</div><div className="zone-artisans-company-actions">{company.telephone && <a href={`tel:${company.telephone.replace(/[^\d+]/g, '')}`}><md-icon>call</md-icon>Appeler</a>}{company.email && <a href={`mailto:${company.email}`}><md-icon>mail</md-icon>E-mail</a>}{company.site_officiel && <a href={company.site_officiel} target="_blank" rel="noopener noreferrer"><md-icon>open_in_new</md-icon>Site officiel</a>}{!company.site_officiel && company.site_annuaire && <a href={company.site_annuaire} target="_blank" rel="noopener noreferrer"><md-icon>open_in_new</md-icon>Fiche entreprise</a>}{address && <a href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`} target="_blank" rel="noopener noreferrer"><md-icon>map</md-icon>Itinéraire</a>}</div></article>; })}</div></>}</section>)}</div>}
          </section>}
        </>
      )}
    </div>
  );
}
