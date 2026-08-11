import { Navigate, Route, Routes } from 'react-router-dom';
import { Home } from './routes/Home';
import { Zone } from './routes/Zone';
import { Usine } from './routes/Usine';
import { JumeauNumerique } from './routes/JumeauNumerique';
import { Faq } from './routes/Faq';
import { Contact } from './routes/Contact';
import { AccountSettings } from './routes/AccountSettings';
import { AssistantProvider } from './assistant/AssistantContext';
import { TyphoonMascot } from './assistant/TyphoonMascot';

/**
 * Application Typhoon :
 *   /         ? landing
 *   /zone     ? diagnostic immobilier
 *   /usine    ? analyse de plan d'usine (VLM)
 *   /jumeau   ? viewer 3D
 *   /faq, /contact ? pages statiques
 *   /account, /settings ? compte
 */
export default function App() {
  return (
    <AssistantProvider>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/zone/*" element={<Zone />} />
        <Route path="/usine" element={<Usine />} />
        <Route path="/jumeau/*" element={<JumeauNumerique />} />
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
