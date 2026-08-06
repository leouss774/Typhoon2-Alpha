// =============================================================================
//   TYPHOON — Niveau 2 : Plan d'usine (import équipements + zones)
//   Permet d'enrichir le score de risque niveau 1 avec le plan réel de l'usine.
//   Le plan est OPTIONNEL : sans plan, le score niveau 1 reste valide.
// =============================================================================

import { useMemo, useState } from 'react';

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

const TYPES_EQUIPEMENT = [
  'machine_outil',
  'ligne_production',
  'four',
  'compresseur',
  'groupe_froid',
  'pompe',
  'chaudiere',
  'reservoir',
  'cuve',
  'silo',
  'pont_roulant',
  'robot',
  'automate',
  'serveur',
  'laboratoire',
  'autre',
];

const TYPES_ZONE = ['production', 'stockage', 'bureaux', 'cuves', 'expedition'];

const TYPES_EQUIPEMENT_LABELS: Record<string, string> = {
  machine_outil: 'Machine-outil',
  ligne_production: 'Ligne de production',
  four: 'Four',
  compresseur: 'Compresseur',
  groupe_froid: 'Groupe froid',
  pompe: 'Pompe',
  chaudiere: 'Chaudière',
  reservoir: 'Réservoir',
  cuve: 'Cuve',
  silo: 'Silo',
  pont_roulant: 'Pont roulant',
  robot: 'Robot',
  automate: 'Automate',
  serveur: 'Serveur',
  laboratoire: 'Laboratoire',
  autre: 'Autre',
};

export const TYPES_ZONE_LABELS: Record<string, string> = {
  production: 'Production',
  stockage: 'Stockage',
  bureaux: 'Bureaux',
  cuves: 'Cuves / réservoirs',
  expedition: 'Expédition',
};

