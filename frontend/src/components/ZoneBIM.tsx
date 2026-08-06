// =============================================================================
//   TYPHOON — /zone : étape 4 « Jumeau BIM » — visualisation 3D du bâtiment
//   Ouvre le viewer thingraph/bim-viewer (clone local, build statique servi
//   par Vite sous /bim-viewer/) dans une iframe, pointé sur le .glb généré
//   par le backend (GET /diagnostic/adresse/gltf — emprise BDNB extrudée).
//
//   Flux : report.adresse_saisie → modelUrl (backend 8765)
//          → iframe /bim-viewer/projects/remote?model=<url encodée>
//   Le viewer charge le projet synthétique « remote » via le query param
//   `model` (patch local du clone) — aucune dépendance à son API service.
// =============================================================================

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { RisqueReport } from '../zone/config';
import { API } from '../zone/config';

export function ZoneBIM({ report }: { report: RisqueReport | null }) {
  const [loaded, setLoaded] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const navigate = useNavigate();

  /* Nouveau diagnostic ou rechargement manuel → on réaffiche le voile de
     chargement le temps que l'iframe remonte. */
  useEffect(() => {
    setLoaded(false);
  }, [report?.adresse_saisie, attempt]);

  if (!report) {
    return (
      <div className="analyse-empty">
        <md-icon>view_in_ar</md-icon>
        <h2>Jumeau 3D indisponible</h2>
        <p>Diagnostiquez d'abord une adresse pour générer le modèle 3D du bâtiment.</p>
      </div>
    );
  }

  const batiment = report.bdnb?.batiment || null;
  // `_r` : cache-buster — l'endpoint répond Cache-Control max-age=3600, sans
  // lui le bouton « Recharger » resservirait le .glb du cache navigateur.
  const modelUrl = `${API}/diagnostic/adresse/gltf?q=${encodeURIComponent(
    report.adresse_saisie
  )}&_r=${attempt}`;
  const iframeSrc = `/bim-viewer/projects/remote?model=${encodeURIComponent(modelUrl)}`;
  const iframeKey = `${attempt}-${report.adresse_saisie}`;

  return (
    <div className="bim-wrap">
      <header className="bim-header">
        <div className="bim-title">
          <h2>Jumeau numérique 3D</h2>
          <p className="bim-meta">
            {report.adresse_normalisee} · modèle glTF généré depuis l'emprise
            BDNB (footprint → extrusion)
          </p>
        </div>
        <div className="bim-actions">
          <md-elevated-button
            className="bim-action"
            aria-label="Ouvrir le jumeau risques 3D pour cette adresse"
            onClick={() =>
              navigate(`/jumeau?adresse=${encodeURIComponent(report.adresse_saisie)}`)
            }
          >
            <md-icon slot="icon">warning</md-icon>
            Jumeau risques
          </md-elevated-button>
          <md-filled-button
            className="bim-action"
            aria-label="Recharger le modèle 3D"
            onClick={() => setAttempt((a) => a + 1)}
          >
            <md-icon slot="icon">refresh</md-icon>
            Recharger
          </md-filled-button>
          <md-elevated-button
            className="bim-action"
            aria-label="Ouvrir le modèle 3D en plein écran"
            href={iframeSrc}
            target="_blank"
            rel="noopener"
          >
            <md-icon slot="icon">open_in_new</md-icon>
            Plein écran
          </md-elevated-button>
        </div>
      </header>

      {batiment && (
        <div className="bim-chips">
          <Chip icon="height" value={fmt(batiment.hauteur_mean, ' m')} label="Hauteur" />
          <Chip icon="stairs" value={fmtNum(batiment.nb_niveau)} label="Niveaux" />
          <Chip
            icon="square_foot"
            value={fmtNum(batiment.surface_emprise_sol, 0) ? `${fmtNum(batiment.surface_emprise_sol, 0)} m²` : null}
            label="Emprise au sol"
          />
          <Chip icon="bricks" value={batiment.mat_mur_txt} label="Murs" />
          <Chip icon="roofing" value={batiment.mat_toit_txt} label="Toiture" />
          <Chip
            icon="door_front"
            value={fmtNum(batiment.nb_log) ? `${fmtNum(batiment.nb_log)}` : null}
            label="Logements"
          />
        </div>
      )}

      <div className="bim-frame-wrap">
        {!loaded && (
          <div className="bim-loading" role="status" aria-live="polite">
            <md-icon>view_in_ar</md-icon>
            <span>Chargement du jumeau 3D…</span>
            <md-linear-progress indeterminate />
          </div>
        )}
        <iframe
          key={iframeKey}
          className="bim-frame"
          src={iframeSrc}
          title="Jumeau numérique 3D du bâtiment — thingraph/bim-viewer"
          allow="webgl; xr-spatial-tracking"
          loading="eager"
          onLoad={() => setLoaded(true)}
        />
      </div>

      {!batiment && (
        <div className="bim-banner">
          <md-icon>info</md-icon>
          <span>
            Emprise BDNB indisponible pour cette adresse — affichage d'une
            géométrie générique (10 × 10 × 6 m). Essayez une adresse voisine
            pour un modèle fidèle.
          </span>
        </div>
      )}

      <p className="bim-footnote">
        Générateur glTF maison (footprint BDNB → extrusion, aucun GPU backend) · rendu{' '}
        <strong>thingraph/bim-viewer</strong> (three.js) en iframe · orbit,
        section, mesures dans le viewer — navigation clavier : A / D / W / S
      </p>
    </div>
  );
}

/* ─────────── Petits blocs réutilisables ─────────── */

function Chip({
  icon,
  value,
  label,
}: {
  icon: string;
  value: string | number | null | undefined;
  label: string;
}) {
  const str = value == null || value === '' ? null : String(value);
  return (
    <span className={`bim-chip${str == null ? ' na' : ''}`}>
      <md-icon>{icon}</md-icon>
      <span className="bim-chip-label">{label}</span>
      <span className="bim-chip-value">{str ?? 'non renseignée'}</span>
    </span>
  );
}

function fmtNum(v: number | null | undefined, digits = 0): string | null {
  if (v == null || Number.isNaN(v)) return null;
  return v.toLocaleString('fr-FR', { maximumFractionDigits: digits });
}

function fmt(v: number | null | undefined, suffix = ''): string | null {
  const n = fmtNum(v, 1);
  return n == null ? null : `${n}${suffix}`;
}
