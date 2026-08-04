import { Link } from 'react-router-dom';

const CONTACT_EMAIL = 'hello@typhoon.eco';
const DEMO_URL = 'https://calendly.com/tobias-vetter/erstberatung';

export function Contact() {
  return (
    <main className="info-page contact-page">
      <section className="info-page__hero">
        <p className="info-page__eyebrow">Contact</p>
        <h1>Talk to the team about your portfolio, workflow, or pilot.</h1>
        <p className="info-page__lead">
          Reach out for a demo, a pilot discussion, or questions about Typhoon&apos;s climate-risk analysis
          workflows.
        </p>
      </section>

      <section className="info-page__surface contact-page__grid">
        <article className="contact-card">
          <p className="contact-card__label">Email</p>
          <h2>{CONTACT_EMAIL}</h2>
          <p>Use email for partnership questions, demos, and follow-up discussions.</p>
          <a className="info-page__button info-page__button--primary" href={`mailto:${CONTACT_EMAIL}`}>
            Send email
          </a>
        </article>

        <article className="contact-card">
          <p className="contact-card__label">Demo</p>
          <h2>Book a walkthrough</h2>
          <p>Choose a time slot and walk through the platform with the team.</p>
          <a
            className="info-page__button info-page__button--secondary"
            href={DEMO_URL}
            target="_blank"
            rel="noreferrer"
          >
            Open Calendly
          </a>
        </article>

        <article className="contact-card contact-card--wide">
          <p className="contact-card__label">Next steps</p>
          <h2>Need more context first?</h2>
          <p>
            Start with the most common platform questions, then come back here when you are ready to talk
            implementation, scope, or rollout.
          </p>
          <Link to="/faq" className="info-page__button info-page__button--ghost">
            Go to FAQ
          </Link>
        </article>
      </section>
    </main>
  );
}
