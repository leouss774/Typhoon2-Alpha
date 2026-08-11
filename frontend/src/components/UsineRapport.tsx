// =============================================================================
//   TYPHOON — /usine : étape 6 « Rapport » — rapport d'analyse narratif
//   Généré côté client à partir du risk engine (déterministe, aucun LLM
//   requis) + export PDF via jsPDF (importé à la demande).
// =============================================================================

import { useMemo, useState } from 'react';
import {
  bandForScore,
  bandForKey,
  normalizeNiveau,
  TYPE_EQUIP_LABELS,
  TYPE_ZONE_LABELS,
  type AnalyseUsine,
  type Equipement,
  type ZonePlan,
} from '../usine/types';

type Props = {
  analyse: AnalyseUsine | null;
};

export function UsineRapport({ analyse }: Props) {
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const sortedZones = useMemo(
    () => [...(analyse?.zones || [])].sort((a, b) => (b.risque ?? 0) - (a.risque ?? 0)),
    [analyse]
  );
  const sortedEquips = useMemo(
    () => [...(analyse?.equipements || [])].sort((a, b) => (b.risque ?? 0) - (a.risque ?? 0)),
    [analyse]
  );

  if (!analyse) {
    return (
      <div className="analyse-empty">
        <md-icon>description</md-icon>
        <h2>Aucun rapport</h2>
        <p>Lancez d'abord l'analyse de risque pour générer le rapport d'évaluation de l'usine.</p>
      </div>
    );
  }

  const band = bandForScore(analyse.score_global);
  const conf = analyse.confiance || { score: 0, niveau: 'faible' };
  const date = new Date().toLocaleDateString('fr-FR', { day: '2-digit', month: 'long', year: 'numeric' });
  const topZones = sortedZones.slice(0, 3);
  const topEquips = sortedEquips.slice(0, 6);

  const synopsis = buildSynopsis(analyse, topZones);

  async function handleExport() {
    if (!analyse) return;
    setExporting(true);
    setExportError(null);
    try {
      const { exportRapportUsinePdf } = await import('../usine/pdf-export');
      await exportRapportUsinePdf(analyse);
    } catch (err) {
      console.error('Export PDF du rapport usine échoué :', err);
      setExportError("L'export PDF a échoué dans le navigateur. Réessayez.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="usine-report">
      <header className="report-header">
        <div className="report-title">
          <h2>Rapport d'analyse — {analyse.nom_usine}</h2>
          <p className="report-meta">
            Généré le {date} · {analyse.nb_zones} zones · {analyse.nb_equipements} équipements
            {analyse.aleas_site?.libelle ? ` · aléa site : ${analyse.aleas_site.libelle}` : ''}
          </p>
        </div>
        <div className="report-actions">
          <md-elevated-button
            className="report-export"
            disabled={exporting}
            aria-busy={exporting || undefined}
            onClick={handleExport}
          >
            <md-icon slot="icon">
              {exporting ? 'hourglass_top' : 'picture_as_pdf'}
            </md-icon>
            {exporting ? 'Génération du PDF…' : 'Exporter en PDF'}
          </md-elevated-button>
        </div>
        {exportError && (
          <p className="report-export-error" role="alert">
            <md-icon>error</md-icon>
            <span>{exportError}</span>
          </p>
        )}
      </header>

      <div className="usine-report-score">
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
        <span className="usine-report-conf">
          <md-icon>verified_user</md-icon> Confiance {conf.niveau} ({conf.score}/100)
        </span>
      </div>

      <p className="report-intro">{synopsis.introduction}</p>

      <div className="report-sections">
        <article className="report-section">
          <h3>Synthèse par zone</h3>
          <div className="usine-report-zone-list">
            {topZones.map((z) => (
              <ReportZoneRow key={z.id} zone={z} />
            ))}
          </div>
        </article>

        <article className="report-section">
          <h3>Équipements les plus sensibles</h3>
          <div className="usine-report-equip-list">
            {topEquips.map((e) => (
              <ReportEquipRow key={e.id} eq={e} />
            ))}
          </div>
          {analyse.equipements.length > topEquips.length ? (
            <p className="usine-report-more">
              …et {analyse.equipements.length - topEquips.length} autre(s) équipement(s) analysé(s).
            </p>
          ) : null}
        </article>

        {synopsis.criticales.length > 0 && (
          <article className="report-section">
            <h3>Points de vigilance</h3>
            <ul>
              {synopsis.criticales.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </article>
        )}
      </div>

      <aside className="report-synthese">
        <md-icon>summarize</md-icon>
        <div>
          <h3>Synthèse finale</h3>
          <p>{synopsis.conclusion}</p>
        </div>
      </aside>

      <p className="report-avertissement">
        <md-icon>info</md-icon>
        <span>
          {synopsis.avertissement}
        </span>
      </p>
    </div>
  );
}

/* ─────────── Lignes du rapport ─────────── */

function ReportZoneRow({ zone }: { zone: ZonePlan }) {
  const band = bandForScore(zone.risque);
  return (
    <div className="usine-report-zone-row">
      <span className="usine-report-zone-score" style={{ background: band.color }}>
        {zone.risque ?? '—'}
      </span>
      <div>
        <strong>{zone.nom}</strong>
        <span className="usine-report-zone-sub">
          {TYPE_ZONE_LABELS[zone.type] || zone.type} · vulnérabilité {zone.vulnerabilite ?? '—'}/100
        </span>
      </div>
      <span className="usine-report-zone-band" style={{ color: band.color }}>
        {band.label}
      </span>
    </div>
  );
}

function ReportEquipRow({ eq }: { eq: Equipement }) {
  const band = bandForScore(eq.risque);
  return (
    <div className="usine-report-equip-row">
      <span className="usine-report-eq-dot" style={{ background: band.color }} />
      <strong>{eq.nom}</strong>
      <span className="usine-report-eq-meta">
        {TYPE_EQUIP_LABELS[eq.type] || eq.type}
        {eq.matieres_dangereuses ? ' · dangereux' : ''}
        {eq.critique_production ? ' · critique' : ''}
      </span>
      <span className="usine-report-eq-score" style={{ color: band.color }}>
        {eq.risque ?? '—'}
      </span>
    </div>
  );
}

/* ─────────── Narratif ─────────── */

function buildSynopsis(analyse: AnalyseUsine, topZones: ZonePlan[]) {
  const band = bandForScore(analyse.score_global);
  const critiques = analyse.zones.filter((z) => (z.risque ?? 0) >= 60);
  const dangereux = analyse.equipements.filter((e) => e.matieres_dangereuses);
  const critiqueProd = analyse.equipements.filter((e) => e.critique_production);

  const topNames = topZones.slice(0, 2).map((z) => z.nom).join(' et ');
  const introduction = `Le site « ${analyse.nom_usine} » présente un score de risque global de ${analyse.score_global}/100, soit un niveau ${band.label.toLowerCase()}. ` +
    `${analyse.nb_zones} zone(s) ont été analysées à partir du plan importé${analyse.aleas_site?.libelle ? `, dans un contexte d'aléa site « ${analyse.aleas_site.libelle} »` : ''}. ` +
    `La zone la plus exposée est « ${topNames || '—'} » avec un risque estimé à ${topZones[0]?.risque ?? '—'}/100. ` +
    `L'analyse combine aléa du site (F) et vulnérabilité (V) selon la moyenne géométrique non-compensatoire R = √(F × V).`;

  const criticales: string[] = [];
  if (critiques.length > 0) {
    criticales.push(
      `${critiques.length} zone(s) atteignent un risque élevé ou critique — à traiter en priorité : ${critiques.map((z) => z.nom).join(', ')}.`
    );
  }
  if (dangereux.length > 0) {
    criticales.push(
      `${dangereux.length} équipement(s) impliquent des matières dangereuses (incendie, explosion ou pollution) : ${dangereux.slice(0, 4).map((e) => e.nom).join(', ')}${dangereux.length > 4 ? '…' : ''}.`
    );
  }
  if (critiqueProd.length > 0) {
    criticales.push(
      `${critiqueProd.length} équipement(s) sont critiques pour la production — leur indisponibilité pèserait directement sur l'activité.`
    );
  }
  if (criticales.length === 0) {
    criticales.push('Aucun point de vigilance majeur détecté par le risk engine sur ce plan.');
  }

  const conclusion =
    `Avec un score de ${analyse.score_global}/100 (${band.label.toLowerCase()}) et une confiance ${confLabel(analyse.confiance.niveau)} (${analyse.confiance.score}/100), ` +
    `l'usine « ${analyse.nom_usine} » requiert ${
      (analyse.score_global ?? 0) >= 60
        ? 'un plan d' + 'action prioritaire : sécuriser les zones à risque, fiabiliser les équipements critiques et renforcer la résilience opérationnelle.'
        : (analyse.score_global ?? 0) >= 40
          ? 'des actions ciblées de renforcement sur les zones les plus exposées et une surveillance des équipements sensibles.'
          : 'principalement des mesures de surveillance et de continuité d' + 'activité à coût maîtrisé.'
    }`;

  const avertissement =
    "Ce rapport est généré automatiquement par le risk engine Typhoon à partir du plan importé et des attributs de zones/équipements. Il ne remplace pas une étude d'ingénierie, une analyse ICPE réglementaire ni l'avis d'un expert en risques industriels.";

  return { introduction, criticales, conclusion, avertissement };
}

function confLabel(niveau: string): string {
  const map: Record<string, string> = {
    elevee: 'élevée',
    bonne: 'bonne',
    moyenne: 'moyenne',
    faible: 'faible',
  };
  return map[niveau] || niveau;
}
