// =============================================================================
//   TYPHOON — /zone : étape « Bâtiment » — fiche bâtiment BDNB (panneau)
//   Le panneau de la fiche reproduit la mini-fiche Go Rénove :
//     • bandeau avertissement (peut / ne peut pas)
//     • chips résumé (année · logements · niveaux)
//     • sections en cartes : Identification · Enveloppe opaque · Enveloppe vitrée
//       · Systèmes d'énergie · Performances énergétiques · Risques & confort
//   Le panneau vit à gauche de la carte unifiée (étape « Bâtiment ») et suit le
//   bâtiment sélectionné au clic (story A2), sinon le bâtiment diagnostiqué.
//   Consomme report.bdnb (batiment_groupe_complet, v0.7).
//   Toutes les valeurs null → « Indisponible » (jamais de plantage).
// =============================================================================

import type { ReactNode } from 'react';
import type { BatimentRisques, BdnbBatiment, RisqueReport } from '../zone/config';

/* ── Texte par défaut pour données manquantes ── */
const NA = 'Indisponible';

/* ── Couleurs DPE ── */
const DPE_COLORS: Record<string, string> = {
  a: '#3aa76d', b: '#7cc45c', c: '#c3d84a',
  d: '#f0e24a', e: '#f2a33c', f: '#ec6c2b', g: '#d92c2c',
};
const DPE_LETTERS = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];

