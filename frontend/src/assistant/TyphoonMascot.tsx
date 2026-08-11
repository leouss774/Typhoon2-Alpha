import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useAssistantContexte } from './AssistantContext';
import { sendChatMessage, type ChatMessage } from './api';
import { MarkdownLite } from './MarkdownLite';
import '../styles/mascot.css';

const GREETING: ChatMessage = {
  role: 'assistant',
  content:
    "Bonjour, je suis le compagnon Typhoon. Je peux vous expliquer la plateforme, " +
    'comment le score de risque est calculé, ou faire la synthèse des risques et ' +
    'recommandations du bien affiché à l\'écran. Que puis-je faire pour vous ?',
};

export function TyphoonMascot() {
  const { contexte } = useAssistantContexte();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([GREETING]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  /* Sur la page d'accueil (préloader), la mascotte flotte AU-DESSUS de la
     bande presse défilante en bas d'écran. Quand l'iframe du préloader
     signale que le préloader est masqué (clic sur « Comment anticiper cela
     ? »), elle redescend à sa position normale (bas droit). */
  const location = useLocation();
  const isHome = location.pathname === '/';
  const [preloaderDone, setPreloaderDone] = useState(false);

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      /* Même origine (iframe du préloader) + type attendu uniquement. */
      if (event.origin === window.location.origin && event.data && event.data.type === 'typhoon:preloader-hidden') {
        setPreloaderDone(true);
      }
    }
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, []);

  /* Retour sur la page d'accueil : le préloader est réaffiché (nouveau
     chargement de l'iframe), on remonte donc la mascotte au-dessus de la
     bande presse jusqu'au prochain clic. */
  useEffect(() => {
    if (isHome) setPreloaderDone(false);
  }, [isHome]);

  const overPress = isHome && !preloaderDone;

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, sending, open]);

  async function handleSend() {
    const value = input.trim();
    if (!value || sending) return;
    setError(null);
    setInput('');
    const next = [...messages, { role: 'user', content: value } as ChatMessage];
    setMessages(next);
    setSending(true);
    try {
      const reponse = await sendChatMessage(
        next.filter((m) => m !== GREETING),
        contexte
      );
      setMessages((prev) => [...prev, { role: 'assistant', content: reponse }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Assistant momentanément indisponible.');
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  return (
    <div className={overPress ? 'mascot-root mascot-over-press' : 'mascot-root'}>
      {open && (
        <div className="mascot-panel" role="dialog" aria-label="Compagnon virtuel Typhoon">
          <div className="mascot-panel-header">
            <img src="/mascotte_typhoon.png" alt="" className="mascot-panel-avatar" />
            <div className="mascot-panel-title">
              <strong>Compagnon Typhoon</strong>
              <span>{contexte ? 'Diagnostic en cours chargé' : 'Aucun diagnostic chargé'}</span>
            </div>
            <button
              type="button"
              className="mascot-panel-close"
              aria-label="Fermer le chat"
              onClick={() => setOpen(false)}
            >
              ×
            </button>
          </div>

          <div className="mascot-panel-messages" ref={listRef}>
            {messages.map((m, i) => (
              <div key={i} className={m.role === 'user' ? 'mascot-msg mascot-msg-user' : 'mascot-msg mascot-msg-bot'}>
                {m.role === 'assistant' ? <MarkdownLite text={m.content} /> : m.content}
              </div>
            ))}
            {sending && (
              <div className="mascot-msg mascot-msg-bot mascot-msg-typing" aria-live="polite">
                <span />
                <span />
                <span />
              </div>
            )}
            {error && <div className="mascot-msg mascot-msg-error">{error}</div>}
          </div>

          <div className="mascot-panel-input">
            <textarea
              rows={1}
              placeholder="Posez votre question…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending}
            />
            <button type="button" onClick={() => void handleSend()} disabled={sending || !input.trim()} aria-label="Envoyer">
              ➤
            </button>
          </div>
        </div>
      )}

      <div className="mascot-trigger">
        {!open && <span className="mascot-trigger-label">Votre compagnon virtuel Typhoon</span>}
        <button
          type="button"
          className="mascot-fab"
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? 'Fermer le compagnon Typhoon' : 'Ouvrir le compagnon Typhoon'}
        >
          <img src="/mascotte_typhoon.png" alt="Compagnon Typhoon" />
        </button>
      </div>
    </div>
  );
}
