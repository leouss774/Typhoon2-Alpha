// =============================================================================
//   TYPHOON — /usine : étape 1 « Plan » — import d'un plan d'usine
//   Dropzone Material 3 : image (JPG/PNG → Mistral Vision) ou JSON/GeoJSON
//   (parsing direct). Aperçu du plan + résumé des zones/équipements détectés.
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import type { DragEvent } from 'react';
import { analyzePlanFile, demoPlan } from '../usine/api';
import { TYPE_EQUIP_LABELS, TYPE_ZONE_LABELS, type PlanUsine } from '../usine/types';

type Props = {
  initialImage?: string | null;
  onReady: (plan: PlanUsine, planImage: string | null) => void;
  onUseDemo: (plan: PlanUsine) => void;
};

export function UsinePlanImport({ initialImage, onReady, onUseDemo }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [planImage, setPlanImage] = useState<string | null>(initialImage || null);
  const [lastFile, setLastFile] = useState<string | null>(null);

  useEffect(() => {
    setPlanImage(initialImage || null);
  }, [initialImage]);

  async function readAsDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
  }

  async function handleFile(file: File) {
    setError(null);
    setLoading(true);
    setLastFile(file.name);

    const isImage = file.type.startsWith('image/');
    const dataUrl = isImage ? await readAsDataUrl(file).catch(() => null) : null;
    if (dataUrl) setPlanImage(dataUrl);
    else setPlanImage(null);

    try {
      const plan = await analyzePlanFile(file);
      if (plan.zones.length === 0 && plan.equipements.length === 0) {
        setError('Aucune zone ni équipement détecté dans ce plan.');
        setLoading(false);
        return;
      }
      onReady(plan, dataUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleFile(file);
  }

  function onInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
    e.target.value = '';
  }

  return (
    <div className="usine-import">
      <div
        id="usine-dropzone"
        className={`usine-dropzone${dragOver ? ' dragover' : ''}${loading ? ' loading' : ''}`}
        role="button"
        tabIndex={0}
        aria-label="Importer un plan d'usine (image, JSON ou GeoJSON)"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          accept="image/*,.json,.geojson"
          onChange={onInputChange}
          tabIndex={-1}
          aria-hidden="true"
        />
        <span className="usine-dropzone-icon" aria-hidden="true">
          <md-icon>{loading ? 'progress_activity' : 'upload_file'}</md-icon>
        </span>
        <span className="usine-dropzone-title">
          {loading ? 'Analyse du plan en cours…' : 'Importer un plan d’usine'}
        </span>
        <span className="usine-dropzone-hint">
          Image (JPG, PNG) analysée par IA Vision · JSON / GeoJSON parsé directement
        </span>
        <span className="usine-dropzone-formats">DXF · PLANS · 3D · PDF</span>
        <md-linear-progress indeterminate className={loading ? 'visible' : 'hidden'} />
      </div>

      {lastFile && !loading && (
        <div className="usine-file-ok">
          <md-icon>check_circle</md-icon>
          <span>
            <strong>{lastFile}</strong> importé — zones et équipements détectés ci-dessous.
          </span>
        </div>
      )}
      {error && (
        <div className="usine-file-error" role="alert">
          <md-icon>error</md-icon>
          <span>{error}</span>
        </div>
      )}

      {planImage && (
        <div className="usine-plan-preview">
          <h4>
            <md-icon>image</md-icon> Plan chargé
          </h4>
          <div className="usine-plan-preview-img">
            <img src={planImage} alt="Plan d'usine importé" />
          </div>
        </div>
      )}

      <div className="usine-import-alt">
        <span className="usine-import-alt-sep">ou</span>
        <md-outlined-button
          onClick={() => onUseDemo(demoPlan())}
          aria-label="Essayer avec une usine de démonstration"
        >
          <md-icon slot="icon">auto_awesome</md-icon>
          Essayer avec une usine de démonstration
        </md-outlined-button>
      </div>
    </div>
  );
}
