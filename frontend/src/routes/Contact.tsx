import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { useTyphoonTheme } from '../typhoon/useTyphoonTheme';
import { TyphoonFooter, TyphoonNavbar } from '../typhoon/TyphoonChrome';
import '../styles/typhoon-pages.css';

const PRIVACY_URL = 'https://vetter-consulting.webflow.io/legal/datenschutz';

export function Contact() {
  const { wrapperClass, wrapperStyle } = useTyphoonTheme();
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    if (!form.checkValidity()) {
      form.reportValidity();
      setStatus('error');
      return;
    }
    setStatus('success');
  };

  return (
    <div className={wrapperClass} style={wrapperStyle}>
      <TyphoonNavbar current="contact" />
      <section className="main-content">
        <div className="contact-form">
          <div className="contact-form-outer">
            <div className="_1x2-grid in-contact">
              <div className="grid-item-form">
                <img
                  src="/vetter-consulting/assets/img/acteur-assureurs.jpg"
                  srcSet="/vetter-consulting/assets/img/acteur-assureurs-p-500.jpg 500w, /vetter-consulting/assets/img/acteur-assureurs.jpg 1400w"
                  sizes="100vw"
                  loading="eager"
                  alt="Expert Typhoon"
                  className="grid-img is-relative in-contact"
                />
              </div>
              <div className="grid-item-form">
                <div className="grid-item-inner p-5">
                  <h1 className="global-headline-m is-left-aligned is-white">
                    Réservez une <span className="is-white">consultation gratuite</span>.
                  </h1>
                  <div className="calendly-btn-div">
                    <Link to="/zone" className="primary-btn _100 w-inline-block">
                      <span className="btn-txt-container">
                        <span className="btn-txt">C'est parti</span>
                        <span className="btn-txt">C'est parti</span>
                      </span>
                    </Link>
                  </div>
                  <div className="contact-divider">
                    <div className="line" />
                    <div className="copytext is-small in-form">Ou utilisez notre formulaire de contact</div>
                    <div className="line" />
                  </div>
                  <div className="form">
                    <form id="kontakt" name="wf-form-Kontakt" className="form-wrap" aria-label="Contact" onSubmit={handleSubmit}>
                      {status === 'success' ? null : (
                        <>
                          <div className="form-row">
                            <div className="form-item margin-right-1rem">
                              <label htmlFor="E-Mail" className="form-txt">
                                E-Mail*
                              </label>
                              <input className="input-field w-input" maxLength={256} name="E-Mail" placeholder="E-Mail" type="email" id="E-Mail" required />
                            </div>
                            <div className="form-item">
                              <label htmlFor="Telefon" className="form-txt">
                                Téléphone
                              </label>
                              <input className="input-field w-input" maxLength={256} name="Telefon" placeholder="Téléphone" type="tel" id="Telefon" />
                            </div>
                          </div>
                          <div className="form-row">
                            <div className="form-item">
                              <label htmlFor="Message" className="form-txt">
                                Votre message*
                              </label>
                              <textarea
                                id="Message"
                                name="Message"
                                maxLength={5000}
                                placeholder="Votre message"
                                required
                                className="input-field w-input"
                              />
                            </div>
                          </div>
                          <div className="form-row last">
                            <div className="form-item">
                              <label className="checkbox-field">
                                <input id="checkbox" type="checkbox" name="checkbox" required className="w-checkbox-input checkbox" />
                                <span className="form-txt w-form-label">
                                  J&apos;ai pris connaissance de la{' '}
                                  <a href={PRIVACY_URL} target="_blank" rel="noreferrer" className="inline-url">
                                    Politique de confidentialité.
                                  </a>
                                </span>
                              </label>
                            </div>
                          </div>
                          <div className="submit-div">
                            <input type="submit" data-wait="Envoi..." className="submit-button" value="Envoyer" />
                          </div>
                        </>
                      )}
                    </form>
                    {status === 'success' ? (
                      <div className="success-message" role="status">
                        <div className="succes-txt">Merci pour votre demande. Nous vous répondons sous 48h !</div>
                      </div>
                    ) : null}
                    {status === 'error' ? (
                      <div className="error-message" role="alert">
                        <div className="error-txt">Une erreur est survenue. Veuillez vérifier le formulaire.</div>
                      </div>
                    ) : null}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      <TyphoonFooter />
    </div>
  );
}