export function PlanUsinePanel({
  onEnrichir,
  onClose,
}: {
  onEnrichir: (plan: PlanUsine) => void;
  onClose: () => void;
}) {
  const [nomUsine, setNomUsine] = useState('');
  const [zones, setZones] = useState<ZonePlan[]>([
    { id: 'z1', nom: 'Zone de production', type: 'production', surface_m2: 2000 },
    { id: 'z2', nom: 'Zone de stockage', type: 'stockage', surface_m2: 1500 },
  ]);
  const [equipements, setEquipements] = useState<Equipement[]>([
    { id: 'e1', nom: 'Ligne d\'assemblage 1', type: 'ligne_production', zone: 'z1', valeur_remplacement_eur: 800000, critique_production: true },
    { id: 'e2', nom: 'Machine CNC', type: 'machine_outil', zone: 'z1', valeur_remplacement_eur: 250000 },
  ]);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [planImage, setPlanImage] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<{zones: any[], equipements: any[]} | null>(null);

  function addZone() {
    const id = `z${zones.length + 1}`;
    setZones([...zones, { id, nom: `Zone ${zones.length + 1}`, type: 'production' }]);
  }

  function removeZone(id: string) {
    setZones(zones.filter((z) => z.id !== id));
  }

  function updateZone(id: string, field: keyof ZonePlan, value: string | number) {
    setZones(zones.map((z) => (z.id === id ? { ...z, [field]: value } : z)));
  }

  function addEquipement() {
    const id = `e${equipements.length + 1}`;
    const zoneId = zones[0]?.id || 'z1';
    setEquipements([
      ...equipements,
      { id, nom: `Équipement ${equipements.length + 1}`, type: 'autre', zone: zoneId },
    ]);
  }

  function removeEquipement(id: string) {
    setEquipements(equipements.filter((e) => e.id !== id));
  }

  function updateEquipement(id: string, field: keyof Equipement, value: unknown) {
    setEquipements(equipements.map((e) => (e.id === id ? { ...e, [field]: value } : e)));
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFileError(null);
    
    // Vérifier si c'est une image
    if (file.type.startsWith('image/')) {
      await handleImageUpload(file);
    } else {
      // Traiter les fichiers texte (JSON, CSV, DXF)
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
  }

  async function handleImageUpload(file: File) {
    setIsAnalyzing(true);
    setAnalysisResult(null);
    setFileError(null);

    try {
      // Afficher l'image en preview
      const reader = new FileReader();
      reader.onload = (ev) => {
        setPlanImage(String(ev.target?.result || ''));
      };
      reader.readAsDataURL(file);

      // Analyser l'image avec l'API backend
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('http://127.0.0.1:8765/diagnostic/plan-usine/analyze', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail?.detail || error.detail || 'Erreur lors de l\'analyse');
      }

      const result = await response.json();
      setAnalysisResult({
        zones: result.zones || [],
        equipements: result.equipements || []
      });

      // Mettre à jour les zones et équipements avec les résultats détectés
      if (result.zones && result.zones.length > 0) {
        const detectedZones = result.zones.map((z: any, i: number) => ({
          id: z.id || `z_vision_${i}`,
          nom: z.nom || `Zone ${i + 1}`,
          type: z.type || 'production',
          surface_m2: z.surface_m2,
        }));
        setZones(detectedZones);
      }

      if (result.equipements && result.equipements.length > 0) {
        const detectedEquipements = result.equipements.map((e: any, i: number) => ({
          id: e.id || `e_vision_${i}`,
          nom: e.nom || `Équipement ${i + 1}`,
          type: e.type || 'autre',
          zone: e.zone || (result.zones?.[0]?.nom || 'Zone 1'),
          valeur_remplacement_eur: e.valeur_remplacement_eur,
          matieres_dangereuses: e.matieres_dangereuses || false,
          critique_production: e.critique_production || false,
        }));
        setEquipements(detectedEquipements);
      }

      if (result.nom_usine) {
        setNomUsine(result.nom_usine);
      }

      setFileContent('✓ Plan analysé avec succès par IA Vision');
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
        // GeoJSON FeatureCollection : on extrait les features comme zones
        if (json.type === 'FeatureCollection' && Array.isArray(json.features)) {
          const parsedZones: ZonePlan[] = json.features.map((f: any, i: number) => ({
            id: `z_geo_${i}`,
            nom: f.properties?.nom || f.properties?.name || `Zone ${i + 1}`,
            type: f.properties?.type || 'production',
            surface_m2: f.properties?.surface_m2,
          }));
          if (parsedZones.length > 0) {
            setZones(parsedZones);
            setFileError(null);
            return;
          }
        }
        // JSON simple : zones + équipements
        if (json.zones) {
          setZones(json.zones);
        }
        if (json.equipements) {
          setEquipements(json.equipements);
        }
        if (json.nom_usine) {
          setNomUsine(json.nom_usine);
        }
        setFileError(null);
        return;
      }

      if (lower.endsWith('.csv')) {
        const lines = content.trim().split('\n');
        if (lines.length > 1) {
          const headers = lines[0].split(';').map((h) => h.trim().toLowerCase());
          const zonesParsed: ZonePlan[] = [];
          const equipementsParsed: Equipement[] = [];

          for (let i = 1; i < lines.length; i++) {
            const cols = lines[i].split(';').map((c) => c.trim());
            const row: Record<string, string> = {};
            headers.forEach((h, idx) => (row[h] = cols[idx] || ''));
            if (row.type === 'zone' || row.categorie === 'zone') {
              zonesParsed.push({
                id: row.id || `z_csv_${i}`,
                nom: row.nom || `Zone ${i}`,
                type: row.sous_type || 'production',
                surface_m2: row.surface_m2 ? Number(row.surface_m2) : undefined,
              });
            } else if (row.type === 'equipement' || row.categorie === 'equipement') {
              equipementsParsed.push({
                id: row.id || `e_csv_${i}`,
                nom: row.nom || `Équipement ${i}`,
                type: row.sous_type || 'autre',
                zone: row.zone || 'z1',
                valeur_remplacement_eur: row.valeur_remplacement_eur ? Number(row.valeur_remplacement_eur) : undefined,
                matieres_dangereuses: row.matieres_dangereuses === 'true' || row.matieres_dangereuses === 'oui',
                critique_production: row.critique_production === 'true' || row.critique_production === 'oui',
              });
            }
          }
          if (zonesParsed.length > 0) setZones(zonesParsed);
          if (equipementsParsed.length > 0) setEquipements(equipementsParsed);
          setFileError(null);
          return;
        }
      }

      // DXF : on extrait les entités TEXT pour deviner les zones
      if (lower.endsWith('.dxf')) {
        const textMatches = content.match(/TEXT[\s\S]*?Text:([^\\n]+)/g) || [];
        if (textMatches.length > 0) {
          const parsedZones = textMatches
            .map((m, i) => {
              const label = m.replace(/TEXT[\s\S]*?Text:/, '').trim();
              return label
                ? { id: `z_dxf_${i}`, nom: label, type: 'production' }
                : null;
            })
            .filter(Boolean) as ZonePlan[];
          if (parsedZones.length > 0) {
            setZones(parsedZones);
            setFileError(null);
            return;
          }
        }
      }

      setFileError('Format non reconnu. Formats supportés : GeoJSON (.geojson), JSON, CSV (.csv), DXF (.dxf).');
    } catch (err) {
      setFileError(`Erreur d'analyse du fichier : ${err}`);
    }
  }

  function handleSubmit() {
    onEnrichir({
      nom_usine: nomUsine.trim() || 'Mon usine',
      equipements,
      zones,
    });
  }

  const totalValeurs = useMemo(
    () => equipements.reduce((sum, e) => sum + (e.valeur_remplacement_eur || 0), 0),
    [equipements]
  );

  return (
    <div className="plan-usine-panel">
      <header className="plan-usine-header">
        <div>
          <h3>📐 Plan de l'usine (niveau 2)</h3>
          <p className="plan-usine-subtitle">Enrichissez le score avec les équipements et zones réels</p>
        </div>
        <md-icon-button aria-label="Fermer" onClick={onClose}>
          <md-icon>close</md-icon>
        </md-icon-button>
      </header>

      {/* Nom usine */}
      <div className="plan-usine-field">
        <label>Nom de l'usine</label>
        <md-outlined-text-field
          value={nomUsine}
          placeholder="Ex. Usine de production Sud"
          onChange={(e: any) => setNomUsine(e.target.value)}
        />
      </div>

      {/* Import fichier */}
      <div className="plan-usine-import">
        <label className="plan-usine-dropzone">
          <md-icon>upload_file</md-icon>
          <span>
            <strong>Importer un plan (optionnel)</strong>
            <span className="plan-usine-dropzone-hint">Images (JPG, PNG) · GeoJSON · JSON · CSV · DXF</span>
          </span>
          <input 
            type="file" 
            accept="image/*,.geojson,.json,.csv,.dxf" 
            onChange={handleFileChange}
          />
        </label>
        {fileContent && <span className="plan-usine-file-ok">{fileContent}</span>}
        {fileError && <span className="plan-usine-file-error">⚠ {fileError}</span>}
      </div>

      {/* Preview de l'image et résultats de détection */}
      {planImage && (
        <div className="plan-usine-image-preview">
          <h4>📷 Plan chargé</h4>
          <div className="plan-usine-image-container">
            <img src={planImage} alt="Plan d'usine" className="plan-usine-image" />
            {isAnalyzing && (
              <div className="plan-usine-analyzing-overlay">
                <div className="plan-usine-spinner"></div>
                <p>Analyse en cours par IA Vision...</p>
              </div>
            )}
          </div>
          {analysisResult && (
            <div className="plan-usine-detection-summary">
              <h4>✅ Détection automatique</h4>
              <p>
                <strong>{analysisResult.zones.length} zone(s)</strong> et 
                <strong> {analysisResult.equipements.length} équipement(s)</strong> détectés
              </p>
            </div>
          )}
        </div>
      )}

      {/* Zones */}
      <div className="plan-usine-section">
        <div className="plan-usine-section-header">
          <h4>🏭 Zones de l'usine</h4>
          <md-text-button onClick={addZone}>
            <md-icon slot="icon">add</md-icon> Ajouter
          </md-text-button>
        </div>
        <div className="plan-usine-zones">
          {zones.map((z) => (
            <div className="plan-usine-zone-row" key={z.id}>
              <md-outlined-text-field
                label="Nom"
                value={z.nom}
                onChange={(e: any) => updateZone(z.id, 'nom', e.target.value)}
              />
              <md-outlined-select
                label="Type"
                value={z.type}
                onChange={(e: any) => updateZone(z.id, 'type', e.target.value)}
              >
                {TYPES_ZONE.map((t) => (
                  <md-select-option key={t} value={t}>
                    {TYPES_ZONE_LABELS[t]}
                  </md-select-option>
                ))}
              </md-outlined-select>
              <md-outlined-text-field
                label="Surface m²"
                type="number"
                value={String(z.surface_m2 ?? '')}
                onChange={(e: any) => updateZone(z.id, 'surface_m2', Number(e.target.value))}
              />
              <md-icon-button aria-label="Supprimer" onClick={() => removeZone(z.id)}>
                <md-icon>delete</md-icon>
              </md-icon-button>
            </div>
          ))}
        </div>
      </div>

      {/* Équipements */}
      <div className="plan-usine-section">
        <div className="plan-usine-section-header">
          <h4>⚙️ Équipements critiques</h4>
          <md-text-button onClick={addEquipement}>
            <md-icon slot="icon">add</md-icon> Ajouter
          </md-text-button>
        </div>
        <div className="plan-usine-equipements">
          {equipements.map((e) => (
            <div className="plan-usine-equip-row" key={e.id}>
              <md-outlined-text-field
                label="Nom"
                value={e.nom}
                onChange={(ev: any) => updateEquipement(e.id, 'nom', ev.target.value)}
              />
              <md-outlined-select
                label="Type"
                value={e.type}
                onChange={(ev: any) => updateEquipement(e.id, 'type', ev.target.value)}
              >
                {TYPES_EQUIPEMENT.map((t) => (
                  <md-select-option key={t} value={t}>
                    {TYPES_EQUIPEMENT_LABELS[t]}
                  </md-select-option>
                ))}
              </md-outlined-select>
              <md-outlined-select
                label="Zone"
                value={e.zone}
                onChange={(ev: any) => updateEquipement(e.id, 'zone', ev.target.value)}
              >
                {zones.map((z) => (
                  <md-select-option key={z.id} value={z.id}>
                    {z.nom}
                  </md-select-option>
                ))}
              </md-outlined-select>
              <md-outlined-text-field
                label="Valeur remplacement (€)"
                type="number"
                value={String(e.valeur_remplacement_eur ?? '')}
                onChange={(ev: any) => updateEquipement(e.id, 'valeur_remplacement_eur', Number(ev.target.value))}
              />
              <div className="plan-usine-checks">
                <label>
                  <md-checkbox
                    checked={!!e.matieres_dangereuses}
                    onChange={(ev: any) => updateEquipement(e.id, 'matieres_dangereuses', ev.target.checked)}
                  />
                  Matières dangereuses
                </label>
                <label>
                  <md-checkbox
                    checked={!!e.critique_production}
                    onChange={(ev: any) => updateEquipement(e.id, 'critique_production', ev.target.checked)}
                  />
                  Critique production
                </label>
              </div>
              <md-icon-button aria-label="Supprimer" onClick={() => removeEquipement(e.id)}>
                <md-icon>delete</md-icon>
              </md-icon-button>
            </div>
          ))}
        </div>
        {equipements.length > 0 && (
          <div className="plan-usine-total">
            <strong>Valeur totale des équipements :</strong>{' '}
            {new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(totalValeurs)}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="plan-usine-actions">
        <md-text-button onClick={onClose}>Annuler</md-text-button>
        <md-filled-button onClick={handleSubmit}>
          <md-icon slot="icon">analytics</md-icon>
          Enrichir le score
        </md-filled-button>
      </div>
    </div>
  );
}