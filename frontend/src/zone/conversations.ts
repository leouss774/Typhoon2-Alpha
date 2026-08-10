// =============================================================================
//   TYPHOON — /zone : historique des diagnostics (adresses récentes).
//   Persisté en localStorage (aucun backend nécessaire pour l'instant) :
//   la liste alimente la section « Récent » de la sidenav, façon Gemini.
// =============================================================================

export interface Conversation {
  id: string;
  address: string;
  updatedAt: number;
}

const STORAGE_KEY = 'typhoon.zone.conversations';
const MAX_ITEMS = 20;

export function loadConversations(): Conversation[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (c): c is Conversation =>
          !!c && typeof c.id === 'string' && typeof c.address === 'string'
      )
      .slice(0, MAX_ITEMS);
  } catch {
    return [];
  }
}

export function saveConversations(list: Conversation[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_ITEMS)));
  } catch {
    /* quota / privé — ignorer silencieusement */
  }
}

/** Ajoute (ou remonte) une adresse en tête de l'historique, sans doublon. */
export function addConversation(list: Conversation[], address: string): Conversation[] {
  const trimmed = address.trim();
  if (!trimmed) return list;

  const key = trimmed.toLowerCase();
  const without = list.filter((c) => c.address.toLowerCase() !== key);
  const next: Conversation[] = [
    { id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`, address: trimmed, updatedAt: Date.now() },
    ...without,
  ];
  return next.slice(0, MAX_ITEMS);
}

/** Supprime une conversation de l'historique. */
export function removeConversation(list: Conversation[], id: string): Conversation[] {
  return list.filter((c) => c.id !== id);
}
