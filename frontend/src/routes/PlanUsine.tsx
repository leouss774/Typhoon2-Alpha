// =============================================================================
//   TYPHOON — Niveau 2 : Plan d'usine (analyse VLM uniquement)
//   Le formulaire et l'affichage d'extraction ont ete supprimes.
//   L'enrichissement du score se fait automatiquement apres analyse.
// =============================================================================

import { useEffect, useState } from 'react';

export interface Equipement {
  id: string;
  nom: string;
  type: string;
  zone: string;
  valeur_remplacement_eur?: number;
  matieres_dangereuses?: boolean;
  critique_production?: boolean;
}

export interface ZonePlan {
  id: string;
  nom: string;
  type: string;
  surface_m2?: number;
}

export interface PlanUsine {
  nom_usine: string;
  equipements: Equipement[];
  zones: ZonePlan[];
}

export const TYPES_ZONE_LABELS: Record<string, string> = {
  production: 'Production',
  stockage: 'Stockage',
  bureaux: 'Bureaux',
  cuves: 'Cuves / reservoirs',
  expedition: 'Expedition',
};

export function PlanUsinePanel({
  onEnrichir,
  onClose,
}: {
  onEnrichir: (plan: PlanUsine) => void;
  onClose: () => void;
}) {
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [planImage, setPlanImage] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<{nom_usine?: string; zones: any[]; equipements: any[]} | null>(null);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileError(null);
    setAnalysisResult(null);

    try {
      if (file.type.startsWith('image/')) {
        await handleImageUpload(file);
      } else {
        const reader = new FileReader();
        reader.onload = (ev) => {
          try {
            const text = String(ev.target?.result || '');
            setFileContent(text);
            parseFile(file.name, text);
          } catch (err) {
            setFileError(`Impossible de lire le fichier : ${err}`);
          }
        };
        reader.onerror = () => setFileError('Erreur de lecture du fichier');
        reader.readAsText(file);
      }
    } catch (err) {
      setFileError(`Erreur inattendue : ${err}`);
    }
  }

  async function handleImageUpload(file: File) {
    setIsAnalyzing(true);
    setFileError(null);
    setAnalysisResult(null);

    try {
      const reader = new FileReader();
      reader.onload = (ev) => {
        setPlanImage(String(ev.target?.result || ''));
      };
      reader.readAsDataURL(file);

      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('/diagnostic/plan-usine/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.detail || error.detail || "Erreur lors de l'analyse");
      }

      const result = await response.json();
      setAnalysisResult({
        nom_usine: result.nom_usine,
        zones: result.zones || [],
        equipements: result.equipements || [],
      });
      setFileContent('? Plan analysé avec succès par IA Vision');

      // Enrichir automatiquement le score après analyse VLM
      const zones: ZonePlan[] = (result.zones || []).map((z: any, i: number) => ({
        id: z.id || `z_vision_${i}`,
        nom: z.nom || `Zone ${i + 1}`,
        type: z.type || 'production',
        surface_m2: z.surface_m2,
      }));
      const equipements: Equipement[] = (result.equipements || []).map((e: any, i: number) => ({
        id: e.id || `e_vision_${i}`,
        nom: e.nom || `Équipement ${i + 1}`,
        type: e.type || 'autre',
        zone: e.zone || (result.zones?.[0]?.nom || zones[0]?.id || 'z1'),
        valeur_remplacement_eur: e.valeur_remplacement_eur,
        matieres_dangereuses: !!e.matieres_dangereuses,
        critique_production: !!e.critique_production,
      }));

      onEnrichir({
        nom_usine: result.nom_usine || 'Mon usine',
        equipements,
        zones,
      });
    } catch (err) {
      setFileError(`Erreur d'analyse : ${err}`);
      setPlanImage(null);
    } finally {
      setIsAnalyzing(false);
    }
  }

  function parseFile(filename: string, content: string) {
    try {
      const lower = filename.toLowerCase();

      if (lower.endsWith('.geojson') || lower.endsWith('.json')) {
        const json = JSON.parse(content);
        let zones: ZonePlan[] = [];
        let equipements: Equipement[] = [];
        let nomUsine = '';

        if (json.type === 'FeatureCollection' && Array.isArray(json.features)) {
          zones = json.features.map((f: any, i: number) => ({
            id: `z_geo_${i}`,
            nom: f.properties?.nom || f.properties?.name || `Zone ${i + 1}`,
            type: f.properties?.type || 'production',
            surface_m2: f.properties?.surface_m2,
          }));
        } else {
          if (Array.isArray(json.zones)) zones = json.zones;
          if (Array.isArray(json.equipements)) equipements = json.equipements;
          if (json.nom_usine) nomUsine = json.nom_usine;
        }

        if (zones.length > 0 || equipements.length > 0) {
          setAnalysisResult({ nom_usine: nomUsine, zones, equipements });
          setFileContent('? Plan importé avec succès');

          onEnrichir({
            nom_usine: nomUsine || 'Mon usine',
            equipements,
            zones,
          });
        } else {
          setFileError('Aucune zone ou équipement détecté dans le fichier');
        }
        return;
      }

      setFileError('Format non reconnu. Formats supportés : GeoJSON (.geojson), JSON.');
    } catch (err) {
      setFileError(`Erreur d'analyse du fichier : ${err}`);
    }
  }

  // Fermer automatiquement le panneau après un enrichissement réussi
  useEffect(() => {
    if (analysisResult && !fileError && !isAnalyzing) {
      const timer = window.setTimeout(() => {
        onClose();
      }, 800);
      return () => window.clearTimeout(timer);
    }
  }, [analysisResult, fileError, isAnalyzing, onClose]);

  return (
    <div className="plan-usine-panel">
      <header className="plan-usine-header">
        <div>
          <h3>?? Analyse du plan d'usine</h3>
          <p className="plan-usine-subtitle">Importez un plan pour analyser automatiquement les zones et équipements</p>
        </div>
        <md-icon-button aria-label="Fermer" onClick={onClose}>
          <md-icon>close</md-icon>
        </md-icon-button>
      </header>

      <div className="plan-usine-import">
        <label className="plan-usine-dropzone">
          <md-icon>upload_file</md-icon>
          <span>
            <strong>Importer un plan</strong>
            <span className="plan-usine-dropzone-hint">Image (JPG, PNG) · JSON / GeoJSON</span>
          </span>
          <input
            type="file"
            accept="image/*,.json,.geojson"
            onChange={handleFileChange}
          />
        </label>
        {fileContent && <span className="plan-usine-file-ok">{fileContent}</span>}
        {fileError && <span className="plan-usine-file-error">? {fileError}</span>}
      </div>

      {planImage && (
        <div className="plan-usine-image-preview">
          <h4>?? Plan chargé</h4>
          <div className="plan-usine-image-container">
            <img src={planImage} alt="Plan d'usine" className="plan-usine-image" />
            {isAnalyzing && (
              <div className="plan-usine-analyzing-overlay">
                <div className="plan-usine-spinner"></div>
                <p>Analyse en cours par IA Vision...</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}