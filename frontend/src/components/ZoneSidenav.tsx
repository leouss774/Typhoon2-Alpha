// =============================================================================
//   TYPHOON — Sidenav rétractable partagée (/zone & /account|/settings)
//   Navigation façon Gemini : Desktop rail pleine largeur ↔ colonne d'icônes
//   (collapsed) · Mobile drawer hors-écran + scrim. Le pied d'écran porte
//   l'utilisateur (MOCK_USER) et le menu réglages (thème sombre, accent,
//   compte) — tout est synchronisé entre les deux pages via le même store
//   useTyphoonTheme (localStorage).
// =============================================================================

import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { CSSProperties, RefObject } from 'react';
import type { Menu } from '@material/web/menu/menu.js';
import type { MdSwitch } from '@material/web/switch/switch.js';
import { MOCK_USER } from './mockUser';
import { ACCENTS } from '../typhoon/useTyphoonTheme';
import type { Conversation } from '../zone/conversations';

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
  accent: string;
  settingsOpen: boolean;
  settingsMenuRef: RefObject<Menu | null>;
  themeSwitchRef: RefObject<MdSwitch | null>;
  onToggleCollapse: () => void;
  onPickAccent: (hex: string) => void;
  onResetAccent: () => void;
  onOpenSettings: () => void;
  onOpenAccount: () => void;
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
  accent,
  settingsOpen,
  settingsMenuRef,
  themeSwitchRef,
  onToggleCollapse,
  onPickAccent,
  onResetAccent,
  onOpenSettings,
  onOpenAccount,
  onCloseDrawer,
  onNewDiagnostic,
  conversations,
  activeAddress,
  onOpenConversation,
  onDeleteConversation,
}: ZoneSidenavProps) {
  const navigate = useNavigate();

  const navGo = (path: string) => {
    onCloseDrawer();
    navigate(path);
  };

  return (
    <aside
      ref={sidenavRef}
      className="zone-sidenav"
      aria-label="Navigation principale"
      inert={hidden}
      aria-hidden={hidden}
    >
      <header className="sidenav-header">
        {collapsed ? (
          /* Replié : l'icône d'expansion remplace le logo (clic → déplier) */
          <md-icon-button
            className="sidenav-expand"
            aria-label="Déplier le menu"
            title="Déplier le menu"
            onClick={onToggleCollapse}
          >
            <md-icon>chevron_right</md-icon>
          </md-icon-button>
        ) : (
          <>
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
            <md-icon-button
              className="sidenav-collapse"
              aria-label={mobile ? 'Fermer le menu' : 'Replier le menu'}
              title={mobile ? 'Fermer le menu' : 'Replier le menu'}
              onClick={onToggleCollapse}
            >
              <md-icon>{mobile ? 'close' : 'menu_open'}</md-icon>
            </md-icon-button>
          </>
        )}
      </header>

      {collapsed ? (
        /* ── Mode replié : colonne d'icônes ── */
        <nav className="sidenav-rail" aria-label="Raccourcis">
          <md-icon-button title="Nouveau diagnostic" aria-label="Nouveau diagnostic" onClick={onNewDiagnostic}>
            <md-icon>add_circle</md-icon>
          </md-icon-button>
          <md-icon-button title="Accueil" aria-label="Accueil" onClick={() => navGo('/')}>
            <md-icon>home</md-icon>
          </md-icon-button>
          <md-icon-button title="FAQ" aria-label="FAQ" onClick={() => navGo('/faq')}>
            <md-icon>help</md-icon>
          </md-icon-button>
          <md-icon-button title="Contact" aria-label="Contact" onClick={() => navGo('/contact')}>
            <md-icon>mail</md-icon>
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
            <md-list-item type="button" onClick={() => navGo('/')}>
              <md-icon slot="start">home</md-icon>
              <span slot="headline">Accueil</span>
            </md-list-item>
            <md-list-item type="button" onClick={() => navGo('/faq')}>
              <md-icon slot="start">help</md-icon>
              <span slot="headline">FAQ</span>
            </md-list-item>
            <md-list-item type="button" onClick={() => navGo('/contact')}>
              <md-icon slot="start">mail</md-icon>
              <span slot="headline">Contact</span>
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
        <button
          type="button"
          className="sidenav-user"
          title={`Compte : ${MOCK_USER.name} (${MOCK_USER.email})`}
          aria-label={`Ouvrir les paramètres du compte (${MOCK_USER.name})`}
          onClick={onOpenAccount}
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
          id="settings-anchor"
          className="sidenav-settings"
          aria-label="Réglages"
          title="Réglages"
          aria-expanded={settingsOpen}
          aria-haspopup="menu"
          onClick={onOpenSettings}
        >
          <md-icon>settings</md-icon>
        </md-icon-button>

        <md-menu
          ref={settingsMenuRef}
          anchor="settings-anchor"
          positioning="popover"
          open={settingsOpen}
          className="sidenav-menu"
        >
          <md-menu-item keepOpen>
            <span slot="headline">Mode sombre</span>
            <md-switch slot="end" ref={themeSwitchRef} selected={theme === 'dark'} icons>
              <md-icon slot="on-icon">dark_mode</md-icon>
              <md-icon slot="off-icon">light_mode</md-icon>
            </md-switch>
          </md-menu-item>

          <div className="sidenav-accent-block">
            <span className="sidenav-accent-title">Couleur d'accent</span>
            <div className="sidenav-accent-swatches">
              {ACCENTS.map((hex) => (
                <button
                  key={hex}
                  type="button"
                  className={`sidenav-accent-swatch${
                    accent.toLowerCase() === hex.toLowerCase() ? ' active' : ''
                  }`}
                  style={{ '--swatch': hex } as CSSProperties}
                  aria-label={`Accent ${hex}`}
                  title={hex}
                  onClick={() => onPickAccent(hex)}
                />
              ))}
            </div>
            <button type="button" className="sidenav-accent-reset" onClick={onResetAccent}>
              <md-icon>restart_alt</md-icon>
              <span>Rétablir le bleu d'origine</span>
            </button>
          </div>

          <md-menu-item type="button" onClick={onOpenAccount}>
            <md-icon slot="start">account_circle</md-icon>
            <span slot="headline">Compte et paramètres</span>
          </md-menu-item>

          <md-menu-item type="button" onClick={() => navGo('/')}>
            <md-icon slot="start">home</md-icon>
            <span slot="headline">Retour à l'accueil</span>
          </md-menu-item>
        </md-menu>
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
