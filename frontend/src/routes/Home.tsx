// Cache-buster: forces the browser to revalidate /landing.html instead of
// serving a stale cached copy (the landing page is a static file in public/).
const LANDING_SRC = '/landing.html?v=20260803';

export function Home() {
  return (
    <main className="landing-embed">
      <iframe src={LANDING_SRC} title="Typhoon" className="landing-frame" />
    </main>
  );
}
