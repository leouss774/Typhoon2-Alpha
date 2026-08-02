import { useEffect } from 'react';

export function Home() {
  useEffect(() => {
    window.location.replace('/nolla-mirror/index.html');
  }, []);

  return (
    <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <p>Loading Nolla mirror…</p>
    </main>
  );
}
