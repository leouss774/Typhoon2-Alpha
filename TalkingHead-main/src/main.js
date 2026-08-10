import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { AvatarTalkAnimator } from './AvatarTalkAnimator.js';

// ---------------------------------------------------------------------------
// Assistant Rapport IA — avatar 3D humain complet (Ready Player Me exporté en
// local depuis le projet avatar-chatbot : typhon-report-avatar.glb + clips
// Idle/Talking_* dans typhon-report-animations.glb) + chat branché sur le
// même backend /api/chat/stream que le chatbot assistant.
// Le contexte du rapport (diagnostic + recommandations) est reçu de l'app
// hôte par postMessage : les réponses sont donc identiques au chat « Aide ? ».
//
// NOTE : les avatars RPM sont chargés depuis des fichiers LOCAUX (l'URL en
// ligne models.readyplayer.me a été fermée le 31/01/2026) — aucun réseau
// requis. L'animation est pilotée par three.js directement.
// ---------------------------------------------------------------------------

const API = import.meta.env.VITE_TYPHOON_API || window.TYPHOON_API || 'http://127.0.0.1:8765';

const box = document.getElementById('chat_message_box');
const input = document.getElementById('chat-input');
const btnSend = document.getElementById('btn-send');
const btnVoice = document.getElementById('btn-voice');
const backBtn = document.getElementById('chat-back');
const avatarNode = document.getElementById('avatar');
const avatarError = document.getElementById('avatar-error');

// ── État du visage 3D ─────────────────────────────────────────────────────
let mixer = null;         // AnimationMixer (créé quand l'avatar est chargé)
let talker = null;        // AvatarTalkAnimator : bouche + bras + clignements
let headNode = null;      // nœud « head » : hochement pendant la parole

// ── État du chat ──────────────────────────────────────────────────────────
let context = null;       // contexte du rapport reçu de l'app hôte
const history = [];       // historique de la conversation
let isListening = false;  // commande vocale
let recognitionRef = null;

const welcome =
  'Bonjour 👋 Je suis votre assistant de Typhon pour expliquer le rapport IA. Comment puis-je vous aider ? Posez-moi une question sur une recommandation, un risque, le diagnostic ou sur Typhon lui-même : je vous réponds à partir de ce rapport.';

