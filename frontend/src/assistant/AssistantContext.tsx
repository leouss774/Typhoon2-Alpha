import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

/* Contrat "digital_twin" attendu par le backend (POST /chat, contexte) :
   adresse, bien, score_global, zones{risque,niveau,alea_principal,
   justification,recommandations}, projection_2050. Toutes les clés sont
   optionnelles — le back ignore ce qui manque. Voir backend/app/api/routes/chat.py. */
export type AssistantContexte = {
  adresse?: string;
  bien?: { type?: string | null; annee_construction?: number | null };
  score_global?: number;
  zones?: Record<string, unknown>;
  projection_2050?: { score_global?: number };
} | null;

type AssistantContextValue = {
  contexte: AssistantContexte;
  setContexte: (contexte: AssistantContexte) => void;
};

const AssistantContext = createContext<AssistantContextValue | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const [contexte, setContexte] = useState<AssistantContexte>(null);
  const value = useMemo(() => ({ contexte, setContexte }), [contexte]);
  return <AssistantContext.Provider value={value}>{children}</AssistantContext.Provider>;
}

/* À appeler depuis une page qui affiche un diagnostic (ex. Zone.tsx) pour
   que le compagnon IA réponde à propos du bien affiché à l'écran. */
export function useAssistantContexte() {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error('useAssistantContexte doit être utilisé sous AssistantProvider');
  return ctx;
}
