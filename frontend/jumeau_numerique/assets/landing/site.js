/* ====================================================================
   Typhoon — comportements partagés de la vitrine (clair, premium/tech).
   100% vanilla (IntersectionObserver), aucune dépendance externe.
   Utilisé par index.html (#home-screen en overlay fixe, scroll interne)
   et solutions.html (#home-screen en flux normal, scroll fenêtre).
   ==================================================================== */
(function () {
  const home = document.getElementById('home-screen');
  if (!home) return;

  const isFixedScroller = getComputedStyle(home).position === 'fixed';
  const scrollerEl = isFixedScroller ? home : window;
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Connexion lente / économie de données : on n'auto-charge pas les vidéos,
  // le poster statique fait office de fallback (cf. #4 des consignes perf).
  const conn = navigator.connection || navigator.webkitConnection || navigator.mozConnection;
  const isSlowConnection = !!(conn && (conn.saveData || /2g/.test(conn.effectiveType || '')));

  // ---- Header : intensifie le fond au scroll ----
  function initHeaderScrollState() {
    const header = document.getElementById('home-header');
    if (!header) return;
    const getY = () => (isFixedScroller ? home.scrollTop : window.scrollY);
    const onScroll = () => header.classList.toggle('is-scrolled', getY() > 30);
    scrollerEl.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  // ---- Apparition au scroll (.reveal / .reveal-stagger, IntersectionObserver) ----
  function initReveal() {
    const targets = home.querySelectorAll('.reveal');
    if (!targets.length) return;
    if (!('IntersectionObserver' in window)) {
      targets.forEach((el) => el.classList.add('visible'));
      return;
    }
    const root = isFixedScroller ? home : null;
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          obs.unobserve(entry.target);
        }
      });
    }, { root, threshold: 0.15, rootMargin: '0px 0px -40px 0px' });
    targets.forEach((el) => obs.observe(el));
  }

  // ---- Entrée du hero (fade + slide-up au chargement, pas au scroll) ----
  function initHeroIntro() {
    const heroContent = document.getElementById('hero-content');
    if (!heroContent) return;
    requestAnimationFrame(() => requestAnimationFrame(() => heroContent.classList.add('hero-in')));
  }

  // ---- Vidéo de fond du hero : chargement direct (au-dessus de la ligne de flottaison) ----
  function initHeroVideo() {
    const video = document.getElementById('hero-video');
    if (!video) return;
    if (isSlowConnection || reduceMotion) return; // le poster (<img>) reste affiché, cf. HTML
    video.src = video.dataset.src;
    video.load();
    video.play().catch(() => {});
  }

  // ---- Vidéos hors premier écran : chargement paresseux via IntersectionObserver ----
  function initLazyVideos() {
    const videos = home.querySelectorAll('video.lazy-video');
    if (!videos.length) return;
    if (isSlowConnection) return; // les <img class="mode-poster-img"> associées restent visibles
    const root = isFixedScroller ? home : null;
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const v = entry.target;
        v.src = v.dataset.src;
        v.load();
        v.play().catch(() => {});
        v.classList.add('is-loaded');
        obs.unobserve(v);
      });
    }, { root, threshold: 0.1, rootMargin: '200px 0px' });
    videos.forEach((v) => obs.observe(v));
  }

  // ---- Fond de page : transition douce du blanc vers un gris-bleu léger
  // en descendant (pas de noir : reste dans la palette claire du site).
  // Invisible derrière le hero (vidéo) et les sections à fond opaque
  // (#home-ai, bandeau partenaires), visible entre les sections neutres.
  function initScrollBackground() {
    if (reduceMotion) return;
    const from = [255, 255, 255];
    const to = [227, 233, 237];
    let ticking = false;
    function update() {
      ticking = false;
      const scrollTop = isFixedScroller ? home.scrollTop : window.scrollY;
      const total = (isFixedScroller
        ? home.scrollHeight - home.clientHeight
        : document.documentElement.scrollHeight - window.innerHeight) || 1;
      const progress = Math.min(1, Math.max(0, scrollTop / (total * 0.45)));
      const r = Math.round(from[0] + (to[0] - from[0]) * progress);
      const g = Math.round(from[1] + (to[1] - from[1]) * progress);
      const b = Math.round(from[2] + (to[2] - from[2]) * progress);
      home.style.backgroundColor = 'rgb(' + r + ',' + g + ',' + b + ')';
    }
    scrollerEl.addEventListener('scroll', () => {
      if (!ticking) { requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    update();
  }

  // ---- Parallax léger sur la vidéo du hero (pur CSS var, pas de lib) ----
  function initHeroParallax() {
    if (reduceMotion) return;
    const hero = document.getElementById('home-hero');
    const wrap = document.getElementById('hero-video-wrap');
    if (!hero || !wrap) return;
    let ticking = false;
    function update() {
      ticking = false;
      const rect = hero.getBoundingClientRect();
      const progress = Math.min(1, Math.max(0, 1 - rect.bottom / (rect.height + window.innerHeight)));
      wrap.style.setProperty('--parallax-y', (progress * 60) + 'px');
    }
    scrollerEl.addEventListener('scroll', () => {
      if (!ticking) { requestAnimationFrame(update); ticking = true; }
    }, { passive: true });
    update();
  }

  // ---- Scroll doux natif vers les ancres internes (#nav, CTA) ----
  // scroll-behavior:smooth (CSS) fait le travail ; rien à faire ici tant
  // qu'aucune lib de scroll pilotée en JS n'est utilisée (cf. consigne :
  // pas de GSAP sauf nécessité réelle — un simple reveal n'en a pas besoin).

  initHeaderScrollState();
  initReveal();
  initHeroIntro();
  initHeroVideo();
  initLazyVideos();
  initHeroParallax();
  initScrollBackground();
})();
