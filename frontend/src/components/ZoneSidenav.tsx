// =============================================================================
//   TYPHOON — Sidenav rétractable partagée (/zone & /account|/settings)
//   Navigation façon Gemini : Desktop rail pleine largeur ↔ colonne d'icônes
//   (collapsed) · Mobile drawer hors-écran + scrim. Le pied d'écran porte
//   l'utilisateur (MOCK_USER) et l'engrenage « compte » : les deux mènent à
//   /settings (onglet Compte).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { RefObject } from 'react';
import { MOCK_USER } from './mockUser';
import type { Conversation } from '../zone/conversations';
import type { ThemeMode } from '../typhoon/useTyphoonTheme';

/* ── Menu utilisateur : onglets navigables du panneau Paramètres + déconnexion ── */
const USER_MENU_ITEMS: Array<{ tab: string; label: string; icon: string }> = [
  { tab: 'account', label: 'Mon profil', icon: 'account_circle' },
  { tab: 'security', label: 'Sécurité', icon: 'lock' },
  { tab: 'billing', label: 'Abonnement & Facturation', icon: 'credit_card' },
  { tab: 'notifications', label: 'Notifications', icon: 'notifications' },
  { tab: 'connections', label: 'Connexions', icon: 'link' },
];

/* ── Menu thème : les trois modes proposés (Clair / Sombre / Système) ── */
const THEME_MODES: Array<{ mode: ThemeMode; label: string; icon: string }> = [
  { mode: 'light', label: 'Clair', icon: 'light_mode' },
  { mode: 'dark', label: 'Sombre', icon: 'dark_mode' },
  { mode: 'system', label: 'Système', icon: 'brightness_auto' },
];

/* ── Détection mobile — 900px, même breakpoint que @media (max-width:900px)
   dans zone.css (garder les deux synchronisés) ── */
export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches
  );
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 900px)');
    const onChange = () => setIsMobile(mq.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isMobile;
}

export type ZoneSidenavProps = {
  sidenavRef: RefObject<HTMLElement | null>;
  collapsed: boolean;
  mobile: boolean;
  hidden: boolean;
  theme: 'dark' | 'light';
  mode: ThemeMode;
  onThemeModeChange: (mode: ThemeMode) => void;
  onToggleCollapse: () => void;
  onOpenAccount: () => void;
  /** Navigation vers un onglet des paramètres (/settings/<tab>). */
  onNavigateSettings: (tab: string) => void;
  /** Déconnexion (retour à l'accueil). */
  onSignOut: () => void;
  onCloseDrawer: () => void;
  onNewDiagnostic: () => void;
  conversations: Conversation[];
  activeAddress: string | null;
  onOpenConversation: (address: string) => void;
  onDeleteConversation: (id: string) => void;
};

/* ── Sidenav rétractable (navigation façon Gemini) ──
   Desktop : rail pleine largeur ↔ colonne d'icônes (collapsed).
   Mobile  : drawer hors-écran ouvert via le hamburger + scrim. */
