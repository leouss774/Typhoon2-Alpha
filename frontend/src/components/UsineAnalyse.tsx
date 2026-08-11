// =============================================================================
//   TYPHOON — /usine : étape 3 « Analyse » — résultats du risk engine
//   Score global + détail du risque par zone et par équipement (R = √(F × V)),
//   contexte d'aléa du site, aperçu du plan analysé, puis bascule vers le
//   jumeau BIM qui porte la visualisation 3D.
// =============================================================================

import { useMemo } from 'react';
import {
  bandForScore,
  bandForKey,
  TYPE_EQUIP_LABELS,
  TYPE_ZONE_LABELS,
  type AnalyseUsine,
  type Equipement,
  type ZonePlan,
} from '../usine/types';

type Props = {
  analyse: AnalyseUsine | null;
  loading: boolean;
  error: string | null;
  onRelance: () => void;
  onGoBim: () => void;
  planImage?: string | null;
};

export function UsineAnalyse({ analyse, loading, error, onRelance, onGoBim, planImage }: Props) {
  if (loading) {
    return (
      <div className="analyse-empty usine-analyse-loading">
        <md-icon>psychology</md-icon>
        <h2>Calcul du risque en cours…</h2>
        <p>Le risk engine combine aléa du site (F) et vulnérabilité (V) pour chaque zone et équipement.</p>
        <md-linear-progress indeterminate />
      </div>
    );
  }

  if (error) {
    return (
      <div className="report-error" role="alert">
        <div className="report-error-icon">
          <md-icon>cloud_off</md-icon>
        </div>
        <h2>Analyse indisponible</h2>
        <p className="report-error-msg">{error}</p>
        <div className="report-error-actions">
          <md-filled-button onClick={onRelance}>
            <md-icon slot="icon">refresh</md-icon> Réessayer
          </md-filled-button>
        </div>
      </div>
    );
  }

  if (!analyse) {
    return (
      <div className="analyse-empty">
        <md-icon>analytics</md-icon>
        <h2>Analyse non lancée</h2>
        <p>Validez le plan puis lancez l'analyse de risque par zone et équipement.</p>
        <md-filled-button onClick={onRelance}>
          <md-icon slot="icon">play_arrow</md-icon> Lancer l'analyse
        </md-filled-button>
      </div>
    );
  }

  const band = bandForScore(analyse.score_global);
  const conf = analyse.confiance || { score: 0, niveau: 'faible' };

  const sortedZones = useMemo(
    () => [...(analyse.zones || [])].sort((a, b) => (b.risque ?? 0) - (a.risque ?? 0)),
    [analyse]
  );
  const sortedEquipements = useMemo(
    () => [...(analyse.equipements || [])].sort((a, b) => (b.risque ?? 0) - (a.risque ?? 0)),
    [analyse]
  );

  return (
    <div className="usine-analyse">
      <header className="usine-analyse-header">
        <div className="usine-analyse-title">
          <h2>Analyse de risque — {analyse.nom_usine}</h2>
          <p className="usine-analyse-meta">
            {analyse.nb_zones} zones · {analyse.nb_equipements} équipements
            {analyse.aleas_site?.libelle
              ? ` · aléa site : ${analyse.aleas_site.libelle}`
              : ' · aléa site neutre (F = 50)'}
          </p>
        </div>
        <span className="src-chip">
          <md-icon>database</md-icon>Typhon Risk Engine · R = √(F × V)
        </span>
      </header>

      <div className="usine-analyse-score">
        <div className="usine-score-big" style={{ color: band.color }}>
          {analyse.score_global}
          <span className="usine-score-max">/100</span>
        </div>
        <div className="usine-score-meta">
          <span className="usine-score-label">Score de risque global</span>
          <span className="usine-score-band" style={{ background: band.soft, color: band.color }}>
            {band.label}
          </span>
        </div>
        <div className="usine-confiance">
          <md-icon>verified_user</md-icon>
          <span>
            Confiance : <strong>{conf.niveau}</strong> ({conf.score}/100)
            {conf.message ? ` — ${conf.message}` : ''}
          </span>
        </div>
      </div>

      {analyse.aleas_site && (
        <div className="usine-aleas-site">
          <span className="usine-aleas-site-icon">
            <md-icon>layers</md-icon>
          </span>
          <div className="usine-aleas-site-body">
            <strong>Contexte Géorisques du site</strong>
            <span className="usine-aleas-site-score" style={{ color: bandForScore(analyse.aleas_site.score).color }}>
              Aléa {analyse.aleas_site.libelle || 'présent'} · {analyse.aleas_site.score}/100
            </span>
            <p>
              L'aléa du site entre dans chaque calcul R = √(F × V) à la place du neutre
              (F = 50). Adresse renseignée via l'import du plan.
            </p>
          </div>
        </div>
      )}

      <div className="usine-risk-legend">
        {['tres_faible', 'faible', 'modere', 'eleve', 'critique'].map((k) => (
          <span className="usine-legend-item" key={k}>
            <span className="usine-legend-dot" style={{ background: bandForKey(k).color }} />
            {bandForKey(k).label}
          </span>
        ))}
      </div>

      <section className="usine-analyse-section">
        <h3>
          <md-icon>maps_home_work</md-icon> Risque par zone
        </h3>
        <div className="usine-zone-cards">
          {sortedZones.map((zone) => (
            <ZoneCard key={zone.id} zone={zone} equipements={analyse.equipements} />
          ))}
        </div>
      </section>

      <section className="usine-analyse-section">
        <h3>
          <md-icon>precision_manufacturing</md-icon> Sensibilité par équipement
        </h3>
        <div className="usine-equip-table">
          <div className="usine-equip-head">
            <span>Équipement</span>
            <span>Zone</span>
            <span>Valeur</span>
            <span>Danger</span>
            <span>Critique</span>
            <span>Risque</span>
          </div>
          {sortedEquipements.map((eq) => (
            <EquipRow key={eq.id} eq={eq} />
          ))}
        </div>
      </section>

      {planImage && (
        <div className="usine-analyse-plan">
          <h4>
            <md-icon>image</md-icon> Plan analysé
          </h4>
          <div className="usine-analyse-plan-img">
            <img src={planImage} alt="Plan d'usine analysé" />
          </div>
        </div>
      )}

      <div className="usine-analyse-cta">
        <md-filled-button onClick={onGoBim}>
          <md-icon slot="icon">view_in_ar</md-icon> Ouvrir le jumeau BIM
        </md-filled-button>
      </div>

      <p className="usine-analyse-note" role="note">
        <md-icon>science</md-icon>
        <span>
          R = 100 × (F/100)^0.5 × (V/100)^0.5 où F est l'aléa du site (Géorisques si une adresse est
          renseignée, neutre sinon) et V la vulnérabilité de la zone / la sensibilité de l'équipement.
          Le plan affine la confiance (+15 pts). La visualisation complète est portée par le jumeau BIM.
        </span>
      </p>
    </div>
  );
}

