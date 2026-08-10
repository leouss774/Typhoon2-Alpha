// =============================================================================
//   TYPHOON — /zone : étape 3 « Analyse » — fiche bâtiment BDNB
//   Quatre vues Material 3 (md-tabs) : Synthèse · Construction · Énergie ·
//   Cadre & foncier. Consomme report.bdnb (batiment_groupe_complet, v0.7).
//   Gère les états vides : adresse non diagnostiquée / BDNB indisponible
//   (les champs null → « Donnée non renseignée », jamais un plantage).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import type { BdnbBatiment, RisqueReport } from '../zone/config';
import { BdnbMap } from './BdnbMap';

const N_A = 'Donnée non renseignée';

const USAGE_ICONS: Record<string, string> = {
  'résidentiel individuel': 'house',
  'résidentiel collectif': 'apartment',
  'commerces et services': 'storefront',
  industriel: 'factory',
  tertiaire: 'business_center',
  agricole: 'agriculture',
};
const USAGE_FALLBACK = 'domain';

const DPE_COLORS: Record<string, string> = {
  a: '#3aa76d', b: '#7cc45c', c: '#c3d84a', d: '#f0e24a', e: '#f2a33c', f: '#ec6c2b', g: '#d92c2c',
};

const TABS = [
  { id: 'synthese', label: 'Synthèse', icon: 'dashboard' },
  { id: 'construction', label: 'Construction', icon: 'bricks' },
  { id: 'energie', label: 'Énergie', icon: 'energy' },
  { id: 'cadre', label: 'Cadre & foncier', icon: 'account_balance' },
] as const;

export function ZoneAnalyse({ report }: { report: RisqueReport | null }) {
  const [tab, setTab] = useState(0);
  const tabsRef = useRef<HTMLElement & { activeTabIndex: number } | null>(null);

  const bdnb = report?.bdnb;
  const batiment = bdnb?.batiment || null;

  /* md-tabs émet un événement `change` natif — on resynchronise l'état React.
     Dépend de `batiment` : le listener se rattache quand les onglets sont
     remontés (nouveau diagnostic → report null → nouveau rapport). */
  useEffect(() => {
    const el = tabsRef.current;
    if (!el) return;
    const onChange = () => setTab(el.activeTabIndex);
    el.addEventListener('change', onChange);
    return () => el.removeEventListener('change', onChange);
  }, [batiment]);

  if (!report) {
    return (
      <div className="analyse-empty">
        <md-icon>home_work</md-icon>
        <h2>Fiche bâtiment indisponible</h2>
        <p>Diagnostiquez d'abord une adresse pour afficher la fiche BDNB du bâtiment.</p>
      </div>
    );
  }

  if (!batiment) {
    const err = (report.erreurs_partielles || []).find((e) =>
      e.toLowerCase().startsWith('bdnb')
    );
    return (
      <div className="analyse-empty">
        <md-icon>domain_disabled</md-icon>
        <h2>BDNB indisponible pour cette adresse</h2>
        <p>
          La BDNB (Base de Données Nationale des Bâtiments) ne référence pas de
          bâtiment à cette adresse exacte. Sa couverture est large mais pas
          exhaustive — essayez une adresse voisine.
        </p>
        {err ? <span className="empty-detail">{err}</span> : null}
      </div>
    );
  }

  return (
    <div className="analyse-wrap">
      <header className="analyse-header">
        <div className="analyse-title">
          <h2>Analyse du bâti — BDNB</h2>
          <p className="analyse-meta">
            {report.adresse_normalisee} ·{' '}
            {batiment.libelle_commune_insee ||
              `INSEE ${batiment.code_commune_insee || report.code_insee}`}
          </p>
          {batiment.cle_interop_adr ? (
            <p className="analyse-meta mono">clé interop BDNB : {batiment.cle_interop_adr}</p>
          ) : null}
        </div>
        <span className="src-chip">
          <md-icon>database</md-icon>BDNB · api.bdnb.io
        </span>
      </header>

      <md-tabs ref={tabsRef} className="analyse-tabs">
        {TABS.map((t) => (
          <md-primary-tab key={t.id} inline-icon>
            <md-icon slot="icon">{t.icon}</md-icon>
            {t.label}
          </md-primary-tab>
        ))}
      </md-tabs>

      <div className="analyse-body">
        {tab === 0 && <SyntheseView b={batiment} report={report} />}
        {tab === 1 && <ConstructionView b={batiment} />}
        {tab === 2 && <EnergieView b={batiment} />}
        {tab === 3 && <CadreView b={batiment} />}
      </div>
    </div>
  );
}

/* ─────────────────────────── Synthèse ─────────────────────────── */

