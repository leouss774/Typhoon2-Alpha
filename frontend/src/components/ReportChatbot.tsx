import { FormEvent, useEffect, useRef, useState } from 'react';
import { API, type RapportNarratif, type RisqueReport } from '../zone/config';

type Message = { author: 'assistant' | 'visitor'; text: string };
type SpeechRecognitionInstance = { lang: string; interimResults: boolean; continuous: boolean; start: () => void; stop: () => void; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

const welcome = 'Bonjour 👋 Je suis votre assistant de Typhon pour expliquer le rapport IA. Comment puis-je vous aider ? Posez-moi une question sur une recommandation, un risque, le diagnostic ou sur Typhon lui-même : je vous réponds à partir de ce rapport.';

function formatMessage(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => part.startsWith('**') && part.endsWith('**')
    ? <strong key={index}>{part.slice(2, -2)}</strong>
    : <span key={index}>{part}</span>);
}

/** Chat contextualisé au Rapport IA, sans avatar humain. */
export function ReportChatbot({ report, rapport }: { report: RisqueReport; rapport?: RapportNarratif | null }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [messages, setMessages] = useState<Message[]>([{ author: 'assistant', text: welcome }]);
  const transcript = useRef<HTMLDivElement>(null);

  useEffect(() => { transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: 'smooth' }); }, [messages, open]);

  function toggleVoice() {
    const speechWindow = window as Window & { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor };
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!Recognition) {
      setMessages((current) => [...current, { author: 'assistant', text: 'La commande vocale n’est pas prise en charge par ce navigateur. Vous pouvez écrire votre question.' }]);
      return;
    }
    const recognition = new Recognition();
    recognition.lang = 'fr-FR'; recognition.interimResults = false; recognition.continuous = false;
    recognition.onresult = (event) => setInput(event.results[0]?.[0]?.transcript || '');
    recognition.onend = () => setListening(false); recognition.onerror = () => setListening(false);
    setListening(true); recognition.start();
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = input.trim();
    if (!question || sending) return;
    const next = [...messages, { author: 'visitor' as const, text: question }];
    setMessages(next); setInput(''); setSending(true); setSpeaking(true);
    try {
      const response = await fetch(`${API}/api/chat/stream`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          context: JSON.stringify({ report, rapport }).slice(0, 48000),
          messages: next.slice(-8).map((message) => ({ role: message.author === 'visitor' ? 'user' : 'assistant', content: message.text })),
        }),
      });
      if (!response.ok || !response.body) throw new Error('Service indisponible');
      // Le placeholder est ajouté tout de suite après votre message : la
      // réponse reste visuellement dessous, même pendant le streaming.
      setMessages((current) => [...current, { author: 'assistant', text: '' }]);
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ''; let answer = '';
      const processEvent = (item: string) => {
        const line = item.split('\n').find((entry) => entry.startsWith('data: '));
        if (!line || line.slice(6) === '[DONE]') return;
        let chunk: { text?: string; error?: string };
        try { chunk = JSON.parse(line.slice(6)); } catch { return; }
        if (chunk.error) throw new Error(chunk.error);
        if (chunk.text) {
          answer += chunk.text;
          setMessages((current) => [...current.slice(0, -1), { author: 'assistant', text: answer }]);
        }
      };
      while (true) {
        const { value, done } = await reader.read(); buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const events = buffer.split('\n\n'); buffer = events.pop() || '';
        for (const item of events) processEvent(item);
        if (done) { if (buffer.trim()) processEvent(buffer); break; }
      }
      if (!answer) throw new Error('Réponse vide');
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const voice = new SpeechSynthesisUtterance(answer.replace(/\*\*/g, ''));
        voice.lang = 'fr-FR'; voice.onend = () => setSpeaking(false); voice.onerror = () => setSpeaking(false);
        window.speechSynthesis.speak(voice);
      } else setSpeaking(false);
    } catch {
      // La réponse doit TOUJOURS s'afficher sous le message de l'utilisateur :
      // on remplace uniquement le placeholder assistant vide, sinon on ajoute
      // le message d'erreur en dessous (jamais à la place du message envoyé).
      setMessages((current) => {
        const last = current[current.length - 1];
        if (last && last.author === 'assistant' && last.text === '') {
          return [...current.slice(0, -1), { author: 'assistant', text: 'Je ne peux pas joindre le service conversationnel pour le moment. Réessayez dans quelques instants.' }];
        }
        return [...current, { author: 'assistant', text: 'Je ne peux pas joindre le service conversationnel pour le moment. Réessayez dans quelques instants.' }];
      });
      setSpeaking(false);
    } finally { setSending(false); }
  }

  return <aside className="report-chat" aria-label="Assistant du rapport IA">
    {open && <section className="report-chat__panel">
      <header><strong>Assistant Typhoon</strong><button type="button" onClick={() => setOpen(false)} aria-label="Fermer le chat">×</button></header>
      <div className="report-chat__messages" ref={transcript} aria-live="polite">
        {messages.map((message, index) => <p key={index} className={`report-chat__message report-chat__message--${message.author}`}>{formatMessage(message.text)}</p>)}
      </div>
      <form className="report-chat__form" onSubmit={submit}>
        <button type="button" className={`report-chat__voice ${listening ? 'is-listening' : ''}`} onClick={toggleVoice} aria-label={listening ? 'Écoute en cours' : 'Dicter une question'} disabled={sending}>{listening ? '■' : '🎙'}</button>
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Posez votre question…" aria-label="Votre question sur le rapport" disabled={sending} />
        <button type="submit" aria-label="Envoyer" disabled={sending}>{sending ? '…' : '↑'}</button>
      </form>
    </section>}
    <button type="button" className={`report-chat__bubble ${speaking || sending ? 'is-speaking' : ''}`} onClick={() => setOpen((value) => !value)} aria-expanded={open} aria-label={open ? 'Fermer le chat du rapport' : 'Ouvrir le chat du rapport'}>
      <span className="report-chat__robot-wrap"><img src="/Capture-removebg-preview.png" alt="Robot assistant Typhoon" /><i className="report-chat__mouth" /><i className="report-chat__waves"><b /><b /><b /></i></span>
    </button>
  </aside>;
}
