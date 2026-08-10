<script setup>
import { ref, reactive, onMounted, onUnmounted, toRaw, watch } from 'vue'

const messageInput = ref(null)
const chatMessagesEnd = ref(null);

// Commande vocale : si l'utilisateur parle (🎙), la réponse est renvoyée
// en voix (homme de préférence). Sinon, réponse en simple texte.
const isListening = ref(false);
const voiceReply = ref(false);
let recognitionRef = null;

// ---------------------------------------------------------------------------
// Branchement sur l'API Typhon (/api/chat/stream) pour conserver exactement
// les mêmes réponses que le chatbot classique de la vitrine.
// ---------------------------------------------------------------------------
const API = import.meta.env.VITE_TYPHOON_API || window.TYPHOON_API || 'http://127.0.0.1:8765';

const state = reactive({
  messageHistory: [],
  isChatting: false
})

watch(() => state.isChatting,
  (isChatting) => {
    if (isChatting) {
      setTimeout(() => {
        messageInput.value.focus();
      }, 10);
    }
  });

const messageHistory = state.messageHistory;

window.messageHistory = messageHistory;

const actionHistory = [];

// Timer de la saisie mot par mot : un seul à la fois (si l'utilisateur envoie
// un nouveau message pendant la frappe, on stoppe le précédent).
let typeTimer = null;
let typeTimerMessage = null;

const scrollRequestQueue = [];
const scrollInterval = setInterval(() => {
  if (scrollRequestQueue.length > 0) {
    scrollToBottom();
    scrollRequestQueue.shift();
  }
}, 500);

function scrollToBottom() {
  chatMessagesEnd.value.scrollIntoView({
    behavior: "smooth"
  });
}

function submitScrollRequest() {
  if (scrollRequestQueue.length == 0) {
    scrollRequestQueue.push(true);

    // force scroll now so don't have to wait for interval delay
    scrollToBottom();
  }
}

