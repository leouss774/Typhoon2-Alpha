import { Navigate, Route, Routes, Link, useLocation } from 'react-router-dom';
import { Home } from './routes/Home';
import { Zone } from './routes/Zone';
import { JumeauNumerique } from './routes/JumeauNumerique';
import { Promoteurs } from './routes/Promoteurs';
import { Artisans } from './routes/Artisans';
import { PropertyId } from './routes/PropertyId';
import { Site } from './routes/Site';
import { Faq } from './routes/Faq';
import { Contact } from './routes/Contact';
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

export default function App() {
  const location = useLocation();
  const fullscreen =
    location.pathname === '/' ||
    location.pathname === '/faq' ||
    location.pathname === '/contact' ||
    location.pathname === '/zone' ||
    location.pathname === '/jumeau';
  return (
    <div>
      {!fullscreen && <TopNav />}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/zone" element={<Zone />} />
        <Route path="/jumeau" element={<JumeauNumerique />} />
        <Route path="/promoteurs" element={<Promoteurs />} />
        <Route path="/artisans" element={<Artisans />} />
        <Route path="/economie" element={<Economie />} />
        <Route path="/property-id" element={<PropertyId />} />
        <Route path="/site" element={<Site />} />
        <Route path="/faq" element={<Faq />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}