function SyntheseView({ b, report }: { b: BdnbBatiment; report: RisqueReport }) {
  const usage = b.usage_principal_bdnb_open || b.usage_niveau_1_txt || null;
  const usageIcon = usage
    ? USAGE_ICONS[usage.toLowerCase()] || USAGE_FALLBACK
    : USAGE_FALLBACK;
  const age =
    typeof b.annee_construction === 'number'
      ? new Date().getFullYear() - b.annee_construction
      : null;

  return (
    <div className="analyse-grid">
      <div className="usage-hero">
        <span className="usage-icon">
          <md-icon>{usageIcon}</md-icon>
        </span>
        <div>
          <span className="usage-label">Usage principal</span>
          <span className="usage-value">{usage || N_A}</span>
        </div>
      </div>

      <div className="stat-grid">
        <StatCard
          icon="calendar_today"
          label="Année de construction"
          value={b.annee_construction != null ? fmtNum(b.annee_construction) : null}
          sub={age != null ? `${age} ans` : null}
        />
        <StatCard
          icon="height"
          label="Hauteur moyenne"
          value={b.hauteur_mean != null ? `${fmtNum(b.hauteur_mean)} m` : null}
        />
        <StatCard
          icon="stairs"
          label="Niveaux"
          value={b.nb_niveau != null ? fmtNum(b.nb_niveau) : null}
        />
        <StatCard
          icon="square_foot"
          label="Emprise au sol"
          value={b.surface_emprise_sol != null ? `${fmtNum(b.surface_emprise_sol)} m²` : null}
        />
        <StatCard
          icon="door_front"
          label="Logements"
          value={b.nb_log != null ? fmtNum(b.nb_log) : null}
        />
      </div>

      <div className="analyse-cols">
        <SectionCard title="Emprise du bâtiment" icon="crop_square">
          <BdnbMap batiment={b} report={report} />
          <p className="footprint-note">
            Emprise BDNB (Lambert-93) · Parcelles cadastrales IGN Géoplateforme ·
            © OpenStreetMap contributors
          </p>
        </SectionCard>

        <SectionCard title="Contexte & protections" icon="policy">
          <div className="badge-row">
            <BoolBadge
              cond={b.zone_plu_bati_patrimonial}
              label="Bâti patrimonial (PLU)"
              icon="account_balance"
            />
            <BoolBadge
              cond={b.perimetre_bat_historique}
              label="Périmètre monument historique"
              icon="museum"
            />
            <BoolBadge
              cond={b.contrainte_urbanisme_ac1}
              label="Contrainte urbanisme AC1"
              icon="gavel"
            />
            {b.alea_argile ? (
              <Badge icon="grass" label={`Argile : ${cap(b.alea_argile)}`} tone="warn" />
            ) : null}
          </div>
          <div className="kv-list">
            <Kv k="Commune" v={b.libelle_commune_insee} />
            <Kv k="Fiabilité de l'adresse" v={b.fiabilite_cr_adr_niv_1} />
          </div>
        </SectionCard>
      </div>
    </div>
  );
}

/* ─────────────────────────── Construction ─────────────────────────── */

function ConstructionView({ b }: { b: BdnbBatiment }) {
  return (
    <div className="analyse-grid">
      <div className="mat-grid">
        <MatCard icon="bricks" label="Matériau des murs" value={b.mat_mur_txt} />
        <MatCard icon="roofing" label="Matériau de toiture" value={b.mat_toit_txt} />
      </div>

      <SectionCard title="Dimensions du bâtiment" icon="straighten">
        <div className="stat-grid compact">
          <StatCard
            icon="height"
            label="Hauteur moyenne"
            value={b.hauteur_mean != null ? `${fmtNum(b.hauteur_mean)} m` : null}
          />
          <StatCard
            icon="stairs"
            label="Niveaux"
            value={b.nb_niveau != null ? fmtNum(b.nb_niveau) : null}
          />
          <StatCard
            icon="square_foot"
            label="Emprise au sol"
            value={b.surface_emprise_sol != null ? `${fmtNum(b.surface_emprise_sol)} m²` : null}
          />
          <StatCard
            icon="terrain"
            label="Altitude du sol"
            value={b.altitude_sol_mean != null ? `${fmtNum(b.altitude_sol_mean)} m` : null}
          />
          <StatCard
            icon="door_front"
            label="Logements"
            value={b.nb_log != null ? fmtNum(b.nb_log) : null}
          />
        </div>
      </SectionCard>

      <SectionCard title="Fiabilité des données BDNB" icon="verified_user">
        <div className="kv-list">
          <Kv k="Adresse (croisement)" v={b.fiabilite_cr_adr_niv_1} />
          <Kv k="Voisinage à l'adresse" v={b.fiabilite_cr_adr_niv_2} />
          <Kv k="Hauteur" v={b.fiabilite_hauteur} />
          <Kv k="Emprise au sol" v={b.fiabilite_emprise_sol} />
        </div>
      </SectionCard>
    </div>
  );
}

