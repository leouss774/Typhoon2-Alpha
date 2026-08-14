// =============================================================================
//   TYPHOON — /account & /settings : page « Paramètres du compte »
//   Page pleine intégrée à l'app (pas une modale) : la MÊME sidenav que /zone
//   (composant partagé ZoneSidenav → nav, historique, pied utilisateur,
//   engrenage « compte ») et le panneau SettingsPanel en corps de page.
//   Le thème et l'accent sont synchronisés entre les deux pages via
//   useTyphoonTheme (store localStorage partagé).
// =============================================================================

import { useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { CSSProperties } from 'react';
import { ZoneSidenav, useIsMobile } from '../components/ZoneSidenav';
import { SettingsPanel, type SettingsTabKey } from '../components/SettingsPanel';
import { useTyphoonTheme } from '../typhoon/useTyphoonTheme';
import {
  loadConversations,
  removeConversation,
  saveConversations,
  type Conversation,
} from '../zone/conversations';
import { removeCachedDiagnostic } from '../zone/diagnosticCache';
import '../styles/zone.css';

/* /settings/<onglet> → ouvre directement l'onglet (Compte, Sécurité,
   Abonnement & Facturation, Notifications, Connexions). */
const TAB_BY_PATH: Record<string, SettingsTabKey> = {
  '': 'account',
  account: 'account',
  security: 'security',
  billing: 'billing',
  notifications: 'notifications',
  connections: 'connections',
};

export function AccountSettings() {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, accent, mode, setThemeMode } = useTyphoonTheme();
  const isMobile = useIsMobile();

  const [navCollapsed, setNavCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const sidenavRef = useRef<HTMLElement | null>(null);

  /* Historique « Récent » partagé (localStorage) — mêmes données que /zone. */
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations());

  const handleDeleteConversation = (id: string) => {
    setConversations((prev) => {
      const victim = prev.find((c) => c.id === id);
      const next = removeConversation(prev, id);
      saveConversations(next);
      if (victim) removeCachedDiagnostic(victim.address);
      return next;
    });
  };

  const tabKey = location.pathname.split('/').filter(Boolean).pop() ?? '';
  const activeTab: SettingsTabKey = TAB_BY_PATH[tabKey] ?? 'account';

  return (
    <main
      className={`zone-app account-settings-page${theme === 'light' ? ' theme-light' : ''}${
        navCollapsed && !isMobile ? ' nav-collapsed' : ''
      }${drawerOpen ? ' drawer-open' : ''}`}
      style={{ '--accent': accent } as CSSProperties}
    >
      {/* ===== SIDENAV — même composant que /zone ===== */}
      <ZoneSidenav
        sidenavRef={sidenavRef}
        collapsed={navCollapsed && !isMobile}
        mobile={isMobile}
        hidden={isMobile && !drawerOpen}
        theme={theme}
        mode={mode}
        onThemeModeChange={setThemeMode}
        onToggleCollapse={() =>
          isMobile ? setDrawerOpen(false) : setNavCollapsed((c) => !c)
        }
        onOpenAccount={() => {
          setDrawerOpen(false);
          navigate('/settings/account');
        }}
        onNavigateSettings={(tab) => {
          setDrawerOpen(false);
          navigate(`/settings/${tab}`);
        }}
        onSignOut={() => {
          setDrawerOpen(false);
          navigate('/');
        }}
        onCloseDrawer={() => setDrawerOpen(false)}
        onNewDiagnostic={() => {
          setDrawerOpen(false);
          navigate('/zone');
        }}
        conversations={conversations}
        activeAddress={null}
        onOpenConversation={(address) => {
          setDrawerOpen(false);
          navigate(`/zone?q=${encodeURIComponent(address)}`);
        }}
        onDeleteConversation={handleDeleteConversation}
      />

      {/* ===== COLONNE PRINCIPALE : en-tête + corps de page ===== */}
      <div className="zone-main">
        <div className="account-settings-scroll">
          <header className="account-settings-header">
            {/* Hamburger mobile — même classe que le stepper de /zone */}
            <md-icon-button
              className="sidenav-hamburger account-settings-hamburger"
              aria-label="Ouvrir le menu"
              onClick={() => setDrawerOpen(true)}
            >
              <md-icon>menu</md-icon>
            </md-icon-button>
            <div className="account-settings-title">
              <h1>Paramètres du compte</h1>
              <p>
                Gérez votre profil, la sécurité, l’abonnement et les
                préférences de notification. Données de démonstration —
                aucune information réelle.
              </p>
            </div>
            <md-filled-button onClick={() => navigate('/zone')}>
              <md-icon slot="icon">science</md-icon>
              Nouveau diagnostic
            </md-filled-button>
          </header>

          <SettingsPanel tab={activeTab} onTabChange={(key) => navigate(`/settings/${key}`)} />
        </div>
      </div>

      {/* Scrim du drawer mobile */}
      <div
        className={`zone-scrim${drawerOpen ? ' visible' : ''}`}
        aria-hidden="true"
        onClick={() => setDrawerOpen(false)}
      />
    </main>
  );
}
