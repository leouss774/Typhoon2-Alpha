import {LitElement, html, css} from 'https://esm.run/lit';

export const materialImports = `
  <script type="importmap">
  {
    "imports": {
      "lit": "https://esm.run/lit",
      "@material/web/": "https://esm.run/@material/web/"
    }
  }
  </script>
`;

export class TyphoonAppHeader extends LitElement {
  static styles = css`
    :host { display: block; }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      padding: 1rem 1.25rem;
      border-bottom: 1px solid var(--md-sys-color-outline-variant);
      background: color-mix(in srgb, var(--md-sys-color-surface) 92%, white);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 20;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.8rem;
      min-width: 0;
    }
    .mark {
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 0.9rem;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, var(--md-sys-color-primary-container), var(--md-sys-color-primary));
      color: var(--md-sys-color-on-primary);
      font-weight: 800;
      box-shadow: 0 12px 30px rgba(49, 111, 150, 0.18);
    }
    .name {
      font-family: var(--typhoon-serif);
      font-size: 1.1rem;
      font-weight: 700;
      line-height: 1;
    }
    .tag {
      display: block;
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--md-sys-color-primary);
      margin-top: 0.2rem;
    }
    nav {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      justify-content: flex-end;
    }
  `;

  render() {
    return html`
      <header>
        <div class="brand">
          <div class="mark">T</div>
          <div>
            <div class="name">Typhoon</div>
            <span class="tag"><slot name="tag">Climate intelligence</slot></span>
          </div>
        </div>
        <nav><slot name="actions"></slot></nav>
      </header>
    `;
  }
}

customElements.define('typhoon-app-header', TyphoonAppHeader);

export class TyphoonSectionCard extends LitElement {
  static styles = css`
    :host { display: block; }
    section {
      border: 1px solid var(--md-sys-color-outline-variant);
      border-radius: 1.25rem;
      background: var(--md-sys-color-surface);
      box-shadow: 0 14px 40px rgba(30, 42, 51, 0.08);
      overflow: hidden;
    }
    .body { padding: 1.25rem; }
    h2 { margin: 0 0 0.5rem; font: 700 1.4rem var(--typhoon-serif); }
    p { margin: 0; color: var(--md-sys-color-on-surface-variant); line-height: 1.6; }
  `;
  render() {
    return html`<section><div class="body"><slot></slot></div></section>`;
  }
}

customElements.define('typhoon-section-card', TyphoonSectionCard);
