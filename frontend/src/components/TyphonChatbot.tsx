import { FormEvent, useEffect, useRef, useState } from 'react';
import { API, ROBOT_COMPANION_URL } from '../zone/config';

type Message = {
  author: 'assistant' | 'visitor';
  text: string;
};
type SpeechRecognitionInstance = { lang: string; interimResults: boolean; continuous: boolean; start: () => void; stop: () => void; onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null; onend: (() => void) | null; onerror: (() => void) | null };
type SpeechRecognitionConstructor = new () => SpeechRecognitionInstance;

function formatMessage(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    return <span key={index}>{part}</span>;
  });
}

const welcome =
  "Bonjour 👋 Je suis l’assistant de Typhon, la plateforme qui transforme une adresse en diagnostic climatique, en travaux de prévention et en preuves vérifiées de réduction du risque. Comment puis-je vous aider aujourd’hui ?";

type RobotStatus = 'checking' | 'ready' | 'down';

export function TyphonChatbot({ fullScreen = false }: { fullScreen?: boolean }) {
  const [open, setOpen] = useState(false);
  const [robotStatus, setRobotStatus] = useState<RobotStatus>('checking');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [messages, setMessages] = useState<Message[]>([{ author: 'assistant', text: welcome }]);
  const transcript = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const voiceTextRef = useRef<string | null>(null);

  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: 'smooth' });
  }, [messages, open]);

  // Le × « retour à l'accueil » vit dans la page robot (iframe) : quand la page
  // embarquée envoie { type: 'typhon-robot-close' } par postMessage, on ferme la
  // conversation pour revenir à la page courante. On vérifie l'origine de
  // l'émetteur pour ignorer les messages forgés par d'autres pages.
  useEffect(() => {
    let robotOrigin = '';
    try { robotOrigin = new URL(ROBOT_COMPANION_URL).origin; } catch { robotOrigin = ''; }
    function onRobotMessage(event: MessageEvent) {
      if (event.data && event.data.type === 'typhon-robot-close') {
        // Si l'origine n'a pas pu être résolue (config malformée), on accepte
        // tout émetteur pour ne jamais bloquer la fermeture.
        if (!robotOrigin || event.origin === robotOrigin) setOpen(false);
      }
    }
    window.addEventListener('message', onRobotMessage);
    return () => window.removeEventListener('message', onRobotMessage);
  }, []);

  useEffect(() => {
    if (!open || robotStatus !== 'down' || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    const greeting = new SpeechSynthesisUtterance(welcome);
    greeting.lang = 'fr-FR';
    greeting.onstart = () => setSpeaking(true);
    greeting.onend = () => setSpeaking(false);
    window.speechSynthesis.speak(greeting);
  }, [open, robotStatus]);

  // Au clic sur le robot : on teste si le serveur du robot compagnon répond.
  // S'il est joignable, on affiche SON interface (iframe) ; sinon on garde le
  // chat classique en secours pour ne jamais bloquer la conversation.
  function probeRobot() {
    setRobotStatus('checking');
    // Timeout de 4 s : si le serveur robot ne répond pas, on bascule sur le
    // chat classique plutôt que de rester bloqué sur l'écran de connexion.
    fetch(ROBOT_COMPANION_URL, { method: 'HEAD', mode: 'no-cors', signal: AbortSignal.timeout(4000) })
      .then(() => setRobotStatus('ready'))
      .catch(() => setRobotStatus('down'));
  }

  function toggle() {
    const next = !open;
    if (next) probeRobot();
    setOpen(next);
  }

  function toggleVoice() {
    const speechWindow = window as Window & { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor };
    if (listening) { recognitionRef.current?.stop(); setListening(false); return; }
    const Recognition = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
    if (!Recognition) { setMessages((current) => [...current, { author: 'assistant', text: 'La commande vocale n’est pas prise en charge par ce navigateur.' }]); return; }
    const recognition = new Recognition();
    recognition.lang = 'fr-FR'; recognition.interimResults = false; recognition.continuous = false;
    recognition.onresult = (event) => {
      const spoken = event.results[0]?.[0]?.transcript || '';
      voiceTextRef.current = spoken;
      setInput((current) => `${current}${current ? ' ' : ''}${spoken}`.trim());
      window.setTimeout(() => document.querySelector<HTMLFormElement>('.typhon-chat__form')?.requestSubmit(), 0);
    };
    recognition.onend = () => setListening(false); recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition; recognition.start(); setListening(true);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = (voiceTextRef.current || input).trim();
    voiceTextRef.current = null;
    if (!question) return;
    const nextMessages = [...messages, { author: 'visitor' as const, text: question }];
    setMessages(nextMessages);
    setInput('');
    setSending(true);
    try {
      const response = await fetch(`${API}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: nextMessages.slice(-8).map((message) => ({ role: message.author === 'visitor' ? 'user' : 'assistant', content: message.text })),
        }),
      });
      if (!response.ok || !response.body) throw new Error('Service indisponible');
      setMessages((current) => [...current, { author: 'assistant', text: '' }]);
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let streamedText = '';
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';
        for (const event of events) {
          const line = event.split('\n').find((entry) => entry.startsWith('data: '));
          if (!line) continue;
          const data = line.slice(6);
          if (data === '[DONE]') continue;
          const chunk = JSON.parse(data) as { text?: string; error?: string };
          if (chunk.error) throw new Error(chunk.error);
          if (chunk.text) {
            streamedText += chunk.text;
            setMessages((current) => [...current.slice(0, -1), { author: 'assistant', text: streamedText }]);
          }
        }
        if (done) break;
      }
      if (!streamedText) throw new Error('Réponse vide');
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const speech = new SpeechSynthesisUtterance(streamedText.replace(/\*\*/g, ''));
        speech.lang = 'fr-FR';
        speech.onstart = () => setSpeaking(true);
        speech.onend = () => setSpeaking(false);
        window.speechSynthesis.speak(speech);
      }
    } catch {
      // La réponse doit TOUJOURS s'afficher sous le message de l'utilisateur :
      // on remplace uniquement le placeholder assistant vide, sinon on ajoute
      // le message d'erreur en dessous (jamais à la place du message envoyé).
      setMessages((current) => {
        const last = current[current.length - 1];
        if (last && last.author === 'assistant' && last.text === '') {
          return [...current.slice(0, -1), { author: 'assistant', text: "Je ne peux pas joindre le service conversationnel pour le moment. Réessayez dans quelques instants." }];
        }
        return [...current, { author: 'assistant', text: "Je ne peux pas joindre le service conversationnel pour le moment. Réessayez dans quelques instants." }];
      });
    } finally {
      setSending(false);
    }
  }

  const robotReady = open && robotStatus === 'ready';
  const robotDown = open && robotStatus === 'down';

  return (
    <aside className={`typhon-chat ${fullScreen ? 'typhon-chat--fullscreen' : ''}`} aria-label="Assistant Typhon">
      {/* Interface du robot compagnon 3D (robot-companion-main), branchée sur
          le même backend /api/chat/stream → réponses identiques au chat classique */}
      {(robotReady || (open && robotStatus === 'checking')) && (
        <section className="typhon-chat__robot-panel" aria-label="Robot compagnon 3D">
          {/* Le × est dans la page robot elle-même (bouton .chat-back) : il
              ferme ici la conversation via postMessage. Rien d'autre ici. */}
          {robotStatus === 'checking' ? (
            <div className="typhon-chat__robot-loading"><span className="typhon-chat__robot-loader" aria-hidden="true" /><p>Connexion au robot 3D…</p></div>
          ) : (
            <iframe className="typhon-chat__robot-frame" src={ROBOT_COMPANION_URL} title="Robot compagnon 3D Typhon" />
          )}
        </section>
      )}

      {robotDown && (
        <section className="typhon-chat__panel" aria-label="Conversation avec Typhon">
          <header className="typhon-chat__header typhon-chat__header--bare">
            <span className="typhon-chat__bare-title"><strong>Assistant Typhon</strong></span>
            <button type="button" className="typhon-chat__close" onClick={() => setOpen(false)} aria-label="Fermer la conversation">×</button>
          </header>
          <div className="typhon-chat__robot-offline" role="note">Le robot 3D n'est pas démarré — chat classique affiché (réponses identiques). Pour l'activer : <code>cd robot-companion-main && npm run dev</code>.</div>
          <div className="typhon-chat__messages" ref={transcript} aria-live="polite">
            {messages.map((message, index) => <p key={index} className={`typhon-chat__message typhon-chat__message--${message.author}`}>{formatMessage(message.text)}</p>)}
          </div>
          <form className="typhon-chat__form" onSubmit={submit}>
            <button type="button" className={`typhon-chat__voice ${listening ? 'is-listening' : ''}`} onClick={toggleVoice} aria-label={listening ? 'Arrêter la commande vocale' : 'Dicter une question'} disabled={sending}>{listening ? '■' : '●'}</button>
            <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Posez votre question…" aria-label="Votre question à Typhon" disabled={sending} />
            <button type="submit" aria-label="Envoyer" disabled={sending}>{sending ? '…' : '↑'}</button>
          </form>
        </section>
      )}

      <button type="button" className={`typhon-chat__toggle ${open ? 'is-open' : ''} ${speaking || listening ? 'is-active' : ''}`} onClick={toggle} aria-expanded={open} aria-label={open ? 'Fermer le chat Typhon' : 'Ouvrir le chat Typhon'}>
        <span className="typhon-chat__robot-wrap"><img src="/Capture-removebg-preview.png" alt="" className="typhon-chat__robot" /><i className="typhon-chat__mouth" aria-hidden="true" /><i className="typhon-chat__sound-waves" aria-hidden="true"><b /><b /><b /></i></span>
      </button>
    </aside>
  );
}