// ── Rendu des messages (gras **texte**, HTML échappé) ─────────────────────
function renderMarkdown(text) {
  const escaped = String(text || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
  return escaped.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

function addMessage(role, text) {
  const wrap = document.createElement('div');
  wrap.className = role === 'user' ? 'user_message' : 'assistant_message';
  const span = document.createElement('div');
  span.className = 'message_span';
  span.dataset.full = text;
  span.innerHTML = renderMarkdown(text);
  wrap.appendChild(span);
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
  return span;
}

// ── Animations de parole du visage ────────────────────────────────────────
// L'avatar « parle » : bouche animée (morphs ARKit) + gestes des bras
// (clips Mixamo Talking_*) pilotés par AvatarTalkAnimator. No-op tant que
// l'avatar et ses animations ne sont pas chargés (talker === null).
function pulseTalk() {
  if (talker && !talker.isTalking) talker.startTalking();
}

function stopTalk() {
  if (talker) talker.stopTalking();
  if (headNode) { headNode.rotation.x = 0; headNode.rotation.z = 0; }
}

// ── Parole : voix homme française + le visage « parle » en même temps ─────
function speak(text) {
  if (!('speechSynthesis' in window)) { stopTalk(); return; }
  window.speechSynthesis.cancel();
  const clean = text.replace(/\*\*/g, '').replace(/\n+/g, ' ').trim();
  if (!clean) return;
  const utter = new SpeechSynthesisUtterance(clean);
  utter.lang = 'fr-FR';
  utter.rate = 1;
  utter.pitch = 0.75; // ton grave (masculin) par défaut
  try {
    const voices = window.speechSynthesis.getVoices();
    const frVoices = voices.filter((v) => (v.lang || '').toLowerCase().indexOf('fr') === 0);
    const male = frVoices.find((v) => /(male|michel|denis|paul|thomas|pierre|henri|hubert|remy|remi|mathieu|guillaume|david|marc|jean|charles|jean-pierre|voix fr|france male)/i.test(v.name));
    if (male) { utter.voice = male; utter.pitch = 1; }
    else if (frVoices.length) { utter.voice = frVoices[0]; }
  } catch (e) {}
  // Pulse de bouche synchro avec les mots parlés (si supporté)
  utter.onstart = () => pulseTalk();
  utter.onboundary = (e) => {
    if (e && e.name === 'word') pulseTalk();
  };
  utter.onend = () => stopTalk();
  window.speechSynthesis.speak(utter);
}

// ── Envoi d'une question → /api/chat/stream (mêmes réponses que l'assistant) ──
async function sendQuestion(question) {
  question = (question || '').trim();
  if (!question || box.dataset.busy === '1') return;
  box.dataset.busy = '1';
  // Le geste commence tout de suite : l'avatar reste expressif même pendant
  // le court délai de génération de la réponse.
  pulseTalk();

  addMessage('user', question);
  history.push({ role: 'user', content: question });

  const placeholder = addMessage('assistant', '…');

  const body = {
    // Le backend limite context à 50 000 caractères : on tronque pour éviter un 422.
    context: (context || JSON.stringify({ diagnostic: 'Rapport IA en attente de contexte' })).slice(0, 48000),
    messages: history.slice(-8).map((m) => ({ role: m.role, content: m.content })),
  };

  try {
    const res = await fetch(API + '/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok || !res.body) throw new Error('HTTP ' + res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let full = '';

    const speakNow = window.voiceWanted === true; // réponse parlée si dictée au 🎙
    window.voiceWanted = false;

    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const events = buffer.split('\n\n');
      buffer = events.pop() || '';
      for (const evt of events) {
        const line = evt.split('\n').find((l) => l.startsWith('data: '));
        if (!line) continue;
        const data = line.slice(6);
        if (data === '[DONE]') continue;
        try {
          const chunk = JSON.parse(data);
          if (chunk.error) throw new Error(chunk.error);
          if (chunk.text) {
            full += chunk.text;
            placeholder.innerHTML = renderMarkdown(full);
            placeholder.dataset.full = full;
            box.scrollTop = box.scrollHeight;
            pulseTalk(); // le visage « parle » pendant la réponse
          }
        } catch (e) { if (e.message) throw e; }
      }
      if (done) break;
    }
    if (!full) throw new Error('Réponse vide');
    placeholder.dataset.full = full;
    history.push({ role: 'assistant', content: full });
    // La réponse est lue pour que l'avatar parle vraiment, pas uniquement
    // lorsqu'elle provient de la dictée vocale.
    speak(full);
  } catch (e) {
    placeholder.innerHTML = renderMarkdown('Je ne peux pas joindre le service conversationnel pour le moment. Réessayez dans quelques instants.');
    stopTalk();
    console.error(e);
  } finally {
    delete box.dataset.busy;
  }
}

// ── Réception du contexte du rapport depuis l'app hôte ────────────────────
window.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'typhon-report-context') {
    context = event.data.context || null;
  }
});

// ── Retour à l'accueil (×) : ferme la conversation dans l'app hôte ────────
backBtn.addEventListener('click', () => {
  let embedded = false;
  try { embedded = !!(window.parent && window.parent !== window); } catch (e) { embedded = false; }
  if (embedded) {
    try { window.parent.postMessage({ type: 'typhon-report-close' }, '*'); return; } catch (e) {}
  }
  window.location.href = window.TYPHOON_HOME_URL || 'http://localhost:5173/';
});

// ── Commande vocale (dictée + réponse parlée en voix homme) ───────────────
btnVoice.addEventListener('click', () => {
  const w = window;
  const Recognition = w.SpeechRecognition || w.webkitSpeechRecognition;
  if (isListening && recognitionRef) { recognitionRef.stop(); return; }
  if (!Recognition) {
    addMessage('assistant', "La commande vocale n'est pas prise en charge par ce navigateur. Vous pouvez écrire votre question normalement.");
    return;
  }
  const recognition = new Recognition();
  recognition.lang = 'fr-FR';
  recognition.interimResults = false;
  recognition.continuous = false;
  recognition.onresult = (event) => {
    const transcript = event.results[0]?.[0]?.transcript || '';
    if (!transcript.trim()) return;
    window.voiceWanted = true; // réponse parlée (voix homme)
    input.value = transcript;
    btnSend.click();
  };
  recognition.onend = () => { isListening = false; btnVoice.classList.remove('is-listening'); };
  recognition.onerror = () => { isListening = false; btnVoice.classList.remove('is-listening'); };
  recognitionRef = recognition;
  isListening = true;
  btnVoice.classList.add('is-listening');
  recognition.start();
});

