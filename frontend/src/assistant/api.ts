import { API } from '../zone/config';
import type { AssistantContexte } from './AssistantContext';

export type ChatMessage = { role: 'user' | 'assistant'; content: string };

export async function sendChatMessage(
  messages: ChatMessage[],
  contexte: AssistantContexte
): Promise<string> {
  const resp = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, contexte }),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => null);
    const detail = typeof err?.detail === 'string' ? err.detail : null;
    throw new Error(detail || `Assistant indisponible (HTTP ${resp.status}).`);
  }

  const data = (await resp.json()) as { reponse: string };
  return data.reponse;
}
