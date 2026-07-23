import os

content = '''import { useState } from "react";

interface FormData {
  adresse: string;
  code_insee: string;
  type_bien: string;
  surface: number;
  nb_etages: number;
  annee_construction: number;
  annee_renovation: number;
  type_structure: string;
  etat_structure: string;
  fissures: string;
  affaissement: string;
  type_toiture: string;
  age_toiture: number;
  etat_toiture: string;
  infiltrations: string;
  presence_sous_sol: boolean;
  presence_cave: boolean;
  occupation: string;
  installation_electrique_annee: number;
  isolation_toiture: string;
  isolation_murs: string;
}

const defaultForm: FormData = {
  adresse: "", code_insee: "", type_bien: "Maison individuelle", surface: 100,
  nb_etages: 1, annee_construction: 2000, annee_renovation: 0,
  type_structure: "Beton arme", etat_structure: "Bon", fissures: "Non",
  affaissement: "Non", type_toiture: "Tuiles", age_toiture: 2000,
  etat_toiture: "Moyen", infiltrations: "Non", presence_sous_sol: false,
  presence_cave: false, occupation: "Occupe", installation_electrique_annee: 2000,
  isolation_toiture: "moyenne", isolation_murs: "moyenne",
};

interface ClientFormProps {
  onAnalyseLancee?: (sessionId: string) => void;
}

const STYLE = {
  page: { maxWidth: 800, margin: "0 auto", padding: "24px", color: "#e8f4ff" },
  title: { fontSize: 22, fontWeight: 700, color: "#4da6ff", marginBottom: 6 },
  subtitle: { fontSize: 14, color: "#7fb4e8", marginBottom: 24 },
  section: {
    background: "rgba(6,14,26,0.8)", border: "1px solid #1c5a9c",
    borderRadius: 10, padding: 20, marginBottom: 20,
    boxShadow: "0 0 20px rgba(30,130,255,0.08)",
  } as const,
  sectionTitle: { fontSize: 13, fontWeight: 600, color: "#4da6ff", textTransform: "uppercase" as const, letterSpacing: "0.08em", marginBottom: 16, marginTop: 0 },
  row: { display: "flex", gap: 16, marginBottom: 14, flexWrap: "wrap" as const },
  field: { flex: "1 1 200px", minWidth: 200 },
  label: { display: "block", fontSize: 12, color: "#9fc4e8", marginBottom: 4, fontWeight: 500 },
  input: {
    width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #1c5a9c",
    background: "rgba(10,20,40,0.8)", color: "#e8f4ff", fontSize: 14,
    outline: "none", boxSizing: "border-box" as const,
    transition: "border-color 0.15s",
  },
  select: {
    width: "100%", padding: "8px 12px", borderRadius: 6, border: "1px solid #1c5a9c",
    background: "rgba(10,20,40,0.8)", color: "#e8f4ff", fontSize: 14,
    outline: "none", boxSizing: "border-box" as const, cursor: "pointer",
  },
  checkbox: { width: 18, height: 18, accentColor: "#4da6ff", cursor: "pointer" },
  checkboxLabel: { fontSize: 14, color: "#cfe8ff", cursor: "pointer" },
  actions: { display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 24 },
  btnPrimary: {
    padding: "12px 32px", borderRadius: 8, border: "none",
    background: "#4da6ff", color: "#04070c", fontSize: 15, fontWeight: 700,
    cursor: "pointer", transition: "all 0.15s",
  },
  btnSecondary: {
    padding: "12px 32px", borderRadius: 8, border: "1px solid #1c5a9c",
    background: "transparent", color: "#cfe8ff", fontSize: 15,
    cursor: "pointer", transition: "all 0.15s",
  },
};

const typesBien = ["Maison individuelle", "Appartement", "Immeuble", "Commerce", "Autre"];
const typesStructure = ["Beton arme", "Bois", "Acier", "Parpaing", "Pierre", "Brique", "Autre"];
const etats = ["Bon", "Moyen", "Mauvais"];
const fissuresOpts = ["Non", "Legeres", "Moyennes", "Importantes"];
const toitures = ["Tuiles", "Ardoises", "Zinc", "Bac acier", "Toit plat", "Autre"];
const occupations = ["Occupe", "Vacant", "Loue"];
const isolationNiveaux = ["faible", "moyenne", "bonne"];

function Input({ label, val, set, type = "text", min, max }: {
  label: string; val: string | number; set: (v: any) => void;
  type?: string; min?: number; max?: number;
}) {
  return (
    <div style={STYLE.field}>
      <label style={STYLE.label}>{label}</label>
      <input
        style={STYLE.input}
        type={type}
        value={val}
        min={min}
        max={max}
        onChange={e => set(type === "number" ? Number(e.target.value) : e.target.value)}
        onFocus={e => { e.target.style.borderColor = "#4da6ff"; }}
        onBlur={e => { e.target.style.borderColor = "#1c5a9c"; }}
      />
    </div>
  );
}

function Select({ label, val, set, options }: {
  label: string; val: string; set: (v: string) => void; options: string[];
}) {
  return (
    <div style={STYLE.field}>
      <label style={STYLE.label}>{label}</label>
      <select
        style={STYLE.select}
        value={val}
        onChange={e => set(e.target.value)}
        onFocus={e => { e.target.style.borderColor = "#4da6ff"; }}
        onBlur={e => { e.target.style.borderColor = "#1c5a9c"; }}
      >
        {options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

function Checkbox({ label, val, set }: {
  label: string; val: boolean; set: (v: boolean) => void;
}) {
  return (
    <label style={{ ...STYLE.field, display: "flex", alignItems: "center", gap: 8 }}>
      <input type="checkbox" checked={val} onChange={e => set(e.target.checked)} style={STYLE.checkbox} />
      <span style={STYLE.checkboxLabel}>{label}</span>
    </label>
  );
}

export default function ClientForm({ onAnalyseLancee }: ClientFormProps) {
  const [form, setForm] = useState<FormData>(defaultForm);
  const [submitting, setSubmitting] = useState(false);

  const update = <K extends keyof FormData>(key: K, val: FormData[K]) =>
    setForm(prev => ({ ...prev, [key]: val }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const sessionId = "session-" + Date.now();
      const payload = {
        session_id: sessionId,
        client_form: form,
        raw_data: {},
      };
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error("Erreur API");
      if (onAnalyseLancee) onAnalyseLancee(sessionId);
    } catch (err) {
      alert("Erreur lors du lancement de l'analyse : " + (err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={STYLE.page}>
      <h2 style={STYLE.title}>Nouvelle analyse de resilience</h2>
      <p style={STYLE.subtitle}>
        Renseignez les caracteristiques du bien pour lancer le diagnostic multi-agents
      </p>

      {/* LOCALISATION */}
      <div style={STYLE.section}>
        <h3 style={STYLE.sectionTitle}>Localisation</h3>
        <div style={STYLE.row}>
          <Input label="Adresse" val={form.adresse} set={v => update("adresse", v)} />
          <Input label="Code INSEE" val={form.code_insee} set={v => update("code_insee", v)} />
        </div>
      </div>

      {/* CARACTERISTIQUES GENERALES */}
      <div style={STYLE.section}>
        <h3 style={STYLE.sectionTitle}>Caracteristiques generales</h3>
        <div style={STYLE.row}>
          <Select label="Type de bien" val={form.type_bien} set={v => update("type_bien", v)} options={typesBien} />
          <Input label="Surface (m2)" val={form.surface} set={v => update("surface", v)} type="number" min={10} max={10000} />
          <Input label="Nombre d'etages" val={form.nb_etages} set={v => update("nb_etages", v)} type="number" min={1} max={20} />
        </div>
        <div style={STYLE.row}>
          <Input label="Annee de construction" val={form.annee_construction} set={v => update("annee_construction", v)} type="number" min={1800} max={2030} />
          <Input label="Annee de renovation" val={form.annee_renovation} set={v => update("annee_renovation", v)} type="number" min={1800} max={2030} />
          <Select label="Occupation" val={form.occupation} set={v => update("occupation", v)} options={occupations} />
        </div>
      </div>

      {/* STRUCTURE */}
      <div style={STYLE.section}>
        <h3 style={STYLE.sectionTitle}>Structure et materiaux</h3>
        <div style={STYLE.row}>
          <Select label="Type de structure" val={form.type_structure} set={v => update("type_structure", v)} options={typesStructure} />
          <Select label="Etat de la structure" val={form.etat_structure} set={v => update("etat_structure", v)} options={etats} />
        </div>
        <div style={STYLE.row}>
          <Select label="Fissures" val={form.fissures} set={v => update("fissures", v)} options={fissuresOpts} />
          <Select label="Affaissement" val={form.affaissement} set={v => update("affaissement", v)} options={["Non", "Oui"]} />
        </div>
      </div>

      {/* TOITURE */}
      <div style={STYLE.section}>
        <h3 style={STYLE.sectionTitle}>Toiture</h3>
        <div style={STYLE.row}>
          <Select label="Type de toiture" val={form.type_toiture} set={v => update("type_toiture", v)} options={toitures} />
          <Input label="Age de la toiture (annee)" val={form.age_toiture} set={v => update("age_toiture", v)} type="number" min={1800} max={2030} />
          <Select label="Etat de la toiture" val={form.etat_toiture} set={v => update("etat_toiture", v)} options={etats} />
        </div>
        <div style={STYLE.row}>
          <Select label="Isolation toiture" val={form.isolation_toiture} set={v => update("isolation_toiture", v)} options={isolationNiveaux} />
          <Select label="Isolation murs" val={form.isolation_murs} set={v => update("isolation_murs", v)} options={isolationNiveaux} />
          <Select label="Infiltrations" val={form.infiltrations} set={v => update("infiltrations", v)} options={["Non", "Oui"]} />
        </div>
      </div>

      {/* SOUS-SOL */}
      <div style={STYLE.section}>
        <h3 style={STYLE.sectionTitle}>Sous-sol et electricite</h3>
        <div style={{ ...STYLE.row, alignItems: "center" }}>
          <Checkbox label="Presence d'un sous-sol" val={form.presence_sous_sol} set={v => update("presence_sous_sol", v)} />
          <Checkbox label="Presence d'une cave" val={form.presence_cave} set={v => update("presence_cave", v)} />
          <Input label="Annee installation electrique" val={form.installation_electrique_annee} set={v => update("installation_electrique_annee", v)} type="number" min={1900} max={2030} />
        </div>
      </div>

      {/* ACTIONS */}
      <div style={STYLE.actions}>
        <button type="button" style={STYLE.btnSecondary} onClick={() => setForm(defaultForm)}>
          Reinitialiser
        </button>
        <button
          type="submit"
          style={{ ...STYLE.btnPrimary, opacity: submitting ? 0.6 : 1 }}
          disabled={submitting}
        >
          {submitting ? "Analyse en cours..." : "Lancer l'analyse"}
        </button>
      </div>
    </form>
  );
}
'''

path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'src', 'components', 'Form', 'ClientForm.tsx')
os.makedirs(os.path.dirname(path), exist_ok=True)
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"Written {len(content)} chars to {path}")
