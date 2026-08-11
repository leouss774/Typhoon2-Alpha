// =============================================================================
//   TYPHOON — /usine : champ adresse du site (optionnel) avec autocomplétion BAN
//   Le site (adresse) alimente le contexte Géorisques du risk engine :
//   R = √(F × V) où F devient l'aléa du site (score Géorisques) au lieu du
//   neutre 50 quand une adresse est renseignée — même moteur que /zone.
// =============================================================================

import { useEffect, useRef, useState } from 'react';
import { API, type GeocodeSuggestion } from '../zone/config';

type Props = {
  value: string | null;
  onChange: (adresse: string | null) => void;
};

export function UsineAdresseField({ value, onChange }: Props) {
  const [query, setQuery] = useState(value || '');
  const [suggestions, setSuggestions] = useState<GeocodeSuggestion[]>([]);
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const banTimeout = useRef<number | null>(null);

  /* Resynchroniser le champ si l'adresse change en dehors (reset, etc.). */
  useEffect(() => {
    setQuery(value || '');
  }, [value]);

  function fetchSuggestions(q: string) {
    fetch(`${API}/api/geocode/search?q=${encodeURIComponent(q)}&limit=5`)
      .then((resp) => (resp.ok ? resp.json() : Promise.reject(new Error(`HTTP ${resp.status}`))))
      .then((data) => {
        setSuggestions(data.results || []);
        setSuggestionsOpen(true);
      })
      .catch(() => hideSuggestions());
  }

  function hideSuggestions() {
    setSuggestionsOpen(false);
  }

  function onQueryChange(next: string) {
    setQuery(next);
    if (next.trim() !== value && next.trim()) onChange(null);
    if (banTimeout.current) window.clearTimeout(banTimeout.current);
    if (next.trim().length < 3) {
      hideSuggestions();
      return;
    }
    banTimeout.current = window.setTimeout(() => fetchSuggestions(next.trim()), 220);
  }

  function pickSuggestion(s: GeocodeSuggestion) {
    setQuery(s.label);
    hideSuggestions();
    onChange(s.label);
  }

  function clearAddress() {
    setQuery('');
    hideSuggestions();
    onChange(null);
  }

  return (
    <div className="usine-adresse">
      <div className="usine-adresse-label">
        <md-icon>location_on</md-icon>
        <span>Adresse du site industriel</span>
        <span className="usine-adresse-optional">optionnel</span>
      </div>
      <div className="usine-adresse-input-wrap">
        <input
          type="search"
          className="usine-adresse-input"
          placeholder="Ex. 14 Avenue des Palmiers, 13001 Marseille"
          autoComplete="off"
          spellCheck={false}
          inputMode="search"
          aria-label="Adresse du site industriel (optionnelle)"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && query.trim().length >= 3) {
              e.preventDefault();
              hideSuggestions();
              onChange(query.trim());
            }
          }}
          onBlur={() => window.setTimeout(hideSuggestions, 180)}
        />
        {query && value && (
          <md-icon-button className="usine-adresse-clear" aria-label="Effacer l'adresse" onClick={clearAddress}>
            <md-icon>close</md-icon>
          </md-icon-button>
        )}

        {suggestionsOpen && suggestions.length > 0 && (
          <div className="usine-adresse-suggestions">
            <md-list>
              {suggestions.map((s, i) => (
                <md-list-item
                  key={i}
                  onMouseDown={(e: { preventDefault: () => void }) => e.preventDefault()}
                  onClick={() => pickSuggestion(s)}
                >
                  <md-icon slot="start">place</md-icon>
                  <span slot="headline">{s.label}</span>
                  {s.context ? <span slot="supporting-text">{s.context}</span> : null}
                </md-list-item>
              ))}
            </md-list>
          </div>
        )}
      </div>
      <p className="usine-adresse-hint">
        <md-icon>shield</md-icon>
        <span>
          {value
            ? `Géorisques : l'aléa du site « ${value} » entre dans le calcul (F) — même moteur que le diagnostic /zone.`
            : 'Sans adresse, l\u2019aléa du site reste neutre (F = 50). Renseignez-la pour croiser le risque avec les données Géorisques.'}
        </span>
      </p>
    </div>
  );
}