/* ─────────────────────────── Énergie ─────────────────────────── */

function EnergieView({ b }: { b: BdnbBatiment }) {
  const dpe = b.classe_bilan_dpe ? b.classe_bilan_dpe.toUpperCase() : null;
  const dpeColor = dpe ? DPE_COLORS[dpe.toLowerCase()] || '#8a8f98' : null;

  return (
    <div className="analyse-grid">
      <SectionCard title="Diagnostic de performance énergétique" icon="energy">
        {dpe && dpeColor ? (
          <div className="dpe-row">
            <span className="dpe-badge" style={{ background: dpeColor }}>
              {dpe}
            </span>
            <div>
              <span className="dpe-label">Classe bilan DPE</span>
              <span className="dpe-sub">
                Étiquette énergie de l'ensemble du bâtiment (BDNB)
              </span>
            </div>
          </div>
        ) : (
          <p className="na-notice">
            Aucun DPE renseigné dans la BDNB pour ce bâtiment — fréquent sur les
            bâtiments anciens.
          </p>
        )}
        <div className="kv-list">
          <Kv
            k="Consommation 5 usages"
            v={
              b.conso_5_usages_ep_m2 != null
                ? `${fmtNum(b.conso_5_usages_ep_m2)} kWh/m²/an`
                : null
            }
          />
          <Kv
            k="Émissions GES"
            v={
              b.emission_ges_5_usages_m2 != null
                ? `${fmtNum(b.emission_ges_5_usages_m2)} kg CO₂/m²/an`
                : null
            }
          />
          <Kv k="Date de réception du DPE" v={b.date_reception_dpe} />
          <Kv k="Type de bâtiment (DPE)" v={b.type_batiment_dpe} />
        </div>
      </SectionCard>

      <SectionCard title="Chauffage & équipements" icon="local_fire_department">
        <div className="kv-list">
          <Kv k="Énergie de chauffage" v={b.type_energie_chauffage} />
          <Kv k="Générateur de chauffage" v={b.type_generateur_chauffage} />
          <Kv k="Production d'énergie renouvelable" v={b.type_production_energie_renouvelable} />
        </div>
      </SectionCard>

      <SectionCard title="Isolation & vitrage" icon="window">
        <div className="kv-list">
          <Kv k="Isolation murs extérieurs" v={b.type_isolation_mur_exterieur} />
          <Kv k="Isolation plancher haut" v={b.type_isolation_plancher_haut} />
          <Kv k="Isolation plancher bas" v={b.type_isolation_plancher_bas} />
          <Kv k="Type de vitrage" v={b.type_vitrage} />
        </div>
      </SectionCard>

      <SectionCard title="Potentiel énergies renouvelables" icon="wb_sunny">
        <div className="badge-row">
          <BoolBadge
            cond={b.batenr_favorabilite_solaire_thermique}
            label="Solaire thermique"
            icon="wb_sunny"
          />
          <BoolBadge
            cond={b.batenr_favorabilite_geothermie_sonde}
            label="Géothermie (sonde)"
            icon="landscape"
          />
          <BoolBadge
            cond={b.batenr_favorabilite_geothermie_nappe}
            label="Géothermie (nappe)"
            icon="water"
          />
        </div>
        <div className="kv-list">
          <Kv
            k="Potentiel solaire thermique annuel"
            v={
              b.batenr_potentiel_prod_solaire_thermique_annuelle != null
                ? `${fmtNum(b.batenr_potentiel_prod_solaire_thermique_annuelle, 1)} MWh/an`
                : null
            }
          />
          <Kv
            k="Potentiel solaire thermique (été)"
            v={
              b.batenr_potentiel_prod_solaire_thermique_ete != null
                ? `${fmtNum(b.batenr_potentiel_prod_solaire_thermique_ete, 1)} MWh`
                : null
            }
          />
        </div>
      </SectionCard>
    </div>
  );
}

/* ─────────────────────────── Cadre & foncier ─────────────────────────── */