// Rendu des messages : le HTML est échappé (sécurité), puis les paires
// **texte** deviennent du gras. Les sauts de ligne (\n\n des paragraphes)
// sont conservés par le CSS (white-space: pre-wrap).
function renderMarkdown(text) {
  const escaped = String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
  return escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

// Retour à l'accueil : la page robot est embarquée en iframe dans l'app —
// on notifie l'hôte qui ferme la conversation (postMessage géré par
// TyphonChatbot). Si la page est ouverte directement (hors iframe), on
// revient à la page d'accueil de l'app pour que le × fasse toujours
// quelque chose de visible.
function goHome() {
  let embedded = false;
  try {
    embedded = !!(window.parent && window.parent !== window);
  } catch (e) {
    embedded = false; // iframe croisée → on considère qu'on est seul
  }
  if (embedded) {
    try {
      window.parent.postMessage({ type: 'typhon-robot-close' }, '*');
      return;
    } catch (e) {
      // Le postMessage a échoué → on retombe sur le fallback ci-dessous
    }
  }
  // Page ouverte en direct : navigation vers l'accueil de l'app Typhon.
  const home = window.TYPHOON_HOME_URL || 'http://localhost:5173/';
  window.location.href = home;
}

function stripResponse(content) {
  // handle case of >>>. instead of >>>
  content = content.replace(">>>.", ">>>");

  var start = content.indexOf("<<<");
  var end = content.indexOf(">>>");

  if (start != -1 && end != -1) {
    var message = content.substring(0, start) + content.substring(end + 3);

    return message;
  } else if (start != -1) {
    var message = content.substring(0, start);

    return message;
  } else {
    return content;
  }
}

function parseResponse(content) {
  // Example response:
  // Hello there! I am ready to assist you. <<< State=Idle, Emote=None, Expression=[Angry=0, Surprised=0, Sad=0] >>>. How can I help you today?

  // handle case of >>>. instead of >>>
  content = content.replace(">>>.", ">>>");

  // The prompt uses "Thumbs Up" instead of "ThumbsUp" to help the AI model understand it better
  content = content.replace("Emote=Thumbs Up", "Emote=ThumbsUp")

  var start = content.indexOf("<<<");
  var end = content.indexOf(">>>");

  if (start != -1 && end != -1) {
    var footnote = content.substring(start, end + 3);
    var message = content.substring(0, start) + content.substring(end + 3);

    var state = footnote.match(/State=(\w+)/)[1];
    var emote = footnote.match(/Emote=(\w+)/)[1];

    var expressionMatches = footnote.match(/Expression=\[(\w+=\d+\.?\d*,\s\w+=\d+\.?\d*,\s\w+=\d+\.?\d*)\]/);
    var expression = expressionMatches[1];

    var expressionMap = {};
    expression.split(", ").forEach((item) => {
      var [key, value] = item.split("=");
      expressionMap[key] = value;
    });

    var expressionVector = [
      Number(expressionMap["Angry"]),
      Number(expressionMap["Surprised"]),
      Number(expressionMap["Sad"])
    ];

    return {
      message: message,
      state: state,
      emote: emote,
      expressionMap: expressionMap,
      expressionVector: expressionVector
    };
  } else {
    throw 'Footnote not found in response'
  }
}

async function sendMessage(message, speakReply) {
  messageHistory.push(message);

  if (message.role == "user") {
    messageHistory.push({
      role: "assistant",
      content: ""
    });
  }
  const responseMessageIndex = messageHistory.length - 1;

  const actionIndex = actionHistory.length;
  actionHistory.push(null);

  const inputMessages = toRaw(messageHistory).slice(0, responseMessageIndex + 1).map((message) => {
    return {
      role: message.role,
      content: message.content
    };
  });

  // Le placeholder assistant vide (créé ci-dessus) ne doit pas partir en
  // requête : le backend exige content non vide (min_length=1 → 422 sinon).
  // On garde exactement la même fenêtre que le chatbot classique (8 derniers
  // messages réels) pour obtenir des réponses identiques.
  const body = {
    messages: inputMessages
      .filter((m) => typeof m.content === 'string' && m.content.trim().length > 0)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.content }))
  };

  try {
    const res = await fetch(`${API}/api/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) throw new Error(`Le service conversationnel est temporairement indisponible. (HTTP ${res.status})`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let fullText = '';

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
        const chunk = JSON.parse(data);
        if (chunk.error) throw new Error(chunk.error);
        if (chunk.text) fullText += chunk.text;
      }
      if (done) break;
    }
    if (!fullText) throw new Error('Réponse vide');

    messageHistory[responseMessageIndex].content = fullText;
    actionHistory[actionIndex] = fullText;

    // Affichage mot par mot : à chaque mot, le robot ouvre la bouche et bouge
    // les bras (voir window.robotTalk* dans index.html). Le texte complet reste
    // dans content (utilisé pour l'historique envoyé au backend). On découpe en
    // tokens mots+espaces pour préserver les sauts de ligne (\n\n des paragraphes).
    var strippedResponse = stripResponse(fullText);
    const tokens = strippedResponse.match(/\S+\s*/g) || [''];
    let wordIndex = 0;
    // Réponse vocale (voix homme) UNIQUEMENT si le message a été dicté au 🎙
    // (flag capturé à l'envoi — sinon un texte tapé pourrait être prononcé).
    const shouldSpeak = !!speakReply;
    if (window.robotTalkStart) window.robotTalkStart();
    messageHistory[responseMessageIndex].displayContent = '';
    // Si un autre message est encore en cours de frappe, on finalise son texte
    // (sinon sa bulle resterait tronquée à jamais) avant d'en démarrer un nouveau.
    if (typeTimer) {
      clearInterval(typeTimer);
      if (typeTimerMessage && typeTimerMessage._fullDisplay) {
        typeTimerMessage.displayContent = typeTimerMessage._fullDisplay;
      }
    }
    typeTimerMessage = messageHistory[responseMessageIndex];
    typeTimerMessage._fullDisplay = strippedResponse;
    typeTimer = setInterval(() => {
      wordIndex++;
      messageHistory[responseMessageIndex].displayContent = tokens.slice(0, wordIndex).join('');
      if (window.robotTalkPulse) window.robotTalkPulse();
      submitScrollRequest();
      if (wordIndex >= tokens.length) {
        clearInterval(typeTimer);
        typeTimer = null;
        typeTimerMessage = null;
        if (window.robotTalkStop) window.robotTalkStop();
        // Réponse parlée (voix homme) uniquement si la question a été dictée au 🎙
        if (shouldSpeak) speak(fullText);
      }
    }, 70);

    try {
      var parsedResponse = parseResponse(fullText);
      window.actionFunctions.state[parsedResponse.state]();
      if (parsedResponse.emote != "None") {
        window.actionFunctions.emote[parsedResponse.emote]();
      }
      window.actionFunctions.expression(parsedResponse.expressionVector);
    } catch (e) {
      // La réponse de Typhon ne contient pas de footnote d'animation : on
      // laisse le robot dans son état par défaut. Rien à faire ici.
    }

    return res;
  } catch (e) {
    messageHistory[responseMessageIndex].content = "Je ne peux pas joindre le service conversationnel pour le moment. Réessayez dans quelques instants.";
    messageHistory[responseMessageIndex].displayContent = messageHistory[responseMessageIndex].content;
    submitScrollRequest();
    console.error(e);
    return null;
  }
}

onMounted(() => {
  // Démarrage direct de la conversation : plus de bouton « Start Chatting ».
  startChatting();
  // Récupération des voix (certains navigateurs les chargent de façon async)
  if ('speechSynthesis' in window) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function () { window.speechSynthesis.getVoices(); };
  }
});

onUnmounted(() => {
  if (typeTimer) clearInterval(typeTimer);
  if (recognitionRef) { try { recognitionRef.stop(); } catch (e) {} }
  if (window.robotTalkStop) window.robotTalkStop();
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
});

// ---------------------------------------------------------------------------
// Commande vocale — dictée de la question (🎙) et réponse parlée (voix homme).
// ---------------------------------------------------------------------------
function speak(text) {
  if (!('speechSynthesis' in window)) return;
  window.speechSynthesis.cancel();
  const clean = text.replace(/\*\*/g, '').replace(/\n+/g, ' ').trim();
  if (!clean) return;
  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = 'fr-FR';
  utter.rate = 1;
  utter.pitch = 0.75; // ton grave (masculin) par défaut
  // Voix masculine francophone si disponible (Microsoft Denis/Paul, etc.)
  try {
    const voices = window.speechSynthesis.getVoices();
    const frVoices = voices.filter(function (v) { return (v.lang || '').toLowerCase().indexOf('fr') === 0; });
    const male = frVoices.find(function (v) {
      return /(male|denis|paul|thomas|pierre|henri|hubert|remy|remi|mathieu|guillaume|david|marc|jean|voix fr|france male)/i.test(v.name);
    });
    if (male) { utter.voice = male; utter.pitch = 1; }
    else if (frVoices.length) { utter.voice = frVoices[0]; }
  } catch (e) { /* voix indisponible, on garde les réglages par défaut */ }
  window.speechSynthesis.speak(utter);
}

function toggleVoiceInput() {
  const w = window;
  const Recognition = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (isListening.value && recognitionRef) {
    recognitionRef.stop();
    return;
  }
  if (!Recognition) {
    // Le navigateur ne supporte pas la dictée : on l'indique dans le chat.
    messageHistory.push({
      role: "assistant",
      content: "La commande vocale n'est pas prise en charge par ce navigateur. Vous pouvez écrire votre question normalement.",
      displayContent: "La commande vocale n'est pas prise en charge par ce navigateur. Vous pouvez écrire votre question normalement."
    });
    submitScrollRequest();
    return;
  }
  const recognition = new Recognition();
  recognition.lang = 'fr-FR';
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.onresult = function (event) {
    const transcript = event.results[0]?.[0]?.transcript || '';
    if (!transcript.trim()) return;
    voiceReply.value = true; // la réponse sera parlée (voix homme)
    messageInput.value.value = transcript;
    formSendMessage();
  };
  recognition.onend = function () { isListening.value = false; };
  recognition.onerror = function () { isListening.value = false; };
  recognitionRef = recognition;
  isListening.value = true;
  recognition.start();
}

async function startChatting() {
  state.isChatting = true;

  const welcome = "Bonjour 👋 Je suis l’assistant de Typhon, la plateforme qui transforme une adresse en diagnostic climatique, en travaux de prévention et en preuves vérifiées de réduction du risque. Comment puis-je vous aider aujourd’hui ?";
  messageHistory.push({
    role: "assistant",
    content: welcome,
    displayContent: welcome
  });
  submitScrollRequest();
}

async function formSendMessage() {
  var inputMessage = messageInput.value.value;

  messageInput.value.value = '';

  // Ne pas envoyer un message vide (l'API le rejette et l'historique serait
  // corrompu) — même garde que le chatbot classique.
  if (!inputMessage || inputMessage.trim().length === 0) {
    return;
  }

  // On capture immédiatement le flag vocal : un message tapé au clavier ne
  // doit JAMAIS produire de réponse parlée (commande vocale = voix, sinon texte).
  const speakReply = voiceReply.value;
  voiceReply.value = false;

  const response = await sendMessage({
    role: "user",
    content: inputMessage,
    displayContent: inputMessage
  }, speakReply);
}

</script>

<template>
  <button type="button" class="chat-back" @click="goHome" aria-label="Retour à l'accueil" title="Retour à l'accueil">×</button>
  <div id="chat_area">
    <div v-show="state.isChatting">
      <div id="chat_message_box">
        <div v-for="(message, index) in state.messageHistory" :key="index">
          <div v-if="message.displayContent" v-bind:class="message.role == 'user' ? 'user_message' : 'assistant_message'">
            <div class="message_span" v-html="renderMarkdown(message.displayContent)"></div>
          </div>
        </div>
        <div ref="chatMessagesEnd"></div>
      </div>

      <div class="input-group">
        <button type="button" class="btn btn-voice" :class="{ 'is-listening': isListening }" @click="toggleVoiceInput"
          :aria-label="isListening ? 'Arrêter la commande vocale' : 'Commande vocale (réponse en voix homme)'"
          :title="isListening ? 'Écoute en cours…' : 'Commande vocale'">{{ isListening ? '■' : '🎙' }}</button>
        <input type="text" class="form-control" placeholder="Posez votre question…" aria-label="Posez votre question"
          aria-describedby="button-addon2" ref="messageInput" v-on:keyup.enter="formSendMessage">
        <button class="btn btn-send" type="button" id="button-addon2" @click="formSendMessage" aria-label="Envoyer">➤</button>
      </div>
    </div>
  </div>

</template>

<style scoped>
/* Panneau de conversation : grand et semi-transparent pour laisser voir le
   robot derrière. Les bulles de l'assistant ont une queue orientée vers le bas
   (effet « bulle qui sort de la bouche »). */
#chat_area {
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  padding: clamp(1rem, 2.5vw, 3rem);
  background-color: transparent;
  z-index: 100;
  width: min(1440px, 100vw);
  pointer-events: none;
  text-align: center;
}

#chat_area .input-group,
#chat_area .btn,
#chat_message_box {
  pointer-events: auto;
}

.user_message {
  display: flex;
  flex-direction: row-reverse;
  color: darkblue;
}

.user_message .message_span {
  background-color: rgba(27, 63, 56, 0.5);
  color: #fff;
  border-radius: 14px 14px 4px 14px;
  padding: 14px 17px;
  margin: 6px 0;
  max-width: 94%;
  font-size: 1.1rem;
  line-height: 1.55;
  white-space: pre-wrap;
  text-align: left;
}

.assistant_message {
  display: flex;
  color: black;
}

.assistant_message .message_span {
  position: relative;
  background-color: rgba(255, 255, 255, 0.55);
  color: #14221e;
  border: 1px solid rgba(255, 255, 255, 0.35);
  border-radius: 14px 14px 14px 4px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.12);
  padding: 14px 17px;
  margin: 6px 0;
  max-width: 94%;
  font-size: 1.1rem;
  line-height: 1.55;
  white-space: pre-wrap;
  text-align: left;
}

/* Queue de la bulle pointée vers la bouche du robot */
.assistant_message .message_span::after {
  content: '';
  position: absolute;
  left: 30px;
  bottom: -9px;
  border: 9px solid transparent;
  border-top-color: rgba(255, 255, 255, 0.5);
  border-bottom: 0;
}

#chat_message_box {
  overflow-y: auto;
  /* La discussion reste TOUJOURS grande, même avec peu de messages :
     hauteur minimale imposée (min-height), pas seulement un max. Sur les
     petits écrans, on plafonne pour garder le robot visible derrière. */
  min-height: clamp(520px, 80vh, 920px);
  max-height: calc(100vh - 110px);
  padding: clamp(1rem, 2vw, 2rem);
  border-radius: 14px;
  /* Barre de défilement invisible (le défilement reste fonctionnel) */
  scrollbar-width: none;
  -ms-overflow-style: none;
}

/* Chrome, Safari, Edge : scrollbar invisible */
#chat_message_box::-webkit-scrollbar {
  width: 0;
  height: 0;
  display: none;
}

.input-group {
  margin-top: 8px;
  text-align: left;
  flex-wrap: nowrap;
}

.input-group .btn-voice {
  border-radius: 20px 0 0 20px;
  border: 1px solid rgba(0, 0, 0, 0.18);
  background-color: rgba(255, 255, 255, 0.75);
  color: #1b3f38;
  font-size: 1.1rem;
}

.input-group .btn-voice.is-listening {
  background-color: rgba(214, 69, 65, 0.85);
  color: #fff;
  animation: voice-pulse 1s ease-in-out infinite;
}

@keyframes voice-pulse {
  50% { transform: scale(1.06); }
}

.input-group .form-control {
  border-radius: 0;
  border: 1px solid rgba(0, 0, 0, 0.18);
  background-color: rgba(255, 255, 255, 0.75);
  font-size: 1.08rem;
  padding: 0.85rem 1rem;
}

.input-group .btn-send {
  border-radius: 0 20px 20px 0;
  border: 1px solid rgba(0, 0, 0, 0.18);
  background-color: #1b3f38;
  color: #fff;
  font-size: 1.15rem;
  line-height: 1;
}

/* Bouton × « retour à l'accueil » : flottant en haut à droite, au-dessus
   de la discussion. Envoyé par postMessage → l'app hôte ferme le chat. */
.chat-back {
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 300;
  width: 2.5rem;
  height: 2.5rem;
  padding: 0;
  border: 1px solid rgba(0, 0, 0, 0.16);
  border-radius: 50%;
  background-color: rgba(255, 255, 255, 0.72);
  color: #14221e;
  font-size: 1.5rem;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
  transition: transform 0.15s ease, background-color 0.15s ease;
}

.chat-back:hover {
  background-color: #fff;
  transform: scale(1.08);
}
</style>