// ── Actions ───────────────────────────────────────────────────────────────
btnSend.addEventListener('click', () => { const q = input.value; input.value = ''; sendQuestion(q); });
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { const q = input.value; input.value = ''; sendQuestion(q); } });

// ── Démarrage : message d'accueil + chargement du visage ──────────────────
addMessage('assistant', welcome);
history.push({ role: 'assistant', content: welcome });

window.speechSynthesis?.getVoices?.();
window.speechSynthesis && (window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices());

// ── Scène 3D : visage humain local (facecap.glb) ──────────────────────────
function initAvatar() {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(avatarNode.clientWidth, avatarNode.clientHeight);
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  avatarNode.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, avatarNode.clientWidth / avatarNode.clientHeight, 0.1, 100);
  // Avatar humain COMPLET (Ready Player Me local, squelette Mixamo) :
  // le personnage entier est cadré au centre de la partie gauche.
  camera.position.set(0, 1.15, 2.7);
  camera.lookAt(0, 1.1, 0);

  // Lumières douces (visage)
  const hemi = new THREE.HemisphereLight(0xffffff, 0x666677, 1.4);
  scene.add(hemi);
  const dir = new THREE.DirectionalLight(0xffffff, 2.2);
  dir.position.set(1.2, 1.6, 1.6);
  scene.add(dir);
  const rim = new THREE.DirectionalLight(0x88aaff, 0.9);
  rim.position.set(-1.5, 0.6, -1.2);
  scene.add(rim);

  const clock = new THREE.Clock();

  // Animation (boucle) : AvatarTalkAnimator pilote la bouche (morphs ARKit),
  // les gestes des bras (clips Talking_*) et les clignements. On ajoute un
  // léger hochement de tête pendant la parole.
  function animate() {
    requestAnimationFrame(animate);
    const dt = clock.getDelta();
    if (talker) {
      talker.update(dt);
      if (talker.isTalking && headNode) {
        headNode.rotation.x = Math.sin(clock.elapsedTime * 6) * 0.05;
        headNode.rotation.z = Math.sin(clock.elapsedTime * 8) * 0.03;
      }
    }
    renderer.render(scene, camera);
  }

  // Les fichiers d'animation (animations.glb) sont compressés DRACO : on
  // branche le décodeur (copié dans public/draco/) pour pouvoir les lire.
  const loader = new GLTFLoader();
  const dracoLoader = new DRACOLoader();
  dracoLoader.setDecoderPath('/draco/');
  loader.setDRACOLoader(dracoLoader);
  loader.load('/models/typhon-report-avatar.glb', (gltf) => {
    const avatar = gltf.scene;
    scene.add(avatar);

    // AnimationMixer sur le squelette de l'avatar
    mixer = new THREE.AnimationMixer(avatar);

    // Nœud « head » pour le hochement
    headNode = avatar.getObjectByName('Head') || avatar.getObjectByName('Wolf3D_Head') || avatar;

    // L'animateur (bouche + bras + clignements) est créé quand les clips
    // d'animation sont disponibles (ils vivent dans un fichier séparé).
    loader.load('/models/typhon-report-animations.glb', (animationFile) => {
      const clips = animationFile.animations || [];
      talker = new AvatarTalkAnimator(mixer, avatar, clips);
      window.__typhonAvatarReady = true;
    }, undefined, (e) => console.warn('Animations indisponibles :', e));
  }, undefined, (e) => {
    console.error('Avatar 3D indisponible :', e);
    avatarError.hidden = false;
    avatarNode.style.display = 'none';
  });

  window.addEventListener('resize', () => {
    camera.aspect = avatarNode.clientWidth / avatarNode.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(avatarNode.clientWidth, avatarNode.clientHeight);
  });

  animate();
}

initAvatar();
