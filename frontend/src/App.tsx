import { Navigate, Route, Routes, Link, useLocation } from 'react-router-dom';
import { Home } from './routes/Home';
import { Zone } from './routes/Zone';
import { JumeauNumerique } from './routes/JumeauNumerique';
import { Promoteurs } from './routes/Promoteurs';
import { Artisans } from './routes/Artisans';
import { PropertyId } from './routes/PropertyId';
import { Site } from './routes/Site';

const nav = [
  { to: '/', label: 'Accueil' },
  { to: '/zone', label: 'Diagnostic' },
  { to: '/jumeau', label: 'Expérience' },
  { to: '/site', label: 'Site' },
];

function TopNav() {
  const location = useLocation();
  return (
    <header className="app-shell">
      <div className="brand">
        <div className="mark">T</div>
        <div>
          <div className="brand-name">Nolla Health</div>
          <div className="brand-tag">React mirror</div>
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
  const fullscreen = location.pathname === '/zone' || location.pathname === '/jumeau';
  return (
    <div>
      {!fullscreen && <TopNav />}
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/zone" element={<Zone />} />
        <Route path="/jumeau" element={<JumeauNumerique />} />
        <Route path="/promoteurs" element={<Promoteurs />} />
        <Route path="/artisans" element={<Artisans />} />
        <Route path="/property-id" element={<PropertyId />} />
        <Route path="/site" element={<Site />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </div>
  );
}
