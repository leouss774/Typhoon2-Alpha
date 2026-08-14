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

export type ThemeMode = 'light' | 'dark' | 'system';

const hexRe = /^#[0-9a-fA-F]{6}$/;

/* Préférence système suivie en temps réel (mode « system »). */
const sysMq =
  typeof window !== 'undefined' ? window.matchMedia('(prefers-color-scheme: dark)') : null;

function systemPref(): 'dark' | 'light' {
  return sysMq && sysMq.matches ? 'dark' : 'light';
}

function readStorage() {
  let mode: ThemeMode = 'dark';
  let accent = BRAND_ACCENT;
  try {
    const m = localStorage.getItem('typhoon-theme');
    if (m === 'light' || m === 'dark' || m === 'system') mode = m;
    const a = localStorage.getItem('typhoon-accent');
    if (a && hexRe.test(a)) accent = a;
  } catch {
    /* localStorage unavailable */
  }
  return { mode, accent };
}

type ThemeState = { mode: ThemeMode; accent: string };

let state: ThemeState = readStorage();
const listeners = new Set<() => void>();

/* Snapshot mis en cache : identité stable tant que le mode, l'accent et la
   préférence système n'ont pas changé (évite les re-rendus infinis). */
let snapshotKey = '';
let snapshot: { mode: ThemeMode; theme: 'dark' | 'light'; accent: string } = {
  mode: state.mode,
  theme: systemPref(),
  accent: state.accent,
};

function getSnapshot() {
  const key = `${state.mode}|${state.accent}|${systemPref()}`;
  if (snapshotKey !== key) {
    snapshotKey = key;
    snapshot = {
      mode: state.mode,
      theme: state.mode === 'system' ? systemPref() : state.mode,
      accent: state.accent,
    };
  }
  return snapshot;
}

function setState(next: ThemeState) {
  state = next;
  try {
    localStorage.setItem('typhoon-theme', next.mode);
    localStorage.setItem('typhoon-accent', next.accent);
  } catch {
    /* ignore */
  }
  listeners.forEach((l) => l());
}

let mqCount = 0;
function subscribe(listener: () => void) {
  listeners.add(listener);
  if (sysMq && mqCount === 0) {
    sysMq.addEventListener('change', () => listeners.forEach((l) => l()));
  }
  mqCount += 1;
  return () => {
    mqCount -= 1;
    listeners.delete(listener);
  };
}

export function useTyphoonTheme() {
  const { mode, theme, accent } = useSyncExternalStore(subscribe, getSnapshot);
  const [panelOpen, setPanelOpen] = useState(false);

  const setThemeMode = useCallback((next: ThemeMode) => {
    setState({ ...state, mode: next });
  }, []);

  const toggleTheme = useCallback(() => {
    setState({ ...state, mode: theme === 'dark' ? 'light' : 'dark' });
  }, [theme]);

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
    mode,
    accent,
    panelOpen,
    setPanelOpen,
    setThemeMode,
    toggleTheme,
    resetAccent,
    pickAccent,
    wrapperClass: `typhoon-page ${theme === 'light' ? 'theme-light' : ''}`,
    wrapperStyle,
  };
}