function CadreView({ b }: { b: BdnbBatiment }) {
  return (
    <div className="analyse-grid">
      <SectionCard title="Commune & territoire" icon="location_city">
        <div className="kv-list">
          <Kv k="Commune" v={b.libelle_commune_insee} />
          <Kv k="Code INSEE" v={b.code_commune_insee} />
          <Kv k="Département" v={b.code_departement_insee} />
          <Kv k="Région" v={b.code_region_insee} />
          <Kv k="EPCI" v={b.code_epci_insee} />
          <Kv k="IRIS" v={b.code_iris} />
        </div>
      </SectionCard>

      <SectionCard title="Parcelles & adresses" icon="crop_landscape">
        {b.l_parcelle_id?.length ? (
          <div className="chip-row">
            {b.l_parcelle_id.map((p) => (
              <span className="parcelle-chip" key={p}>
                {p}
              </span>
            ))}
          </div>
        ) : (
          <p className="na-notice">{N_A}</p>
        )}
        <div className="kv-list">
          <Kv k="Adresses BAN validées" v={b.nb_adresse_valid_ban != null ? fmtNum(b.nb_adresse_valid_ban) : null} />
          <Kv k="Adresse principale" v={b.libelle_adr_principale_ban} />
        </div>
      </SectionCard>

      <SectionCard title="Patrimoine & urbanisme" icon="museum">
        <div className="kv-list">
          <Kv
            k="Monument historique le plus proche"
            v={b.nom_batiment_historique_plus_proche || b.denomination_monument_historique}
          />
          <Kv
            k="Distance au monument"
            v={b.distance_monument_historique != null ? `${fmtNum(b.distance_monument_historique)} m` : null}
          />
          <Kv k="Bâti patrimonial (PLU)" v={boolTxt(b.zone_plu_bati_patrimonial)} />
          <Kv k="Périmètre monument historique" v={boolTxt(b.perimetre_bat_historique)} />
          <Kv k="Contrainte d'urbanisme AC1" v={boolTxt(b.contrainte_urbanisme_ac1)} />
        </div>
      </SectionCard>

      <SectionCard title="Identifiants BDNB" icon="database">
        <div className="kv-list mono">
          <Kv k="Groupe de bâtiments" v={b.batiment_groupe_id} />
          <Kv k="Clé d'interopérabilité adresse" v={b.cle_interop_adr} />
        </div>
      </SectionCard>
    </div>
  );
}

/* ─────────────────────────── Blocs réutilisables ─────────────────────────── */

function StatCard({
  icon,
  label,
  value,
  sub,
}: {
  icon: string;
  label: string;
  value: string | null;
  sub?: string | null;
}) {
  return (
    <div className="stat-card">
      <md-icon>{icon}</md-icon>
      <div className="stat-body">
        <span className="stat-label">{label}</span>
        <span className={`stat-value${value == null ? ' na' : ''}`}>{value ?? N_A}</span>
        {sub ? <span className="stat-sub">{sub}</span> : null}
      </div>
    </div>
  );
}

function SectionCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: ReactNode;
}) {
  return (
    <section className="analyse-section">
      <h3>
        <md-icon>{icon}</md-icon>
        {title}
      </h3>
      {children}
    </section>
  );
}

function MatCard({
  icon,
  label,
  value,
}: {
  icon: string;
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div className="mat-card">
      <span className="usage-icon">
        <md-icon>{icon}</md-icon>
      </span>
      <span className="mat-label">{label}</span>
      <span className="mat-value">{value ? cap(value) : N_A}</span>
    </div>
  );
}

function Kv({ k, v }: { k: string; v: string | number | null | undefined }) {
  const str = v == null || v === '' ? null : String(v);
  return (
    <div className="kv">
      <span className="kv-k">{k}</span>
      <span className={str == null ? 'kv-v na' : 'kv-v'}>{str ?? N_A}</span>
    </div>
  );
}

function BoolBadge({
  cond,
  label,
  icon,
}: {
  cond: boolean | null | undefined;
  label: string;
  icon: string;
}) {
  if (cond == null) return <Badge icon={icon} label={label} tone="na" />;
  return cond ? (
    <Badge icon={icon} label={label} tone="yes" />
  ) : (
    <Badge icon={icon} label={label} tone="no" />
  );
}

function Badge({
  icon,
  label,
  tone,
}: {
  icon: string;
  label: string;
  tone: 'yes' | 'no' | 'warn' | 'na';
}) {
  return (
    <span className={`info-badge ${tone}`}>
      <md-icon>{icon}</md-icon>
      {label}
    </span>
  );
}

/* ─────────────────────────── Helpers ─────────────────────────── */

function fmtNum(v: number, digits = 0): string {
  return v.toLocaleString('fr-FR', { maximumFractionDigits: digits });
}

function boolTxt(v: boolean | null | undefined): string | null {
  if (v == null) return null;
  return v ? 'Oui' : 'Non';
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}