export function ZoneSidenav({
  sidenavRef,
  collapsed,
  mobile,
  hidden,
  theme,
  mode,
  onThemeModeChange,
  onToggleCollapse,
  onOpenAccount,
  onNavigateSettings,
  onSignOut,
  onCloseDrawer,
  onNewDiagnostic,
  conversations,
  activeAddress,
  onOpenConversation,
  onDeleteConversation,
}: ZoneSidenavProps) {
  /* Survol (desktop, replié) : dépliage temporaire « peek » — la sidenav
     n'est dépliée durablement que si elle est épinglée (toggle) ; sinon elle
     se déplie tant que la souris reste dessus puis se replie au départ. */
  const [peek, setPeek] = useState(false);
  const canPeek = !mobile && collapsed;
  const peekActive = canPeek && peek;
  const effectiveCollapsed = collapsed && !peekActive;
  /* Déplié durablement (épinglé) : l'aside reste ouverte après un clic,
     par opposition au « peek » temporaire au survol. */
  const pinned = !mobile && !collapsed;

  /* ── Menu utilisateur (dropdown du pied de sidenav) ── */
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userBtnRef = useRef<HTMLButtonElement | null>(null);
  const userMenuRef = useRef<HTMLDivElement | null>(null);

  /* ── Menu thème (Clair / Sombre / Système) ── */
  const [themeMenuOpen, setThemeMenuOpen] = useState(false);
  const themeBtnRef = useRef<HTMLButtonElement | null>(null);
  const themeMenuRef = useRef<HTMLDivElement | null>(null);

  /* Clic extérieur + Échap ferment le menu ; repli de la sidenav aussi. */
  useEffect(() => {
    if (!userMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (userMenuRef.current?.contains(t)) return;
      if (userBtnRef.current?.contains(t)) return;
      setUserMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [userMenuOpen]);

  useEffect(() => {
    setUserMenuOpen(false);
  }, [effectiveCollapsed]);

  /* Clic extérieur + Échap ferment le menu thème ; repli de la sidenav aussi. */
  useEffect(() => {
    if (!themeMenuOpen) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (themeMenuRef.current?.contains(t)) return;
      if (themeBtnRef.current?.contains(t)) return;
      setThemeMenuOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setThemeMenuOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [themeMenuOpen]);

  useEffect(() => {
    setThemeMenuOpen(false);
  }, [effectiveCollapsed]);

  return (
    <aside
      ref={sidenavRef}
      className={`zone-sidenav${canPeek && peek ? ' sidenav-peek' : ''}`}
      aria-label="Navigation principale"
      inert={hidden}
      aria-hidden={hidden}
      onMouseEnter={() => {
        if (canPeek) setPeek(true);
      }}
      onMouseLeave={() => {
        if (canPeek) setPeek(false);
      }}
    >
      <header className="sidenav-header">
        <Link
          to="/"
          className="sidenav-brand"
          aria-label="Typhoon — accueil"
          onClick={onCloseDrawer}
        >
          {/* Wordmark teinté par l'accent : le SVG blanc sert de masque
              alpha, la couleur est --accent (voir zone.css). Le lien a déjà
              aria-label — le span est décoratif. */}
          <span className="sidenav-wordmark-img" aria-hidden="true" />
        </Link>
        {/* Toggle à 3 états (desktop) :
            1. Repliée → hamburger (clic = déplier) ;
            2. Survol « peek » → menu_open creuse (clic = épingler, l'aside
               reste alors dépliée) ;
            3. Épinglée → menu_open pleine/adherente, l'aside demeure dépliée. */}
        <md-icon-button
          className={`sidenav-toggle${pinned ? ' sidenav-toggle--pinned' : ''}${peekActive ? ' sidenav-toggle--peek' : ''}`}
          aria-label={
            mobile
              ? 'Fermer le menu'
              : effectiveCollapsed
                ? 'Déplier le menu'
                : peekActive
                  ? 'Épingler la navigation'
                  : 'Replier le menu'
          }
          title={
            mobile
              ? 'Fermer le menu'
              : effectiveCollapsed
                ? 'Déplier le menu'
                : peekActive
                  ? 'Épingler la navigation'
                  : 'Replier le menu'
          }
          onClick={onToggleCollapse}
        >
          <md-icon>
            {mobile ? 'close' : effectiveCollapsed ? 'menu' : 'menu_open'}
          </md-icon>
        </md-icon-button>
      </header>

      {effectiveCollapsed ? (
        /* ── Mode replié : colonne d'icônes ── */
        <nav className="sidenav-rail" aria-label="Raccourcis">
          <md-icon-button title="Nouveau diagnostic" aria-label="Nouveau diagnostic" onClick={onNewDiagnostic}>
            <md-icon>add_circle</md-icon>
          </md-icon-button>
        </nav>
      ) : (
        /* ── Mode déplié : liste M3 + historique « Récent » ── */
        <div className="sidenav-body">
          <md-list className="sidenav-nav">
            <md-list-item
              className="sidenav-new"
              type="button"
              onClick={onNewDiagnostic}
            >
              <md-icon slot="start">add_circle</md-icon>
              <span slot="headline">Nouveau diagnostic</span>
            </md-list-item>
          </md-list>

          <ConversationHistory
            conversations={conversations}
            activeAddress={activeAddress}
            onOpen={onOpenConversation}
            onDelete={onDeleteConversation}
          />
        </div>
      )}

      <footer className="sidenav-footer">
        {/* Rangée du haut : sélecteur de thème (Clair / Sombre / Système) —
            bouton avec libellé quand la sidenav est dépliée, icône seule dans
            le rail. Le libellé reflète le thème effectif. */}
        <div className="sidenav-footer-top">
          <div className="sidenav-theme">
            <button
              type="button"
              className="sidenav-theme-btn"
              ref={themeBtnRef}
              aria-label="Changer de thème"
              title="Changer de thème"
              aria-haspopup="menu"
              aria-expanded={themeMenuOpen}
              onClick={() => setThemeMenuOpen((o) => !o)}
            >
              <md-icon>{theme === 'dark' ? 'dark_mode' : 'light_mode'}</md-icon>
              <span className="sidenav-theme-label">
                {theme === 'dark' ? 'Sombre' : 'Clair'}
              </span>
            </button>

            {themeMenuOpen && (
              <div
                className="sidenav-theme-menu"
                ref={themeMenuRef}
                role="menu"
                aria-label="Choix du thème"
              >
                {THEME_MODES.map((item) => (
                  <button
                    key={item.mode}
                    type="button"
                    role="menuitemradio"
                    aria-checked={mode === item.mode}
                    className={`sidenav-theme-menu-item${mode === item.mode ? ' active' : ''}`}
                    onClick={() => {
                      setThemeMenuOpen(false);
                      onThemeModeChange(item.mode);
                    }}
                  >
                    <md-icon>{item.icon}</md-icon>
                    <span>{item.label}</span>
                    {mode === item.mode && (
                      <md-icon className="sidenav-theme-menu-check">check</md-icon>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        {/* Rangée du bas : utilisateur + réglages (compte) */}
        <div className="sidenav-footer-main">
          <button
            type="button"
            className="sidenav-user"
            ref={userBtnRef}
            title={`Compte : ${MOCK_USER.name} (${MOCK_USER.email})`}
            aria-label={`Ouvrir le menu utilisateur (${MOCK_USER.name})`}
            aria-haspopup="menu"
            aria-expanded={userMenuOpen}
            onClick={() => setUserMenuOpen((o) => !o)}
          >
            <span className="sidenav-user-avatar" aria-hidden="true">
              {MOCK_USER.initials}
            </span>
            <span className="sidenav-user-info">
              <span className="sidenav-user-name">{MOCK_USER.name}</span>
              <span className="sidenav-user-tier">{MOCK_USER.tier}</span>
            </span>
          </button>
          <md-icon-button
            className="sidenav-settings"
            aria-label="Compte et paramètres"
            title="Compte et paramètres"
            onClick={onOpenAccount}
          >
            <md-icon>settings</md-icon>
          </md-icon-button>
        </div>

        {/* ── Menu utilisateur (dropdown, au-dessus du pied) ── */}
        {userMenuOpen && (
          <div
            className="sidenav-user-menu"
            ref={userMenuRef}
            role="menu"
            aria-label="Menu utilisateur"
          >
          <div className="sidenav-user-menu-head">
            <span className="sidenav-user-avatar" aria-hidden="true">
              {MOCK_USER.initials}
            </span>
            <span className="sidenav-user-menu-copy">
              <span className="sidenav-user-menu-name">{MOCK_USER.name}</span>
              <span className="sidenav-user-menu-tier">
                {MOCK_USER.tier} · {MOCK_USER.organization}
              </span>
            </span>
          </div>

          {USER_MENU_ITEMS.map((item) => (
            <button
              key={item.tab}
              type="button"
              role="menuitem"
              className="sidenav-user-menu-item"
              onClick={() => {
                setUserMenuOpen(false);
                onNavigateSettings(item.tab);
              }}
            >
              <md-icon>{item.icon}</md-icon>
              <span>{item.label}</span>
            </button>
          ))}

          <div className="sidenav-user-menu-divider" role="separator" />

          <button
            type="button"
            role="menuitem"
            className="sidenav-user-menu-item sidenav-user-menu-item--danger"
            onClick={() => {
              setUserMenuOpen(false);
              onSignOut();
            }}
          >
            <md-icon>logout</md-icon>
            <span>Se déconnecter</span>
          </button>
        </div>
        )}
      </footer>
    </aside>
  );
}

/* ── Historique « Récent » de la sidenav (façon Gemini) ──
   Section repliable : liste des adresses diagnostiquées (localStorage),
   clic → relance le diagnostic, survol → bouton de suppression. */
export function ConversationHistory({
  conversations,
  activeAddress,
  onOpen,
  onDelete,
}: {
  conversations: Conversation[];
  activeAddress: string | null;
  onOpen: (address: string) => void;
  onDelete: (id: string) => void;
}) {
  const [open, setOpen] = useState(true);

  if (conversations.length === 0) {
    return (
      <div className="sidenav-recent-empty">
        <md-icon>history</md-icon>
        <span>Pas encore de diagnostic</span>
      </div>
    );
  }

  return (
    <details
      className="sidenav-recent"
      open={open}
      onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="sidenav-recent-header" aria-label="Historique des adresses diagnostiquées">
        <span className="sidenav-recent-title">Récent</span>
        <md-icon>expand_more</md-icon>
      </summary>
      <div className="sidenav-recent-list">
        {conversations.map((c) => {
          const active = activeAddress !== null && c.address === activeAddress;
          return (
            <div
              className={`sidenav-recent-item${active ? ' active' : ''}`}
              key={c.id}
            >
              <button
                type="button"
                className="sidenav-recent-btn"
                title={c.address}
                onClick={() => onOpen(c.address)}
              >
                <md-icon>history</md-icon>
                <span className="sidenav-recent-label">{c.address}</span>
              </button>
              <md-icon-button
                className="sidenav-recent-del"
                aria-label={`Supprimer ${c.address} de l'historique`}
                title="Supprimer de l'historique"
                onClick={() => onDelete(c.id)}
              >
                <md-icon>close</md-icon>
              </md-icon-button>
            </div>
          );
        })}
      </div>
    </details>
  );
}
