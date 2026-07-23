import { useState, useCallback } from "react";
import type { ChatMessage } from "../types/models";
import { api } from "../services/api";

interface UseChatReturn {
  messages: ChatMessage[];
  sendMessage: (question: string) => Promise<void>;
  loading: boolean;
  error: string | null;
}

export function useChat(sessionId: string): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendMessage = useCallback(
    async (question: string) => {
      const userMsg: ChatMessage = {
        role: "user",
        content: question,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMsg]);
      setLoading(true);
      setError(null);

      try {
        const response = await api.chat(sessionId, {
          question,
          historique: messages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
        });

        const assistantMsg: ChatMessage = {
          role: "assistant",
          content: response.reponse,
          timestamp: Date.now(),
        };

        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Erreur lors de l'envoi");
      } finally {
        setLoading(false);
      }
    },
    [sessionId, messages]
  );

  return { messages, sendMessage, loading, error };
}
