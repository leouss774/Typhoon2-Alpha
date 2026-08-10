import { useCallback, useState, useSyncExternalStore, type CSSProperties } from 'react';

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

type ThemeState = { theme: 'dark' | 'light'; accent: string };

let state: ThemeState = readStorage();
const listeners = new Set<() => void>();

function setState(next: ThemeState) {
  state = next;
  try {
    localStorage.setItem('typhoon-theme', next.theme);
    localStorage.setItem('typhoon-accent', next.accent);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): ThemeState {
  return state;
}

export function useTyphoonTheme() {
  const { theme, accent } = useSyncExternalStore(subscribe, getSnapshot);
  const [panelOpen, setPanelOpen] = useState(false);

  const toggleTheme = useCallback(() => {
    setState({ ...state, theme: state.theme === 'dark' ? 'light' : 'dark' });
  }, []);

  const resetAccent = useCallback(() => {
    setState({ ...state, accent: BRAND_ACCENT });
    setPanelOpen(false);
  }, []);

  const pickAccent = useCallback((hex: string) => {
    setState({ ...state, accent: hex });
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
