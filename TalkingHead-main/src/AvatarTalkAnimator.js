import * as THREE from 'three';

// ---------------------------------------------------------------------------
// AvatarTalkAnimator.js
// Anime la bouche (morph targets ARKit) + les bras (clips Mixamo Talking_0/1/2)
// de façon fluide, synchronisée sur l'audio de la réponse du chatbot.
//
// Usage rapide :
//   const talker = new AvatarTalkAnimator(mixer, gltf.scene, animationsGltf.animations);
//   talker.startTalking(audioElement);   // audioElement = balise <audio> qui joue la voix
//   // dans la boucle de rendu :
//   talker.update(delta);
//   // quand la réponse audio est terminée :
//   talker.stopTalking();
// ---------------------------------------------------------------------------

export class AvatarTalkAnimator {
  constructor(mixer, sceneRoot, animationClips, options = {}) {
    this.mixer = mixer;

    // ---- 1. Trouver TOUS les meshes qui portent les morph targets ARKit ----
    // (les avatars Ready Player Me répartissent les morphs sur EyeLeft/EyeRight,
    // Wolf3D_Head et Wolf3D_Teeth : on les pilote tous pour un rendu cohérent)
    this.morphMeshes = [];
    sceneRoot.traverse((obj) => {
      if (obj.isMesh && obj.morphTargetDictionary && obj.morphTargetDictionary.jawOpen !== undefined) {
        this.morphMeshes.push(obj);
      }
    });
    if (!this.morphMeshes.length) {
      console.warn('AvatarTalkAnimator: aucun mesh avec morph targets ARKit trouvé.');
    }

    // valeurs cibles vs valeurs actuelles -> pour un lerp doux à chaque frame
    this.targetMouth = { jawOpen: 0, mouthFunnel: 0, mouthClose: 0 };
    this.currentMouth = { jawOpen: 0, mouthFunnel: 0, mouthClose: 0 };

    // clignement des yeux
    this.blinkTimer = 0;
    this.nextBlinkAt = this._randomBlinkDelay();
    this.blinkProgress = -1; // -1 = pas en train de cligner

    // ---- 2. Préparer les clips d'animation ----
    this.actions = {};
    animationClips.forEach((clip) => {
      this.actions[clip.name] = this.mixer.clipAction(clip);
    });

    this.idleName = options.idleName || this._findClipName(/idle/i);
    this.talkNames = options.talkNames || Object.keys(this.actions).filter((n) => /talking/i.test(n));

    this.currentAction = this.actions[this.idleName];
    if (this.currentAction) {
      this.currentAction.reset().play();
    }

    this.isTalking = false;
    this.gestureBlendTime = options.gestureBlendTime ?? 0.5; // secondes, transition douce
    this.timeUntilNextGesture = 0;
    this._currentGestureName = null;

    // ---- 3. Analyse audio (pour synchro bouche réaliste) ----
    this.audioCtx = null;
    this.analyser = null;
    this.freqData = null;
    this.audioSource = null;
    this.fallbackPhase = 0; // utilisé si pas d'audio fourni
  }

  _findClipName(regex) {
    return Object.keys(this.actions).find((n) => regex.test(n));
  }

  _randomBlinkDelay() {
    return 2 + Math.random() * 3; // un clignement toutes les 2-5s
  }