/* ── Helpers ── */
function fmtNum(v: number, digits = 0): string {
  return v.toLocaleString('fr-FR', { maximumFractionDigits: digits });
}
function val(v: string | number | null | undefined, suffix = ''): string {
  if (v == null || v === '') return NA;
  return `${v}${suffix}`;
}
function boolVal(v: boolean | null | undefined): string {
  if (v == null) return NA;
  return v ? 'Oui' : 'Non';
}
function capFirst(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// =============================================================================
//   Export principal
// =============================================================================

export function BuildingFiche({
  report,
  batiment: selectedBatiment,
  risques,
  loading,
  error,
}: {
  report: RisqueReport | null;
  /** Bâtiment sélectionné par un clic sur la carte (story A2) ; sinon le bâtiment diagnostiqué. */
  batiment?: BdnbBatiment | null;
  risques?: BatimentRisques | null;
  loading?: boolean;
  error?: string | null;
}) {
  const bdnb = report?.bdnb;
  const batiment = selectedBatiment ?? bdnb?.batiment ?? null;

  /* ── États vides ── */
  if (!report) {
    return (
      <div className="gr-empty">
        <md-icon>home_work</md-icon>
        <h2>Fiche bâtiment indisponible</h2>
        <p>Diagnostiquez d'abord une adresse pour afficher la fiche BDNB.</p>
      </div>
    );
  }

  if (!batiment) {
    const err = (report.erreurs_partielles || []).find((e) =>
      e.toLowerCase().startsWith('bdnb')
    );
    return (
      <div className="gr-empty">
        <md-icon>domain_disabled</md-icon>
        <h2>BDNB indisponible pour cette adresse</h2>
        <p>
          La BDNB ne référence pas de bâtiment à cette adresse exacte.
          Sa couverture est large mais pas exhaustive — essayez une adresse voisine.
        </p>
        {err ? <span className="gr-empty-detail">{err}</span> : null}
      </div>
    );
  }

  return (
    <div className="gr-panel" role="region" aria-label="Fiche bâtiment BDNB">
      {loading && (
        <md-linear-progress indeterminate className="gr-fiche-progress" aria-hidden="true" />
      )}
      {error && (
        <div className="gr-fiche-error" role="alert">
          <md-icon>error</md-icon>
          <span>Fiche indisponible pour ce bâtiment — {error}</span>
        </div>
      )}

        {/* En-tête adresse */}
        <div className="gr-panel-header">
          <h2 className="gr-panel-address">
            {batiment.libelle_adr_principale_ban || report.adresse_normalisee}
          </h2>
          <span className="gr-src-chip">
            <md-icon>database</md-icon>
            BDNB · api.bdnb.io
          </span>
        </div>

        {/* Bandeau avertissement */}
        <WarningBanner />

        {/* Chips résumé */}
        <div className="gr-chips">
          {batiment.annee_construction != null && (
            <span className="gr-chip">Construit en {batiment.annee_construction}</span>
          )}
          {batiment.nb_log != null && (
            <span className="gr-chip">{fmtNum(batiment.nb_log)} logement{batiment.nb_log > 1 ? 's' : ''}</span>
          )}
          {batiment.nb_niveau != null && (
            <span className="gr-chip">{fmtNum(batiment.nb_niveau)} niveau{batiment.nb_niveau > 1 ? 'x' : ''}</span>
          )}
        </div>

        {/* ── Sections ── */}
        <IdentificationSection b={batiment} report={report} />
        <EnveloppeOpaqueSection b={batiment} />
        <EnveloppeVitreeSection b={batiment} />
        <SystemesEnergieSection b={batiment} />
        <PerformancesSection b={batiment} />
        <ConfortSection b={batiment} />
    </div>
  );
}

// =============================================================================
//   Bandeau avertissement
// =============================================================================

function WarningBanner() {
  return (
    <details className="gr-warning" open>
      <summary className="gr-warning-summary">
        <span className="gr-warning-icon">
          <md-icon>shield</md-icon>
        </span>
        <span className="gr-warning-title">Cette fiche ne remplace pas une visite sur site</span>
        <md-icon className="gr-warning-chevron">expand_more</md-icon>
      </summary>

      <div className="gr-warning-body">
        {/* Ce document peut vous aider à */}
        <div className="gr-warning-col gr-warning-col--yes">
          <div className="gr-warning-col-header">
            <span className="gr-status-icon gr-status-icon--yes">
              <md-icon>check</md-icon>
            </span>
            <span className="gr-warning-col-title">CE DOCUMENT PEUT VOUS AIDER À</span>
          </div>
          <ul className="gr-warning-list">
            <li>
              <span className="gr-status-icon gr-status-icon--yes gr-status-icon--sm">
                <md-icon>check</md-icon>
              </span>
              S'informer sur les caractéristiques techniques d'un bâtiment
            </li>
            <li>
              <span className="gr-status-icon gr-status-icon--yes gr-status-icon--sm">
                <md-icon>check</md-icon>
              </span>
              Obtenir des ordres de grandeur sur les performances thermiques, énergétiques et les émissions GES du bâtiment
            </li>
            <li>
              <span className="gr-status-icon gr-status-icon--yes gr-status-icon--sm">
                <md-icon>check</md-icon>
              </span>
              Préparer une mission en disposant d'une base structurée
            </li>
          </ul>
        </div>

        {/* Ce document ne peut pas */}
        <div className="gr-warning-col gr-warning-col--no">
          <div className="gr-warning-col-header">
            <span className="gr-status-icon gr-status-icon--no">
              <md-icon>close</md-icon>
            </span>
            <span className="gr-warning-col-title">CE DOCUMENT NE PEUT PAS</span>
          </div>
          <ul className="gr-warning-list">
            <li>
              <span className="gr-status-icon gr-status-icon--no gr-status-icon--sm">
                <md-icon>close</md-icon>
              </span>
              Remplacer la visite sur site et les relevés effectués par un professionnel qualifié — aucune donnée n'est issue d'une inspection physique du bâtiment
            </li>
            <li>
              <span className="gr-status-icon gr-status-icon--no gr-status-icon--sm">
                <md-icon>close</md-icon>
              </span>
              Engager la responsabilité du CSTB ou de Go Rénove sur la véracité des données affichées ni sur les décisions prises sur leur fondement
            </li>
          </ul>
        </div>
      </div>
    </details>
  );
}

// =============================================================================
//   Section : Identification du bâtiment
// =============================================================================

function IdentificationSection({ b, report }: { b: BdnbBatiment; report: RisqueReport }) {
  const parcelles = b.l_parcelle_id?.length
    ? b.l_parcelle_id.join(', ')
    : null;

  const usage = b.usage_principal_bdnb_open || b.usage_niveau_1_txt || null;

  const qpvMonument = (() => {
    const parts: string[] = [];
    if (b.zone_plu_bati_patrimonial) parts.push('Bâti patrimonial (PLU)');
    if (b.perimetre_bat_historique) parts.push('Périmètre monument historique');
    if (b.contrainte_urbanisme_ac1) parts.push('Contrainte urbanisme AC1');
    return parts.length ? parts.join(' · ') : 'Aucun';
  })();

  return (
    <GrSection
      title="Identification du bâtiment"
      sectionId="ID"
      source="BAN · RNC · Cadastre"
    >
      <div className="gr-card-grid">
        <DataCard
          label="Commune"
          value={b.libelle_commune_insee || null}
          sub={b.code_commune_insee ? `INSEE : ${b.code_commune_insee}` : undefined}
        />
        <DataCard label="Identifiant parcelle" value={parcelles} />
        <DataCard label="Catégorie d'usage du bâtiment" value={usage ? capFirst(usage) : null} />
        <DataCard
          label="Altitude"
          value={b.altitude_sol_mean != null ? `${fmtNum(b.altitude_sol_mean, 1)} m` : null}
        />
        <DataCard label="QPV / Monument historique" value={qpvMonument} />
        <DataCard
          label="Emprise au sol"
          value={b.surface_emprise_sol != null ? `${fmtNum(b.surface_emprise_sol)} m²` : null}
        />
        <DataCard
          label="Hauteur moyenne"
          value={b.hauteur_mean != null ? `${fmtNum(b.hauteur_mean, 1)} m` : null}
        />
        <DataCard
          label="Étages (niveaux)"
          value={b.nb_niveau != null ? String(fmtNum(b.nb_niveau)) : null}
        />
        <DataCard
          label="Logements"
          value={b.nb_log != null ? String(fmtNum(b.nb_log)) : null}
        />
        <DataCard
          label="Fiabilité de l'adresse"
          value={b.fiabilite_cr_adr_niv_1 || null}
        />
        <DataCard
          label="Code département"
          value={b.code_departement_insee ? `${b.code_departement_insee}` : null}
        />
        <DataCard label="Code région" value={b.code_region_insee || null} />
      </div>
    </GrSection>
  );
}

// =============================================================================
//   Section : Enveloppe opaque
// =============================================================================

function EnveloppeOpaqueSection({ b }: { b: BdnbBatiment }) {
  return (
    <GrSection
      title="Enveloppe opaque"
      icon="layers"
      source="DPE ADEME 2021"
    >
      <div className="gr-card-grid gr-card-grid--icon">
        <IconDataCard
          icon="house_siding"
          label="Matériaux mur extérieur"
          value={b.mat_mur_txt ? capFirst(b.mat_mur_txt) : null}
          sub={b.materiaux_structure_mur_exterieur ? capFirst(b.materiaux_structure_mur_exterieur) : undefined}
        />
        <IconDataCard
          icon="roofing"
          label="Matériaux toiture"
          value={b.mat_toit_txt ? capFirst(b.mat_toit_txt) : null}
        />
        <IconDataCard
          icon="house_siding"
          label="Type d'isolation du mur extérieur"
          value={b.type_isolation_mur_exterieur ? capFirst(b.type_isolation_mur_exterieur) : null}
          tone={!b.type_isolation_mur_exterieur ? 'warn' : 'normal'}
        />
        <IconDataCard
          icon="arrow_downward"
          label="Type d'isolation du plancher bas"
          value={b.type_isolation_plancher_bas ? capFirst(b.type_isolation_plancher_bas) : null}
          tone={!b.type_isolation_plancher_bas ? 'warn' : 'normal'}
        />
        <IconDataCard
          icon="arrow_upward"
          label="Type d'isolation du plancher haut"
          value={b.type_isolation_plancher_haut ? capFirst(b.type_isolation_plancher_haut) : null}
          tone={!b.type_isolation_plancher_haut ? 'warn' : 'normal'}
        />
        <IconDataCard
          icon="floor"
          label="Nature du plancher bas"
          value={b.type_plancher_bas_deperditif ? capFirst(b.type_plancher_bas_deperditif) : null}
          sub={b.u_plancher_bas_final_deperditif != null
            ? `U = ${b.u_plancher_bas_final_deperditif.toFixed(2)} W/m²·K`
            : undefined}
        />
        <IconDataCard
          icon="roofing"
          label="Nature du plancher haut"
          value={b.type_plancher_haut_deperditif ? capFirst(b.type_plancher_haut_deperditif) : null}
          sub={b.u_plancher_haut_deperditif != null
            ? `U = ${b.u_plancher_haut_deperditif.toFixed(2)} W/m²·K`
            : undefined}
        />
        <IconDataCard
          icon="thermostat"
          label="Coefficient U mur extérieur"
          value={b.u_mur_exterieur != null ? `${b.u_mur_exterieur.toFixed(2)} W/m²·K` : null}
          sub="Performance thermique (plus bas = mieux isolé)"
        />
      </div>
    </GrSection>
  );
}

// =============================================================================
//   Section : Enveloppe vitrée
// =============================================================================

function EnveloppeVitreeSection({ b }: { b: BdnbBatiment }) {
  return (
    <GrSection
      title="Enveloppe vitrée"
      icon="window"
      source="DPE ADEME 2021"
    >
      <div className="gr-card-grid gr-card-grid--icon">
        <IconDataCard
          icon="window"
          label="Type du vitrage"
          value={b.type_vitrage ? capFirst(b.type_vitrage) : null}
          sub={b.vitrage_vir ? 'Vitrage à faible émissivité (VIR)' : undefined}
        />
        <IconDataCard
          icon="thermostat"
          label="Coefficient Uw (baie)"
          value={b.u_baie_vitree != null ? `${b.u_baie_vitree.toFixed(2)} W/m²·K` : null}
          sub={b.facteur_solaire_baie_vitree != null
            ? `Facteur solaire : ${b.facteur_solaire_baie_vitree.toFixed(2)}`
            : 'Plus bas = mieux isolé'}
        />
        <IconDataCard
          icon="construction"
          label="Menuiserie"
          value={b.type_materiaux_menuiserie ? capFirst(b.type_materiaux_menuiserie) : null}
          sub={b.type_fermeture ? capFirst(b.type_fermeture) : undefined}
        />
        <IconDataCard
          icon="blur_on"
          label="Lame / gaz de remplissage"
          value={
            b.epaisseur_lame != null || b.type_gaz_lame
              ? `${b.epaisseur_lame != null ? `${b.epaisseur_lame} mm` : '—'}${b.type_gaz_lame ? ` · ${capFirst(b.type_gaz_lame)}` : ''}`
              : null
          }
        />
        <IconDataCard
          icon="photo_size_select_large"
          label="Ratio de surface vitrée"
          value={b.pourcentage_surface_baie_vitree_exterieur != null
            ? `${(b.pourcentage_surface_baie_vitree_exterieur * 100).toFixed(0)} %`
            : null}
        />
      </div>
    </GrSection>
  );
}

// =============================================================================
//   Section : Systèmes d'énergie
// =============================================================================

function SystemesEnergieSection({ b }: { b: BdnbBatiment }) {
  const hasEnr = b.batenr_favorabilite_solaire_thermique != null
    || b.batenr_favorabilite_geothermie_sonde != null
    || b.batenr_favorabilite_geothermie_nappe != null;

  return (
    <GrSection
      title="Systèmes d'énergie"
      icon="wb_sunny"
      source="DPE ADEME · BDNB"
    >
      <div className="gr-card-grid gr-card-grid--array">
        {/* Chauffage */}
        <ArrayCard
          icon="fireplace"
          title="Chauffage principal"
          rows={[
            { label: 'Énergie de chauffage', value: b.type_energie_chauffage },
            { label: 'Générateur de chauffage', value: b.type_generateur_chauffage },
            {
              label: 'Installation',
              value: b.type_installation_chauffage
                ? capFirst(b.type_installation_chauffage)
                : null,
            },
            {
              label: 'Chauffage d\'appoint',
              value:
                b.type_energie_chauffage_appoint || b.type_generateur_chauffage_appoint
                  ? [b.type_energie_chauffage_appoint, b.type_generateur_chauffage_appoint]
                      .filter((x): x is string => !!x)
                      .map(capFirst)
                      .join(' · ')
                  : null,
            },
          ]}
          tone={!b.type_energie_chauffage ? 'warn' : 'normal'}
        />

        {/* Eau chaude sanitaire */}
        <ArrayCard
          icon="shower"
          title="Eau chaude sanitaire"
          rows={[
            { label: 'Générateur ECS', value: b.type_generateur_ecs },
            {
              label: 'Installation',
              value: b.type_installation_ecs ? capFirst(b.type_installation_ecs) : null,
            },
            { label: 'ECS solaire', value: boolVal(b.ecs_solaire) },
          ]}
          tone={!b.type_generateur_ecs ? 'warn' : 'normal'}
        />

        {/* Climatisation / refroidissement */}
        <ArrayCard
          icon="ac_unit"
          title="Climatisation"
          rows={[
            {
              label: 'Générateur de climatisation',
              value: b.type_generateur_climatisation,
            },
            {
              label: 'Ancienneté',
              value: b.type_generateur_climatisation_anciennete
                ? capFirst(b.type_generateur_climatisation_anciennete)
                : null,
            },
          ]}
          tone={!b.type_generateur_climatisation ? 'warn' : 'normal'}
        />

        {/* Ventilation */}
        <ArrayCard
          icon="air"
          title="Ventilation"
          rows={[
            { label: 'Système de ventilation', value: b.type_ventilation },
          ]}
          tone={!b.type_ventilation ? 'warn' : 'normal'}
        />

        {/* Énergie renouvelable */}
        <ArrayCard
          icon="solar_power"
          title="Énergie renouvelable"
          rows={[
            {
              label: 'Production ENR',
              value: b.type_production_energie_renouvelable,
            },
            {
              label: 'Favorabilité solaire thermique',
              value: hasEnr && b.batenr_favorabilite_solaire_thermique != null
                ? (b.batenr_favorabilite_solaire_thermique ? 'Favorable' : 'Non favorable')
                : null,
            },
            {
              label: 'Favorabilité géothermie (sonde)',
              value: b.batenr_favorabilite_geothermie_sonde != null
                ? (b.batenr_favorabilite_geothermie_sonde ? 'Favorable' : 'Non favorable')
                : null,
            },
            {
              label: 'Potentiel solaire annuel',
              value: b.batenr_potentiel_prod_solaire_thermique_annuelle != null
                ? `${fmtNum(b.batenr_potentiel_prod_solaire_thermique_annuelle, 1)} MWh/an`
                : null,
            },
          ]}
          tone="normal"
        />
      </div>
    </GrSection>
  );
}

// =============================================================================
//   Section : Performances énergétiques
// =============================================================================

function PerformancesSection({ b }: { b: BdnbBatiment }) {
  const dpe = b.classe_bilan_dpe?.toUpperCase() || null;
  /* DPE officiel (story C4) : un DPE réel recensé sur le bâtiment porte un
     identifiant ADEME ; à défaut, seule l'estimation moyenne BDNB s'affiche. */
  const dpeOfficiel = b.identifiant_dpe || null;
  const dpeCounts: Record<string, number | null | undefined> = {
    A: b.nb_classe_bilan_dpe_a,
    B: b.nb_classe_bilan_dpe_b,
    C: b.nb_classe_bilan_dpe_c,
    D: b.nb_classe_bilan_dpe_d,
    E: b.nb_classe_bilan_dpe_e,
    F: b.nb_classe_bilan_dpe_f,
    G: b.nb_classe_bilan_dpe_g,
  };
  const dpeDistribution = DPE_LETTERS
    .map((letter) => ({ letter, count: Number(dpeCounts[letter] ?? 0) }))
    .filter((d) => d.count > 0);
  const dpeTotal = dpeDistribution.reduce((s, d) => s + d.count, 0);

  return (
    <GrSection
      title="Performances énergétiques"
      icon="energy"
      source="DPE ADEME · BDNB"
    >
      {/* DPE officiel recensé (logements réellement diagnostiqués) */}
      {dpeOfficiel && (
        <div className="gr-dpe-officiel">
          <div className="gr-dpe-officiel-head">
            <span className="gr-dpe-officiel-badge">
              <md-icon>verified</md-icon>
              DPE officiel
            </span>
            <span className="gr-dpe-officiel-id">n° {dpeOfficiel}</span>
          </div>
          {b.date_reception_dpe && (
            <span className="gr-dpe-officiel-date">
              Reçu le {b.date_reception_dpe.slice(0, 10)}
            </span>
          )}
          {dpeTotal > 0 && (
            <div className="gr-dpe-distrib">
              {dpeDistribution.map((d) => (
                <span
                  key={d.letter}
                  className="gr-dpe-distrib-chip"
                  style={{ '--dpe-color': DPE_COLORS[d.letter.toLowerCase()] } as React.CSSProperties}
                >
                  <b>{d.letter}</b> {d.count}
                </span>
              ))}
              <span className="gr-dpe-distrib-total">
                {dpeTotal} DPE recensé{dpeTotal > 1 ? 's' : ''}
              </span>
            </div>
          )}
        </div>
      )}
      {/* Échelle DPE A–G */}
      <div className="gr-dpe-wrapper">
        <div className="gr-dpe-label-col">
          <md-icon>bolt</md-icon>
          <span className="gr-dpe-label-text">DPE bâtiment</span>
        </div>
        <div className="gr-dpe-scale-card">
          <div className="gr-dpe-scale">
            {DPE_LETTERS.map((letter) => {
              const active = letter === dpe;
              const color = DPE_COLORS[letter.toLowerCase()];
              return (
                <div
                  key={letter}
                  className={`gr-dpe-pill${active ? ' active' : ''}`}
                  style={{ '--dpe-color': color } as React.CSSProperties}
                >
                  {letter}
                </div>
              );
            })}
          </div>
          <div className="gr-dpe-scale-info">
            {dpe
              ? `Étiquette ${dpe} — estimation BDNB (moyenne bâtiment)`
              : 'Étiquette DPE non renseignée dans la BDNB (estimation)'}
          </div>
        </div>
      </div>

      {/* Conso + GES */}
      <div className="gr-perf-cards">
        <div className="gr-perf-card">
          <div className="gr-perf-card-label">
            <md-icon>bolt</md-icon>
            <span>Estimation consommation énergie finale</span>
          </div>
          <div className="gr-perf-card-value">
            {b.conso_5_usages_ep_m2 != null
              ? `${fmtNum(b.conso_5_usages_ep_m2, 0)} kWh/m²/an`
              : <span className="gr-na">Données de performance indisponibles</span>}
          </div>
        </div>
        <div className="gr-perf-card">
          <div className="gr-perf-card-label">
            <md-icon>cloud</md-icon>
            <span>Émissions GES</span>
          </div>
          <div className="gr-perf-card-value">
            {b.emission_ges_5_usages_m2 != null
              ? (
                <>
                  <strong>{fmtNum(b.emission_ges_5_usages_m2, 2)} kgCO₂/m²/an</strong>
                  <span className="gr-perf-sub">Estimation BDNB</span>
                </>
              )
              : <span className="gr-na">Données de performance indisponibles</span>}
          </div>
        </div>
      </div>
    </GrSection>
  );
}

// =============================================================================
//   Section : Confort des occupants
// =============================================================================

function ConfortSection({ b }: { b: BdnbBatiment }) {
  const hasComfort = Boolean(b.classe_inertie || b.traversant);

  if (!hasComfort) return null;

  return (
    <GrSection title="Confort des occupants" icon="thermostat" source="BDNB">
      <div className="gr-comfort-grid">
        {b.classe_inertie && (
          <div className="gr-comfort-item">
            <md-icon>thermostat</md-icon>
            <div>
              <span className="gr-comfort-label">Classe d'inertie</span>
              <span className="gr-comfort-value">{capFirst(b.classe_inertie)}</span>
            </div>
          </div>
        )}
        {b.traversant && (
          <div className="gr-comfort-item">
            <md-icon>compare_arrows</md-icon>
            <div>
              <span className="gr-comfort-label">Traversant</span>
              <span className="gr-comfort-value">{capFirst(b.traversant)}</span>
            </div>
          </div>
        )}
      </div>
    </GrSection>
  );
}

// =============================================================================
//   Blocs réutilisables
// =============================================================================

function GrSection({
  title,
  sectionId,
  icon,
  source,
  children,
}: {
  title: string;
  sectionId?: string;
  icon?: string;
  source: string;
  children: ReactNode;
}) {
  return (
    <details className="gr-section" open>
      <summary className="gr-section-header">
        <div className="gr-section-icon">
          {sectionId ? (
            <span className="gr-section-id-text">{sectionId}</span>
          ) : icon ? (
            <md-icon>{icon}</md-icon>
          ) : null}
        </div>
        <div className="gr-section-meta">
          <span className="gr-section-title">{title}</span>
          <span className="gr-section-source">Sources : {source}</span>
        </div>
        <md-icon className="gr-section-chevron" aria-hidden="true">expand_more</md-icon>
      </summary>
      <div className="gr-section-body">{children}</div>
    </details>
  );
}

function DataCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string | null | undefined;
  sub?: string;
}) {
  const display = value ?? NA;
  const isNa = value == null || value === '';
  return (
    <div className="gr-data-card">
      <span className="gr-data-card-label">{label}</span>
      <span className={`gr-data-card-value${isNa ? ' gr-na' : ''}`}>{display}</span>
      {sub && <span className="gr-data-card-sub">{sub}</span>}
    </div>
  );
}

