// =============================================================================
//   TYPHOON — /usine : étape 2 « Zones & équipements » — revue et édition du
//   plan détecté avant le calcul de risque. Listes éditables (nom, type,
//   surface, valeur, attributs métiers).
// =============================================================================

import { useMemo, useState } from 'react';
import {
  EQUIP_TYPES,
  TYPE_EQUIP_LABELS,
  TYPE_ZONE_LABELS,
  ZONE_TYPES,
  type Equipement,
  type PlanUsine,
  type ZonePlan,
} from '../usine/types';

type Props = {
  plan: PlanUsine;
  onChange: (plan: PlanUsine) => void;
};

export function UsineZones({ plan, onChange }: Props) {
  const [tab, setTab] = useState<'zones' | 'equipements'>('zones');

  const stats = useMemo(() => {
    const totalSurface = plan.zones.reduce(
      (acc, z) => acc + (typeof z.surface_m2 === 'number' ? z.surface_m2 : 0),
      0
    );
    const dangereux = plan.equipements.filter((e) => e.matieres_dangereuses).length;
    const critiques = plan.equipements.filter((e) => e.critique_production).length;
    return { totalSurface, dangereux, critiques };
  }, [plan]);

  function updateZone(index: number, patch: Partial<ZonePlan>) {
    const zones = plan.zones.map((z, i) => (i === index ? { ...z, ...patch } : z));
    onChange({ ...plan, zones });
  }

  function updateEquip(index: number, patch: Partial<Equipement>) {
    const equipements = plan.equipements.map((e, i) => (i === index ? { ...e, ...patch } : e));
    onChange({ ...plan, equipements });
  }

  function removeEquip(index: number) {
    onChange({ ...plan, equipements: plan.equipements.filter((_, i) => i !== index) });
  }

  function addEquip() {
    const zone = plan.zones[0]?.nom || '';
    onChange({
      ...plan,
      equipements: [
        ...plan.equipements,
        {
          id: `e_${Date.now()}`,
          nom: `Équipement ${plan.equipements.length + 1}`,
          type: 'autre',
          zone,
          valeur_remplacement_eur: 0,
          matieres_dangereuses: false,
          critique_production: false,
        },
      ],
    });
  }

  const zonesForEquip = plan.zones.map((z) => z.nom).filter(Boolean);

  return (
    <div className="usine-zones-wrap">
      <header className="usine-zones-header">
        <div className="usine-zones-title">
          <h2>{plan.nom_usine}</h2>
          <p className="usine-zones-meta">
            {plan.zones.length} zone(s) · {plan.equipements.length} équipement(s) ·{' '}
            {stats.totalSurface.toLocaleString('fr-FR')} m²
          </p>
        </div>
        <div className="usine-zones-summary">
          <span className="usine-kpi">
            <md-icon>factory</md-icon> {plan.zones.length} zones
          </span>
          <span className="usine-kpi">
            <md-icon>precision_manufacturing</md-icon> {plan.equipements.length} équipements
          </span>
          <span className="usine-kpi warn" title="Équipements à matières dangereuses">
            <md-icon>warning</md-icon> {stats.dangereux} dangereux
          </span>
          <span className="usine-kpi accent" title="Équipements critiques pour la production">
            <md-icon>priority_high</md-icon> {stats.critiques} critiques
          </span>
        </div>
      </header>

      <div className="usine-edit-tabs" role="tablist" aria-label="Éditer les zones ou les équipements">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'zones'}
          className={`usine-edit-tab${tab === 'zones' ? ' active' : ''}`}
          onClick={() => setTab('zones')}
        >
          <md-icon>maps_home_work</md-icon>
          <span>Zones ({plan.zones.length})</span>
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'equipements'}
          className={`usine-edit-tab${tab === 'equipements' ? ' active' : ''}`}
          onClick={() => setTab('equipements')}
        >
          <md-icon>precision_manufacturing</md-icon>
          <span>Équipements ({plan.equipements.length})</span>
        </button>
      </div>

      {tab === 'zones' ? (
        <section className="usine-edit-list" aria-label="Zones du plan">
          <div className="usine-edit-grid usine-edit-grid-zones">
            {plan.zones.map((zone, i) => (
              <div className="usine-edit-row" key={zone.id}>
                <input
                  className="usine-field usine-field-text"
                  value={zone.nom}
                  aria-label={`Nom de la zone ${i + 1}`}
                  onChange={(e) => updateZone(i, { nom: e.target.value })}
                />
                <select
                  className="usine-field usine-field-select"
                  value={zone.type}
                  aria-label={`Type de la zone ${zone.nom}`}
                  onChange={(e) => updateZone(i, { type: e.target.value })}
                >
                  {ZONE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {TYPE_ZONE_LABELS[t]}
                    </option>
                  ))}
                </select>
                <input
                  className="usine-field usine-field-number"
                  type="number"
                  min={0}
                  step={10}
                  placeholder="Surface m²"
                  value={zone.surface_m2 ?? ''}
                  aria-label={`Surface de ${zone.nom}`}
                  onChange={(e) =>
                    updateZone(i, {
                      surface_m2: e.target.value === '' ? undefined : Number(e.target.value),
                    })
                  }
                />
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="usine-edit-list" aria-label="Équipements du plan">
          <div className="usine-edit-grid usine-edit-grid-equip">
            {plan.equipements.map((eq, i) => (
              <div className="usine-edit-row usine-edit-row-equip" key={eq.id}>
                <input
                  className="usine-field usine-field-text"
                  value={eq.nom}
                  aria-label={`Nom de l'équipement ${i + 1}`}
                  onChange={(e) => updateEquip(i, { nom: e.target.value })}
                />
                <select
                  className="usine-field usine-field-select"
                  value={eq.type}
                  aria-label={`Type de ${eq.nom}`}
                  onChange={(e) => updateEquip(i, { type: e.target.value })}
                >
                  {EQUIP_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {TYPE_EQUIP_LABELS[t]}
                    </option>
                  ))}
                </select>
                <select
                  className="usine-field usine-field-select"
                  value={eq.zone || ''}
                  aria-label={`Zone d'accueil de ${eq.nom}`}
                  onChange={(e) => updateEquip(i, { zone: e.target.value })}
                >
                  <option value="" disabled>
                    Zone d'accueil
                  </option>
                  {zonesForEquip.map((zn) => (
                    <option key={zn} value={zn}>
                      {zn}
                    </option>
                  ))}
                </select>
                <input
                  className="usine-field usine-field-number"
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="Valeur €"
                  value={eq.valeur_remplacement_eur ?? ''}
                  aria-label={`Valeur de remplacement de ${eq.nom}`}
                  onChange={(e) =>
                    updateEquip(i, {
                      valeur_remplacement_eur:
                        e.target.value === '' ? undefined : Number(e.target.value),
                    })
                  }
                />
                <div className="usine-check">
                  <label>
                    <input
                      type="checkbox"
                      checked={!!eq.matieres_dangereuses}
                      onChange={(e) => updateEquip(i, { matieres_dangereuses: e.target.checked })}
                    />
                    <span>Dangereux</span>
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={!!eq.critique_production}
                      onChange={(e) => updateEquip(i, { critique_production: e.target.checked })}
                    />
                    <span>Critique</span>
                  </label>
                </div>
                <button
                  type="button"
                  className="usine-edit-remove"
                  aria-label={`Supprimer ${eq.nom}`}
                  title="Supprimer"
                  onClick={() => removeEquip(i)}
                >
                  <md-icon>close</md-icon>
                </button>
              </div>
            ))}
          </div>
          <md-outlined-button className="usine-add-equip" onClick={addEquip}>
            <md-icon slot="icon">add</md-icon>
            Ajouter un équipement
          </md-outlined-button>
        </section>
      )}
    </div>
  );
}