  // Branche l'analyseur audio sur l'élément <audio> qui joue la voix du chatbot
  _attachAudio(audioElement) {
    if (!audioElement) return;
    if (!this.audioCtx) {
      this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (this.audioSource) {
      try { this.audioSource.disconnect(); } catch (e) {}
    }
    this.audioSource = this.audioCtx.createMediaElementSource(audioElement);
    this.analyser = this.audioCtx.createAnalyser();
    this.analyser.fftSize = 256;
    this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
    this.audioSource.connect(this.analyser);
    this.analyser.connect(this.audioCtx.destination);
  }

  startTalking(audioElement = null) {
    this.isTalking = true;
    if (audioElement) this._attachAudio(audioElement);
    this._playNextGesture();
  }

  stopTalking() {
    this.isTalking = false;
    this.targetMouth.jawOpen = 0;
    this.targetMouth.mouthFunnel = 0;
    this.targetMouth.mouthClose = 0.15; // légère fermeture, plus naturel qu'un 0 sec
    this._crossFadeTo(this.idleName, this.gestureBlendTime);
  }

  // Choisit un geste (bras) différent du précédent et fait un fondu doux
  _playNextGesture() {
    if (!this.talkNames.length) return;
    let name = this.talkNames[Math.floor(Math.random() * this.talkNames.length)];
    if (this.talkNames.length > 1 && name === this._currentGestureName) {
      name = this.talkNames[(this.talkNames.indexOf(name) + 1) % this.talkNames.length];
    }
    this._currentGestureName = name;
    this._crossFadeTo(name, this.gestureBlendTime, true);

    const action = this.actions[name];
    const duration = action ? action.getClip().duration : 2;
    // légère variation de vitesse pour que ça ne semble pas robotique/répétitif
    if (action) action.setEffectiveTimeScale(0.92 + Math.random() * 0.16);
    this.timeUntilNextGesture = duration - this.gestureBlendTime * 0.5;
  }

  _crossFadeTo(name, duration, loopOnce = false) {
    const next = this.actions[name];
    if (!next || next === this.currentAction) return;
    next.reset();
    next.setLoop(loopOnce ? THREE.LoopOnce : THREE.LoopRepeat, loopOnce ? 1 : Infinity);
    next.clampWhenFinished = loopOnce;
    next.enabled = true;
    next.play();
    if (this.currentAction) {
      this.currentAction.crossFadeTo(next, duration, true);
    } else {
      next.fadeIn(duration);
    }
    this.currentAction = next;
  }

  // Applique un morph sur tous les meshes qui le possèdent
  _setMorph(name, value) {
    const v = Math.max(0, Math.min(1, value));
    this.morphMeshes.forEach((mesh) => {
      const i = mesh.morphTargetDictionary[name];
      if (i !== undefined && mesh.morphTargetInfluences) {
        mesh.morphTargetInfluences[i] = v;
      }
    });
  }

  // Calcule une "intensité de parole" à partir du spectre audio (0-1)
  _getAudioAmplitude() {
    if (this.analyser && this.freqData) {
      this.analyser.getByteFrequencyData(this.freqData);
      // bande basse/médium = correspond grossièrement à l'énergie vocale
      let sum = 0;
      const bandEnd = Math.floor(this.freqData.length * 0.5);
      for (let i = 0; i < bandEnd; i++) sum += this.freqData[i];
      const avg = sum / bandEnd / 255;
      return Math.min(1, avg * 1.6);
    }
    // Pas d'audio branché -> mouvement procédural crédible (sinusoïde + bruit)
    this.fallbackPhase += 0.18;
    const wave = (Math.sin(this.fallbackPhase) + 1) / 2;
    const jitter = Math.random() * 0.15;
    return Math.min(1, wave * 0.7 + jitter);
  }

  update(delta) {
    this.mixer.update(delta);

    // ---- Bouche ----
    if (this.morphMeshes.length) {
      if (this.isTalking) {
        const amp = this._getAudioAmplitude();
        this.targetMouth.jawOpen = amp * 0.7;
        this.targetMouth.mouthFunnel = Math.max(0, amp - 0.4) * 0.5;
        this.targetMouth.mouthClose = 0;
      }
      // lerp doux vers la cible (vitesse ~ 12/s) -> évite les saccades
      const lerpSpeed = 12;
      for (const key of Object.keys(this.targetMouth)) {
        this.currentMouth[key] += (this.targetMouth[key] - this.currentMouth[key]) * Math.min(1, lerpSpeed * delta);
        this._setMorph(key, this.currentMouth[key]);
      }

      // ---- Clignement des yeux ----
      this.blinkTimer += delta;
      if (this.blinkProgress < 0 && this.blinkTimer >= this.nextBlinkAt) {
        this.blinkProgress = 0;
      }
      if (this.blinkProgress >= 0) {
        this.blinkProgress += delta / 0.12; // clignement rapide (~120ms)
        const v = this.blinkProgress <= 1
          ? Math.sin(this.blinkProgress * Math.PI)
          : 0;
        this._setMorph('eyeBlinkLeft', v);
        this._setMorph('eyeBlinkRight', v);
        if (this.blinkProgress > 1) {
          this.blinkProgress = -1;
          this.blinkTimer = 0;
          this.nextBlinkAt = this._randomBlinkDelay();
        }
      }
    }

    // ---- Bras : enchaîner les gestes de parole tant qu'on parle ----
    if (this.isTalking) {
      this.timeUntilNextGesture -= delta;
      if (this.timeUntilNextGesture <= 0) {
        this._playNextGesture();
      }
    }
  }
}
