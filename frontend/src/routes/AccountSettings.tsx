// =============================================================================
//   TYPHOON — /account & /settings : page « Paramètres du compte »
//   Page pleine intégrée à l'app (pas une modale) : la MÊME sidenav que /zone
//   (composant partagé ZoneSidenav → nav, historique, pied utilisateur, menu
//   réglages thème/accent) et le panneau SettingsPanel en corps de page.
//   Le thème et l'accent sont synchronisés entre les deux pages via
//   useTyphoonTheme (store localStorage partagé).
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import type { CSSProperties } from 'react';
import type { Menu } from '@material/web/menu/menu.js';
import type { MdSwitch } from '@material/web/switch/switch.js';
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
  const { theme, accent, toggleTheme, pickAccent, resetAccent } = useTyphoonTheme();
  const isMobile = useIsMobile();

  /* Rétractée par défaut ; le survol déplie temporairement, le toggle épingle. */
  const [navCollapsed, setNavCollapsed] = useState(true);
  const [navHovered, setNavHovered] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsMenuRef = useRef<Menu | null>(null);
  const themeSwitchRef = useRef<MdSwitch | null>(null);
  const sidenavRef = useRef<HTMLElement | null>(null);

  /* Même écouteurs que /zone : le menu réglages se referme tout seul et on
     resynchronise l'état React ; md-switch émet `change`. */
  useEffect(() => {
    const menu = settingsMenuRef.current;
    if (!menu) return;
    const onClosed = () => setSettingsOpen(false);
    menu.addEventListener('closed', onClosed);
    return () => menu.removeEventListener('closed', onClosed);
  }, []);

  useEffect(() => {
    const sw = themeSwitchRef.current;
    if (!sw) return;
    const onChange = () => toggleTheme();
    sw.addEventListener('change', onChange);
    return () => sw.removeEventListener('change', onChange);
  }, [toggleTheme]);

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
  const initialTab: SettingsTabKey = TAB_BY_PATH[tabKey] ?? 'account';

  return (
    <main
      className={`zone-app account-settings-page${theme === 'light' ? ' theme-light' : ''      }${navCollapsed && !navHovered && !isMobile ? ' nav-collapsed' : ''}${drawerOpen ? ' drawer-open' : ''}`}
      style={{ '--accent': accent } as CSSProperties}
    >
      {/* ===== SIDENAV — même composant que /zone ===== */}
      <ZoneSidenav
        sidenavRef={sidenavRef}
        collapsed={navCollapsed && !navHovered && !isMobile}
        mobile={isMobile}
        hidden={isMobile && !drawerOpen}
        theme={theme}
        accent={accent}
        settingsOpen={settingsOpen}
        settingsMenuRef={settingsMenuRef}
        themeSwitchRef={themeSwitchRef}
        onToggleCollapse={() =>
          isMobile ? setDrawerOpen(false) : setNavCollapsed((c) => !c)
        }
        onHoverChange={setNavHovered}
        onPickAccent={pickAccent}
        onResetAccent={resetAccent}
        onOpenSettings={() => setSettingsOpen((o) => !o)}
        onOpenAccount={() => {
          setDrawerOpen(false);
          setSettingsOpen(false);
          navigate('/settings/account');
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

          <SettingsPanel initialTab={initialTab} />
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