function IconDataCard({
  icon,
  label,
  value,
  sub,
  tone = 'normal',
}: {
  icon: string;
  label: string;
  value: string | null | undefined;
  sub?: string;
  tone?: 'normal' | 'warn';
}) {
  const display = value ?? NA;
  const isNa = value == null || value === '';
  return (
    <div className={`gr-data-card gr-data-card--icon${tone === 'warn' ? ' gr-data-card--warn' : ''}`}>
      <span className="gr-data-card-icon"><md-icon>{icon}</md-icon></span>
      <div className="gr-data-card-content">
        <span className="gr-data-card-label">{label}</span>
        <span className={`gr-data-card-value${isNa ? ' gr-na' : ''}`}>{display}</span>
        {sub && <span className="gr-data-card-sub">{sub}</span>}
      </div>
    </div>
  );
}

function ArrayCard({
  icon,
  title,
  rows,
  tone = 'normal',
}: {
  icon: string;
  title: string;
  rows: { label: string; value: string | null | undefined }[];
  tone?: 'normal' | 'warn';
}) {
  return (
    <div className={`gr-array-card${tone === 'warn' ? ' gr-array-card--warn' : ''}`}>
      <div className="gr-array-card-header">
        <span className="gr-array-card-icon"><md-icon>{icon}</md-icon></span>
        <span className="gr-array-card-title">{title}</span>
      </div>
      <div className="gr-array-card-rows">
        {rows.map((r) => (
          <div key={r.label} className="gr-array-card-row">
            <span className="gr-array-card-row-label">{r.label}</span>
            <span className={`gr-array-card-row-value${r.value == null ? ' gr-na' : ''}`}>
              {r.value ?? NA}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}


