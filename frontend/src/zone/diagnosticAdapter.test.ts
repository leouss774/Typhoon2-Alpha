import { describe, expect, it } from 'vitest';
import { adaptDiagnosticContract } from './diagnosticAdapter';

describe('adaptDiagnosticContract', () => {
  it('maps new backend geometry and zones into the house-renderer contract', () => {
    const adapted = adaptDiagnosticContract({
      adresse_saisie: '26 Rue Victor Hugo, 37140 Bourgueil',
      adresse_normalisee: '26 Rue Victor Hugo, 37140 Bourgueil',
      geometry: {
        largeur_m: 6.57,
        longueur_m: 19.21,
        floors_count: 2,
        roof_shape: 'deux_pans',
      },
      zones: {
        toiture: {
          risque: 18,
          niveau: 'tres_faible',
          alea_principal: 'Feu de forêt / vent',
        },
      },
      score_global: 42,
      projection_2050: {
        score_global: 55,
        zones: {
          toiture: {
            risque: 24,
            niveau: 'faible',
            alea_principal: 'Feu de forêt / vent',
          },
        },
      },
    });

    expect(adapted.adresse).toBe('26 Rue Victor Hugo, 37140 Bourgueil');
    expect(adapted.geometry.largeur_m).toBe(6.57);
    expect(adapted.geometry.longueur_m).toBe(19.21);
    expect(adapted.zones.toiture.risque).toBe(18);
    expect(adapted.projection_2050.zones.toiture.niveau).toBe('faible');
    expect(adapted.score_global).toBe(42);
  });

  it('derives score_global from zone averages when the backend returns 0', () => {
    const zones = Object.fromEntries(
      ['fondations', 'murs_nord', 'murs_sud', 'murs_est', 'murs_ouest', 'toiture', 'sous_sol'].map(
        (z) => [z, { risque: 20 }]
      )
    );
    const projectionZones = Object.fromEntries(
      ['fondations', 'murs_nord', 'murs_sud', 'murs_est', 'murs_ouest', 'toiture', 'sous_sol'].map(
        (z) => [z, { risque: 40 }]
      )
    );
    const adapted = adaptDiagnosticContract({
      zones,
      projection_2050: { score_global: 0, zones: projectionZones },
      score_global: 0, // route /diagnostic/adresse : score non calculé (0 codé en dur)
    });
    expect(adapted.score_global).toBe(20);
    expect(adapted.projection_2050.score_global).toBe(40);
  });
});
