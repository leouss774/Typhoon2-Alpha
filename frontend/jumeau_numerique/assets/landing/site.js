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

  // ---- Fond décoratif : vagues SVG bleues plein écran, animées en continu
  // (morph du tracé) + léger parallax souris. Généré en JS pour rester
  // partagé entre index.html et solutions.html sans dupliquer le HTML.
  function initBgWaves() {
    const bands = [
      { cls: 'mk-wave-wrap-1', path: 'mk-wave-path-1', dur: '13s',
        d0: 'M0,120 C300,40 650,220 950,140 C1200,75 1450,180 1600,110 L1600,300 C1450,370 1200,270 950,330 C650,410 300,230 0,320 Z',
        d1: 'M0,150 C300,230 650,60 950,180 C1200,270 1450,110 1600,170 L1600,300 C1450,370 1200,270 950,330 C650,410 300,230 0,320 Z' },
      { cls: 'mk-wave-wrap-2', path: 'mk-wave-path-2', dur: '17s',
        d0: 'M0,420 C280,340 600,520 900,440 C1150,375 1400,480 1600,410 L1600,600 C1400,670 1150,570 900,630 C600,710 280,530 0,620 Z',
        d1: 'M0,450 C280,540 600,360 900,460 C1150,540 1400,400 1600,470 L1600,600 C1400,670 1150,570 900,630 C600,710 280,530 0,620 Z' },
      { cls: 'mk-wave-wrap-3', path: 'mk-wave-path-3', dur: '21s',
        d0: 'M0,700 C300,630 650,800 950,730 C1200,670 1450,770 1600,710 L1600,900 L0,900 Z',
        d1: 'M0,730 C300,790 650,650 950,720 C1200,770 1450,690 1600,740 L1600,900 L0,900 Z' }
    ];
    const wrap = document.createElement('div');
    wrap.id = 'mk-bg-fx';
    wrap.setAttribute('aria-hidden', 'true');
    wrap.innerHTML = bands.map(function (b) {
      var anim = reduceMotion ? '' :
        '<animate attributeName="d" dur="' + b.dur + '" repeatCount="indefinite" calcMode="spline" ' +
        'keySplines="0.45 0 0.55 1; 0.45 0 0.55 1" values="' + b.d0 + ';' + b.d1 + ';' + b.d0 + '"/>';
      return '<div class="mk-wave-wrap ' + b.cls + '"><svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice">' +
        '<path class="' + b.path + '" d="' + b.d0 + '">' + anim + '</path></svg></div>';
    }).join('');
    home.insertBefore(wrap, home.firstChild);
    if (reduceMotion) return; // formes visibles mais statiques, pas de parallax souris

    const waves = wrap.querySelectorAll('.mk-wave-wrap');
    let targetX = 0, targetY = 0, curX = 0, curY = 0;

    function onMove(e) {
      targetX = (e.clientX / window.innerWidth - 0.5) * 2;
      targetY = (e.clientY / window.innerHeight - 0.5) * 2;
    }
    window.addEventListener('mousemove', onMove, { passive: true });

    function raf() {
      curX += (targetX - curX) * 0.045;
      curY += (targetY - curY) * 0.045;
      waves.forEach((w, i) => {
        const depth = (i + 1) * 10;
        w.style.transform = 'translate(' + (curX * depth) + 'px,' + (curY * depth) + 'px)';
      });
      requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);
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
  initHeroIntro();
  initHeroVideo();
  initLazyVideos();
  initBgWaves();
  initHeroParallax();
})();