/* ─────────── Blocs ─────────── */

function ZoneCard({ zone, equipements }: { zone: ZonePlan; equipements: Equipement[] }) {
  const band = bandForScore(zone.risque);
  const eqs = (zone.equipements || [])
    .map((id) => equipements.find((e) => e.id === id))
    .filter((e): e is Equipement => Boolean(e));

  return (
    <article className="usine-zone-card">
      <div className="usine-zone-card-head">
        <span className="usine-zone-card-index" style={{ background: band.color }}>
          {zone.risque ?? '—'}
        </span>
        <div className="usine-zone-card-id">
          <strong>{zone.nom}</strong>
          <span className="usine-zone-card-sub">
            {TYPE_ZONE_LABELS[zone.type] || zone.type}
            {typeof zone.surface_m2 === 'number' ? ` · ${zone.surface_m2.toLocaleString('fr-FR')} m²` : ''}
          </span>
        </div>
        <span className="usine-zone-niveau" style={{ color: band.color, borderColor: band.color }}>
          {band.label}
        </span>
      </div>
      <div className="usine-zone-bars">
        <Bar label="Vulnérabilité" value={zone.vulnerabilite ?? 0} color={band.color} />
        <Bar label="Risque" value={zone.risque ?? 0} color={band.color} strong />
      </div>
      {zone.description ? <p className="usine-zone-desc">{zone.description}</p> : null}
      {eqs.length > 0 && (
        <div className="usine-zone-equip">
          {eqs.map((e) => (
            <span
              key={e.id}
              className="usine-zone-equip-chip"
              style={{ color: bandForScore(e.risque).color }}
            >
              <md-icon>precision_manufacturing</md-icon>
              {e.nom}
              {e.risque != null ? ` · ${e.risque}` : ''}
            </span>
          ))}
        </div>
      )}
    </article>
  );
}

function EquipRow({ eq }: { eq: Equipement }) {
  const band = bandForScore(eq.risque);
  return (
    <div className="usine-equip-row">
      <span className="usine-equip-name">
        <span className="usine-equip-dot" style={{ background: band.color }} />
        {eq.nom}
        <small>{TYPE_EQUIP_LABELS[eq.type] || eq.type}</small>
      </span>
      <span className="usine-equip-cell">{eq.zone || '—'}</span>
      <span className="usine-equip-cell">
        {typeof eq.valeur_remplacement_eur === 'number'
          ? `${eq.valeur_remplacement_eur.toLocaleString('fr-FR')} €`
          : '—'}
      </span>
      <span className="usine-equip-cell">
        {eq.matieres_dangereuses ? <md-icon className="usine-flag warn">warning</md-icon> : '—'}
      </span>
      <span className="usine-equip-cell">
        {eq.critique_production ? <md-icon className="usine-flag accent">priority_high</md-icon> : '—'}
      </span>
      <span className="usine-equip-cell usine-equip-score" style={{ color: band.color }}>
        {eq.risque ?? '—'}
        {eq.sensibilite != null ? <small>sens. {eq.sensibilite}</small> : null}
      </span>
    </div>
  );
}

function Bar({ label, value, color, strong }: { label: string; value: number; color: string; strong?: boolean }) {
  return (
    <div className={`usine-bar${strong ? ' strong' : ''}`}>
      <span className="usine-bar-label">{label}</span>
      <span className="usine-bar-track">
        <span className="usine-bar-fill" style={{ width: `${Math.min(100, value)}%`, background: color }} />
      </span>
      <span className="usine-bar-value" style={{ color }}>
        {value}
      </span>
    </div>
  );
}
