import { Navigate, Route, Routes } from 'react-router-dom';
import { Home } from './routes/Home';
import { Zone } from './routes/Zone';
import { JumeauNumerique } from './routes/JumeauNumerique';
import { Faq } from './routes/Faq';
import { Contact } from './routes/Contact';
<<<<<<< HEAD
import Economie from './routes/Economie';

const nav = [
  { to: '/', label: 'Accueil' },
  { to: '/zone', label: 'Zone' },
  { to: '/jumeau', label: 'Jumeau 3D' },
  { to: '/promoteurs', label: 'Promoteurs' },
  { to: '/artisans', label: 'Artisans' },
  { to: '/economie', label: 'Économie' },
  { to: '/property-id', label: 'Property ID' },
  { to: '/site', label: 'Site' },
];

function TopNav() {
  const location = useLocation();
  return (
    <header className="app-shell">
      <div className="brand">
        <div className="mark">T</div>
        <div>
          <div className="brand-name">Typhoon</div>
          <div className="brand-tag">Material Web React</div>
        </div>
      </div>
      <nav className="nav">
        {nav.map((item) => (
          <Link key={item.to} to={item.to} className={location.pathname === item.to ? 'active' : ''}>
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}

=======
import { AccountSettings } from './routes/AccountSettings';
import { AssistantProvider } from './assistant/AssistantContext';
import { TyphoonMascot } from './assistant/TyphoonMascot';

/**
 * Application Typhoon — toutes les pages sont autonomes (plein écran) :
 *   /                  → landing page
 *   /zone              → diagnostic géo-risque (stepper + carte + jumeau BIM)
 *   /jumeau            → viewer 3D
 *   /faq, /contact     → pages typhoon
 *   /account, /settings → page « Paramètres du compte » (même chrome que /zone)
 */
>>>>>>> origin/develop
export default function App() {
  return (
    <AssistantProvider>
      <Routes>
        <Route path="/" element={<Home />} />
<<<<<<< HEAD
        <Route path="/zone" element={<Zone />} />
        <Route path="/jumeau" element={<JumeauNumerique />} />
        <Route path="/promoteurs" element={<Promoteurs />} />
        <Route path="/artisans" element={<Artisans />} />
        <Route path="/economie" element={<Economie />} />
        <Route path="/property-id" element={<PropertyId />} />
        <Route path="/site" element={<Site />} />
=======
        <Route path="/zone/*" element={<Zone />} />
        <Route path="/jumeau/*" element={<JumeauNumerique />} />
>>>>>>> origin/develop
        <Route path="/faq" element={<Faq />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/account" element={<AccountSettings />} />
        <Route path="/settings" element={<AccountSettings />} />
        <Route path="/settings/*" element={<AccountSettings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <TyphoonMascot />
    </AssistantProvider>
  );
}