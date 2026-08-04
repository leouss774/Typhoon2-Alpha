import { useCallback, useEffect, useState, type CSSProperties } from 'react';

export const BRAND_ACCENT = '#4386B1';

export const ACCENTS = [
  '#4386B1',
  '#7b2cbf',
  '#e63946',
  '#f97316',
  '#22c55e',
  '#06b6d4',
  '#ec4899',
  '#eab308',
  '#64748b',
  '#10b981',
];

const hexRe = /^#[0-9a-fA-F]{6}$/;

function readStorage() {
  let theme: 'dark' | 'light' = 'dark';
  let accent = BRAND_ACCENT;
  try {
    if (localStorage.getItem('typhoon-theme') === 'light') theme = 'light';
    const a = localStorage.getItem('typhoon-accent');
    if (a && hexRe.test(a)) accent = a;
  } catch {
    /* localStorage unavailable */
  }
  return { theme, accent };
}

export function useTyphoonTheme() {
  const [state] = useState(readStorage);
  const [theme, setTheme] = useState<'dark' | 'light'>(state.theme);
  const [accent, setAccent] = useState<string>(state.accent);
  const [panelOpen, setPanelOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem('typhoon-theme', theme);
    } catch {
      /* ignore */
    }
  }, [theme]);

  useEffect(() => {
    try {
      localStorage.setItem('typhoon-accent', accent);
    } catch {
      /* ignore */
    }
  }, [accent]);

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'));
  }, []);

  const resetAccent = useCallback(() => {
    setAccent(BRAND_ACCENT);
    setPanelOpen(false);
  }, []);

  const pickAccent = useCallback((hex: string) => {
    setAccent(hex);
    setPanelOpen(false);
  }, []);

  const wrapperStyle = {
    '--orange': accent,
    '--orange-tint': `${accent}2e`,
  } as CSSProperties;

  return {
    theme,
    accent,
    panelOpen,
    setPanelOpen,
    toggleTheme,
    resetAccent,
    pickAccent,
    wrapperClass: `typhoon-page ${theme === 'light' ? 'theme-light' : ''}`,
    wrapperStyle,
  };
}
