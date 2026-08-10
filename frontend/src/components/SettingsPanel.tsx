import { useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { MOCK_USER } from './mockUser';
import { BrandIcon, type BrandName } from './BrandIcon';

export type SettingsTabKey = 'account' | 'security' | 'billing' | 'notifications' | 'connections';

const TABS: Array<{ key: SettingsTabKey; label: string; icon: string }> = [
  { key: 'account', label: 'Compte', icon: 'account_circle' },
  { key: 'security', label: 'Sécurité', icon: 'lock' },
  { key: 'billing', label: 'Abonnement & Facturation', icon: 'credit_card' },
  { key: 'notifications', label: 'Notifications', icon: 'notifications' },
  { key: 'connections', label: 'Connexions', icon: 'link' },
];

const COUNTRIES = [
  'France', 'Belgique', 'Suisse', 'Canada', 'Maroc', 'Tunisie',
  'Allemagne', 'Espagne', 'Italie', 'Royaume-Uni', 'États-Unis', 'Autre',
];
const LANGUAGES = [
  { value: 'fr', label: 'Français' },
  { value: 'en', label: 'English' },
  { value: 'de', label: 'Deutsch' },
  { value: 'es', label: 'Español' },
];
const TIMEZONES = [
  '(GMT+01:00) Paris, Berlin, Rome',
  '(GMT+00:00) Londres, Lisbonne',
  '(GMT+02:00) Le Caire, Athènes',
  '(GMT-05:00) New York, Montréal',
  '(GMT-08:00) Los Angeles',
];
const CURRENCIES = [
  { value: 'eur', label: 'EUR — Euro' },
  { value: 'usd', label: 'USD — Dollar' },
  { value: 'gbp', label: 'GBP — Livre sterling' },
  { value: 'chf', label: 'CHF — Franc suisse' },
];

/**
 * Panneau « Paramètres du compte » — intégré dans /zone (overlay sombre),
 * plus aucune route /settings dédiée.
 */
export function SettingsPanel({ initialTab = 'account' }: { initialTab?: SettingsTabKey }) {
  const [tab, setTab] = useState<SettingsTabKey>(initialTab);
  return (
    <div className="settings-page">
      <div className="settings-tabs" role="tablist" aria-label="Réglages du compte">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`settings-tab${tab === t.key ? ' active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            <md-icon>{t.icon}</md-icon>
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      <div className="settings-body">
        {tab === 'account' && <AccountTab />}
        {tab === 'security' && <SecurityTab />}
        {tab === 'billing' && <BillingTab />}
        {tab === 'notifications' && <NotificationsTab />}
        {tab === 'connections' && <ConnectionsTab />}
      </div>
    </div>
  );
}

/* ───────────────────────────── Petit matériel ───────────────────────────── */

function SectionCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className="settings-card">
      <h3>{title}</h3>
      {description && <p className="settings-card-desc">{description}</p>}
      {children}
    </section>
  );
}

function TextField({
  label,
  value,
  onChange,
  placeholder,
  type = 'text',
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <md-outlined-text-field
      label={label}
      value={value}
      type={type}
      placeholder={placeholder || ''}
      onInput={(e: React.FormEvent<HTMLElement>) =>
        onChange((e.target as HTMLInputElement).value)
      }
    />
  );
}

function SelectField({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: ReactNode;
}) {
  return (
    <label className="field m3-select-field">
      <span className="m3-select-label">{label}</span>
      <select
        className="m3-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {children}
      </select>
    </label>
  );
}

function SwitchRow({
  title,
  description,
  selected,
  onChange,
}: {
  title: string;
  description: string;
  selected: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="switch-row">
      <div className="switch-row-copy">
        <span className="switch-row-title">{title}</span>
        <span className="switch-row-desc">{description}</span>
      </div>
      <md-switch
        selected={selected}
        onChange={(e: React.FormEvent<HTMLElement>) =>
          onChange((e.target as unknown as { selected: boolean }).selected)
        }
      />
    </div>
  );
}

function SaveBar({ onSave, onReset }: { onSave: () => void; onReset?: () => void }) {
  const [saved, setSaved] = useState(false);
  return (
    <div className="settings-actions">
      <div className="settings-saved" role="status">
        {saved ? 'Modifications enregistrées (démo).' : ''}
      </div>
      <div className="settings-actions-btns">
        <md-filled-button
          onClick={() => {
            onSave();
            setSaved(true);
            window.setTimeout(() => setSaved(false), 2600);
          }}
        >
          Enregistrer les modifications
        </md-filled-button>
        {onReset && (
          <md-outlined-button onClick={onReset}>Annuler</md-outlined-button>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────────── Onglet Compte ───────────────────────────── */

function AccountTab() {
  const [avatar, setAvatar] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [firstName, setFirstName] = useState('Julien');
  const [lastName, setLastName] = useState('Martin');
  const [email, setEmail] = useState(MOCK_USER.email);
  const [organization, setOrganization] = useState(MOCK_USER.organization);
  const [phone, setPhone] = useState('+33 6 12 34 56 78');
  const [address, setAddress] = useState('14 Avenue des Palmiers');
  const [state, setState] = useState('Provence-Alpes-Côte d’Azur');
  const [zipCode, setZipCode] = useState('06000');
  const [country, setCountry] = useState('France');
  const [language, setLanguage] = useState('fr');
  const [timezone, setTimezone] = useState(TIMEZONES[0]);
  const [currency, setCurrency] = useState('eur');

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleted, setDeleted] = useState(false);

  const reset = () => {
    setFirstName('Julien');
    setLastName('Martin');
    setEmail(MOCK_USER.email);
    setOrganization(MOCK_USER.organization);
    setPhone('+33 6 12 34 56 78');
    setAddress('14 Avenue des Palmiers');
    setState('Provence-Alpes-Côte d’Azur');
    setZipCode('06000');
    setCountry('France');
    setLanguage('fr');
    setTimezone(TIMEZONES[0]);
    setCurrency('eur');
    setAvatar(null);
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setAvatar(String(reader.result));
    reader.readAsDataURL(file);
  };

  if (deleted) {
    return (
      <SectionCard title="Compte désactivé">
        <div className="delete-done">
          <md-icon>account_circle_off</md-icon>
          <p>
            Votre compte a été désactivé (démonstration). Cette action est
            réversible dans la vraie application — ici, rechargez la page pour
            revenir à la démo.
          </p>
          <md-filled-button onClick={() => setDeleted(false)}>
            Réactiver le compte (démo)
          </md-filled-button>
        </div>
      </SectionCard>
    );
  }

  return (
    <>
      <SectionCard title="Photo de profil" description="Votre photo apparaît dans votre profil et les rapports partagés.">
        <div className="avatar-upload-row">
          <div className="avatar-preview">
            {avatar ? (
              <img src={avatar} alt="Aperçu de la photo de profil" />
            ) : (
              <span className="mavatar-image">{MOCK_USER.initials}</span>
            )}
          </div>
          <div className="avatar-upload-actions">
            <div className="avatar-upload-btns">
              <md-outlined-button onClick={() => fileRef.current?.click()}>
                <md-icon slot="icon">upload</md-icon>
                Importer une photo
              </md-outlined-button>
              <md-text-button onClick={() => setAvatar(null)}>Réinitialiser</md-text-button>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept="image/png, image/jpeg, image/gif"
              hidden
              onChange={onPick}
            />
            <small>JPG, GIF ou PNG autorisés — 800 Ko maximum.</small>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Informations personnelles">
        <div className="settings-grid">
          <div className="field">
            <TextField label="Prénom" value={firstName} onChange={setFirstName} />
          </div>
          <div className="field">
            <TextField label="Nom" value={lastName} onChange={setLastName} />
          </div>
          <div className="field">
            <TextField label="Adresse e-mail" value={email} onChange={setEmail} type="email" />
          </div>
          <div className="field">
            <TextField label="Organisation" value={organization} onChange={setOrganization} />
          </div>
          <div className="field">
            <TextField label="Téléphone" value={phone} onChange={setPhone} placeholder="+33 6 12 34 56 78" />
          </div>
          <div className="field">
            <TextField label="Adresse" value={address} onChange={setAddress} />
          </div>
          <div className="field">
            <TextField label="Région / Département" value={state} onChange={setState} />
          </div>
          <div className="field">
            <TextField label="Code postal" value={zipCode} onChange={setZipCode} placeholder="06000" />
          </div>
          <div className="field">
            <SelectField label="Pays" value={country} onChange={setCountry}>
              <option value="">Sélectionner</option>
              {COUNTRIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </SelectField>
          </div>
          <div className="field">
            <SelectField label="Langue" value={language} onChange={setLanguage}>
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>{l.label}</option>
              ))}
            </SelectField>
          </div>
          <div className="field">
            <SelectField label="Fuseau horaire" value={timezone} onChange={setTimezone}>
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </SelectField>
          </div>
          <div className="field">
            <SelectField label="Devise" value={currency} onChange={setCurrency}>
              {CURRENCIES.map((c) => (
                <option key={c.value} value={c.value}>{c.label}</option>
              ))}
            </SelectField>
          </div>
        </div>
        <SaveBar onSave={() => undefined} onReset={reset} />
      </SectionCard>

      <SectionCard title="Supprimer le compte">
        <div className="delete-warning">
          <md-icon>warning</md-icon>
          <div>
            <strong>Êtes-vous sûr de vouloir supprimer votre compte ?</strong>
            <p>
              Une fois le compte supprimé, il n'y a plus de retour en arrière :
              vos diagnostics, rapports et préférences seront définitivement
              effacés. Soyez certain(e) avant de continuer.
            </p>
          </div>
        </div>
        {!confirmDelete ? (
          <md-outlined-button
            className="danger"
            onClick={() => setConfirmDelete(true)}
          >
            Supprimer le compte
          </md-outlined-button>
        ) : (
          <div className="delete-confirm">
            <label className="confirm-line">
              <input
                type="checkbox"
                checked={confirmDelete}
                onChange={() => setConfirmDelete((c) => !c)}
              />
              <span>Je confirme la suppression de mon compte</span>
            </label>
            <div className="settings-actions-btns">
              <md-filled-button className="danger" onClick={() => setDeleted(true)}>
                Supprimer définitivement
              </md-filled-button>
              <md-text-button onClick={() => setConfirmDelete(false)}>
                Annuler
              </md-text-button>
            </div>
          </div>
        )}
      </SectionCard>
    </>
  );
}

/* ───────────────────────────── Onglet Sécurité ─────────────────────────── */

const PASSWORD_REQS = [
  'Au moins 8 caractères — plus c’est long, mieux c’est.',
  'Au moins une lettre minuscule.',
  'Au moins un chiffre, un symbole ou un espace.',
];

function SecurityTab() {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [twoFaEnabled, setTwoFaEnabled] = useState(false);
  const [keyType, setKeyType] = useState('full');
  const [keyName, setKeyName] = useState('Clé Serveur 1');
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  const resetPassword = () => {
    setCurrent('');
    setNext('');
    setConfirm('');
  };

  return (
    <>
      <SectionCard title="Changer le mot de passe">
        <div className="settings-grid">
          <div className="field span-2">
            <TextField label="Mot de passe actuel" value={current} onChange={setCurrent} type="password" />
          </div>
          <div className="field">
            <TextField label="Nouveau mot de passe" value={next} onChange={setNext} type="password" />
          </div>
          <div className="field">
            <TextField label="Confirmer le nouveau mot de passe" value={confirm} onChange={setConfirm} type="password" />
          </div>
        </div>
        <div className="password-reqs">
          <span className="password-reqs-title">Exigences du mot de passe :</span>
          <ul>
            {PASSWORD_REQS.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </div>
        <SaveBar onSave={() => undefined} onReset={resetPassword} />
      </SectionCard>

      <SectionCard title="Vérification en deux étapes">
        {!twoFaEnabled ? (
          <>
            <p className="twofa-subtitle">La double authentification n’est pas encore activée.</p>
            <p className="twofa-desc">
              La double authentification ajoute une couche de sécurité
              supplémentaire à votre compte en exigeant plus qu’un simple mot de
              passe pour vous connecter.{' '}
              <a href="#" onClick={(e) => e.preventDefault()}>En savoir plus.</a>
            </p>
            <md-filled-button onClick={() => setTwoFaEnabled(true)}>
              <md-icon slot="icon">verified_user</md-icon>
              Activer la double authentification
            </md-filled-button>
          </>
        ) : (
          <div className="twofa-on">
            <span className="chip chip-live">Activée</span>
            <p>
              La double authentification est active sur votre compte. À chaque
              connexion sur un nouvel appareil, un code à usage unique vous sera
              demandé (démo).
            </p>
            <md-outlined-button onClick={() => setTwoFaEnabled(false)}>
              Désactiver
            </md-outlined-button>
          </div>
        )}
      </SectionCard>

      <SectionCard title="Créer une clé API" description="Générez des clés pour intégrer Typhoon à vos outils et scripts.">
        <div className="api-key-layout">
          <div className="api-key-form">
            <SelectField label="Choisissez le type de clé API à créer" value={keyType} onChange={setKeyType}>
              <option value="full">Accès complet</option>
              <option value="read">Lecture seule</option>
              <option value="webhook">Webhooks</option>
            </SelectField>
            <div className="field">
              <TextField label="Nommer la clé API" value={keyName} onChange={setKeyName} placeholder="Clé Serveur 1" />
            </div>
            {createdKey && (
              <div className="key-output">
                <span>Clé générée (démo) :</span>
                <code>{createdKey}</code>
              </div>
            )}
            <md-filled-button
              className="api-key-create"
              onClick={() =>
                setCreatedKey(`ty_${keyType}_${Math.random().toString(36).slice(2, 10)}_${Math.random().toString(36).slice(2, 10)}`)
              }
            >
              Créer la clé
            </md-filled-button>
          </div>
          <div className="api-key-visual" aria-hidden="true">
            <div className="api-key-illo">
              <md-icon>key</md-icon>
              <md-icon>terminal</md-icon>
              <md-icon>shield</md-icon>
            </div>
            <span>Intégration API</span>
            <small>REST · JSON · clés en lecture ou écriture</small>
          </div>
        </div>
      </SectionCard>
    </>
  );
}

/* ──────────────────── Onglet Abonnement & Facturation ──────────────────── */

type SavedCard = {
  id: number;
  brand: 'mastercard' | 'visa';
  holder: string;
  last4: string;
  exp: string;
  primary?: boolean;
};

function BillingTab() {
  const [cardType, setCardType] = useState<'card' | 'paypal'>('card');
  const [cardNumber, setCardNumber] = useState('1356 3215 6548 7898');
  const [cardName, setCardName] = useState('Julien Martin');
  const [expDate, setExpDate] = useState('12/26');
  const [cvv, setCvv] = useState('654');
  const [saveCard, setSaveCard] = useState(false);
  const [saved, setSaved] = useState(false);

  const [cards, setCards] = useState<SavedCard[]>([
    { id: 1, brand: 'mastercard', holder: 'Julien Martin', last4: '9856', exp: '12/26', primary: true },
    { id: 2, brand: 'visa', holder: 'Julien Martin', last4: '5896', exp: '10/27' },
  ]);

  const removeCard = (id: number) => setCards((cs) => cs.filter((c) => c.id !== id));
  const addCard = () => {
    const last4 = cardNumber.replace(/\D/g, '').slice(-4) || '0000';
    setCards((cs) => [
      ...cs,
      { id: Date.now(), brand: cardType === 'paypal' ? 'visa' : 'mastercard', holder: cardName || 'Julien Martin', last4, exp: expDate || '12/27' },
    ]);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2600);
  };

  return (
    <>
      <SectionCard title="Formule actuelle">
        <div className="plan-summary">
          <div className="plan-summary-info">
            <p className="plan-summary-title">Votre formule actuelle est <strong>Pro</strong></p>
            <p className="plan-summary-sub">Un démarrage simple pour tous.</p>

            <div className="plan-summary-active">
              <strong>Active jusqu’au 9 déc. 2026</strong>
              <span>Nous vous enverrons une notification à l’expiration de l’abonnement.</span>
            </div>

            <div className="plan-price-row">
              <span className="plan-price-amount">29 €</span>
              <span className="plan-price-period">par mois</span>
              <span className="plan-badge">Populaire</span>
            </div>
            <p className="plan-summary-desc">
              Formule standard pour particuliers et petites structures.
            </p>

            <div className="plan-summary-actions">
              <md-filled-button>Passer à la formule supérieure</md-filled-button>
              <md-outlined-button className="danger">Annuler l’abonnement</md-outlined-button>
            </div>
          </div>

          <div className="plan-summary-side">
            <div className="plan-attention">
              <md-icon>warning</md-icon>
              <div>
                <strong>Nous avons besoin de votre attention !</strong>
                <span>Votre formule nécessite une mise à jour.</span>
              </div>
            </div>
            <div className="plan-progress">
              <div className="plan-progress-meta">
                <span>Jours</span>
                <span>12 de 30</span>
              </div>
              <div className="plan-progress-track" aria-hidden="true">
                <div className="plan-progress-fill" style={{ width: '40%' }} />
              </div>
              <small>18 jours restants avant la mise à jour de votre formule.</small>
            </div>
          </div>
        </div>
      </SectionCard>

      <SectionCard title="Moyens de paiement">
        <div className="payment-layout">
          <div className="payment-form">
            <div className="radio-group" role="radiogroup" aria-label="Type de paiement">
              <label className={`radio-option${cardType === 'card' ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="cardType"
                  checked={cardType === 'card'}
                  onChange={() => setCardType('card')}
                />
                <span>Carte de crédit / débit</span>
              </label>
              <label className={`radio-option${cardType === 'paypal' ? ' selected' : ''}`}>
                <input
                  type="radio"
                  name="cardType"
                  checked={cardType === 'paypal'}
                  onChange={() => setCardType('paypal')}
                />
                <span className="radio-paypal">
                  <BrandIcon name="paypal" className="brand-mark" />
                  Compte Paypal
                </span>
              </label>
            </div>

            {cardType === 'card' ? (
              <>
                <div className="field">
                  <TextField label="Numéro de carte" value={cardNumber} onChange={setCardNumber} placeholder="1356 3215 6548 7898" />
                </div>
                <div className="payment-field-row">
                  <div className="field">
                    <TextField label="Nom" value={cardName} onChange={setCardName} placeholder="Julien Martin" />
                  </div>
                  <div className="field">
                    <TextField label="Expiration" value={expDate} onChange={setExpDate} placeholder="MM/AA" />
                  </div>
                  <div className="field">
                    <TextField label="Cryptogramme (CVV)" value={cvv} onChange={setCvv} type="password" placeholder="•••" />
                  </div>
                </div>
                <div className="payment-save-toggle">
                  <md-switch
                    selected={saveCard}
                    onChange={(e: React.FormEvent<HTMLElement>) =>
                      setSaveCard((e.target as unknown as { selected: boolean }).selected)
                    }
                  />
                  <span>Enregistrer la carte pour les futurs paiements ?</span>
                </div>
              </>
            ) : (
              <div className="paypal-note">
                <BrandIcon name="paypal" className="brand-mark brand-mark--paypal" />
                <p>
                  Vous serez redirigé vers Paypal pour associer votre compte
                  (démo — aucune connexion réelle n’est effectuée).
                </p>
              </div>
            )}

            {cardType === 'card' && (
              <div className="settings-actions-btns payment-form-actions">
                <md-filled-button onClick={addCard}>Enregistrer</md-filled-button>
                <md-outlined-button onClick={() => { setCardType('card'); setCardNumber(''); setCardName(''); setExpDate(''); setCvv(''); }}>
                  Annuler
                </md-outlined-button>
                {saved && <span className="settings-saved">Carte enregistrée (démo).</span>}
              </div>
            )}
          </div>

          <div className="my-cards">
            <h4>Mes cartes</h4>
            <ul className="saved-card-list">
              {cards.map((card) => (
                <li key={card.id} className="saved-card">
                  <div className="saved-card-main">
                    <span
                      className={`card-brand card-brand--${card.brand}`}
                      aria-hidden="true"
                      title={card.brand === 'mastercard' ? 'Mastercard' : 'Visa'}
                    >
                      <BrandIcon name={card.brand} className="card-brand-svg" />
                    </span>
                    <div className="saved-card-info">
                      <div className="saved-card-holder">
                        <span>{card.holder}</span>
                        {card.primary && <span className="chip chip-primary">Principale</span>}
                      </div>
                      <span className="saved-card-num">•••• •••• {card.last4}</span>
                    </div>
                  </div>
                  <div className="saved-card-actions">
                    <div className="settings-actions-btns">
                      <md-text-button>Modifier</md-text-button>
                      <md-text-button className="danger" onClick={() => removeCard(card.id)}>
                        Supprimer
                      </md-text-button>
                    </div>
                    <span className="saved-card-exp">La carte expire le {card.exp}</span>
                  </div>
                </li>
              ))}
              {cards.length === 0 && (
                <li className="saved-card saved-card--empty">
                  <md-icon>credit_card_off</md-icon>
                  <span>Aucune carte enregistrée.</span>
                </li>
              )}
            </ul>
          </div>
        </div>
      </SectionCard>
    </>
  );
}

/* ──────────────────────────── Onglet Notifications ─────────────────────── */

function NotificationsTab() {
  const [emailRisk, setEmailRisk] = useState(true);
  const [emailReport, setEmailReport] = useState(true);
  const [emailNews, setEmailNews] = useState(false);
  const [push, setPush] = useState(true);
  const [pushZone, setPushZone] = useState(false);

  return (
    <>
      <SectionCard title="Notifications par e-mail">
        <div className="switch-stack">
          <SwitchRow
            title="Alertes de risque élevé"
            description="Prévenez-moi par e-mail dès qu'un niveau critique est détecté sur une adresse suivie."
            selected={emailRisk}
            onChange={setEmailRisk}
          />
          <SwitchRow
            title="Rapport mensuel"
            description="Résumé mensuel de l'activité et des évolutions réglementaires sur mes zones suivies."
            selected={emailReport}
            onChange={setEmailReport}
          />
          <SwitchRow
            title="Nouveautés produit"
            description="Annonces de nouvelles fonctionnalités et améliorations de Typhoon."
            selected={emailNews}
            onChange={setEmailNews}
          />
        </div>
      </SectionCard>

      <SectionCard title="Notifications push (navigateur)">
        <div className="switch-stack">
          <SwitchRow
            title="Simulations du jumeau BIM"
            description="Recevez une notification quand une simulation de catastrophe se termine sur votre jumeau."
            selected={push}
            onChange={setPush}
          />
          <SwitchRow
            title="Zones surveillées"
            description="Alerte immédiate si un nouvel arrêté CatNat touche une commune de votre liste."
            selected={pushZone}
            onChange={setPushZone}
          />
        </div>
      </SectionCard>
      <SaveBar onSave={() => undefined} />
    </>
  );
}

/* ──────────────────────────── Onglet Connexions ────────────────────────── */

function ConnectionsTab() {
  const apps: Array<{
    name: string;
    slug: BrandName;
    desc: string;
    connected: boolean;
  }> = [
    { name: 'GitHub', slug: 'github', desc: 'Synchronisation des projets d’exemple', connected: true },
    { name: 'Google Drive', slug: 'googledrive', desc: 'Export des rapports PDF', connected: true },
    { name: 'Slack', slug: 'slack', desc: 'Notifications d’équipe', connected: false },
    { name: 'Notion', slug: 'notion', desc: 'Documentation & notes de diagnostic', connected: false },
    { name: 'Mistral AI', slug: 'mistralai', desc: 'Moteur de rédaction des rapports narratifs', connected: true },
  ];
  const [state, setState] = useState(apps.map((a) => a.connected));

  return (
    <>
      <SectionCard title="Applications connectées" description="Gérez les services tiers liés à votre compte Typhoon.">
        <ul className="conn-list">
          {apps.map((app, i) => (
            <li key={app.name} className="conn-row">
              <div className={`conn-icon brand-tile brand-tile--${app.slug}`}>
                <BrandIcon name={app.slug} />
              </div>
              <div className="conn-copy">
                <span className="conn-name">{app.name}</span>
                <span className="conn-desc">{app.desc}</span>
              </div>
              {state[i] ? (
                <md-outlined-button onClick={() => setState((s) => s.map((v, j) => (j === i ? false : v)))}>
                  Déconnecter
                </md-outlined-button>
              ) : (
                <md-filled-button onClick={() => setState((s) => s.map((v, j) => (j === i ? true : v)))}>
                  Connecter
                </md-filled-button>
              )}
            </li>
          ))}
        </ul>
      </SectionCard>
      <div className="settings-note">
        <md-icon>info</md-icon>
        <span>
          Démonstration : les connexions affichées sont fictives et aucune
          donnée n'est échangée avec des services tiers.
        </span>
      </div>
    </>
  );
}
