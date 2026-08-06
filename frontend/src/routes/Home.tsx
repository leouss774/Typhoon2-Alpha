import { StaticPage } from './StaticPage';

// Cache-buster: forces the browser to revalidate /landing.html instead of
// serving a stale cached copy (the landing page is a static file in public/).
// Cache-buster bumpé après le correctif SRI jquery (landing figée sur le
// preloader : hash d'intégrité obsolète bloqué par le navigateur).
const LANDING_SRC = '/landing.html?v=20260806';

export function Home() {
  return <StaticPage src={LANDING_SRC} title="Typhoon" />;
}
