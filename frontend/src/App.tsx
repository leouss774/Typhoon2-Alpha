import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { Home } from './routes/Home';
import { Zone } from './routes/Zone';
import { JumeauNumerique } from './routes/JumeauNumerique';
import { Faq } from './routes/Faq';
import { Contact } from './routes/Contact';
import { AccountSettings } from './routes/AccountSettings';
import { TyphonChatbot } from './components/TyphonChatbot';

/**
 * Application Typhoon — toutes les pages sont autonomes (plein écran) :
 *   /                  → landing page
 *   /zone              → diagnostic géo-risque (stepper + carte + jumeau BIM)
 *   /jumeau            → viewer 3D
 *   /faq, /contact     → pages typhoon
 *   /account, /settings → page « Paramètres du compte » (même chrome que /zone)
 */
export default function App() {
  const location = useLocation();
  return (
    <>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/zone/*" element={<Zone />} />
        <Route path="/jumeau/*" element={<JumeauNumerique />} />
        <Route path="/faq" element={<Faq />} />
        <Route path="/contact" element={<Contact />} />
        <Route path="/account" element={<AccountSettings />} />
        <Route path="/settings" element={<AccountSettings />} />
        <Route path="/settings/*" element={<AccountSettings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      {/* La page d'accueil reste volontairement sans chatbot flottant. */}
      {location.pathname !== '/' && !location.pathname.startsWith('/zone') && <TyphonChatbot />}
    </>
  );
}
