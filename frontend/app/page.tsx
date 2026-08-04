import Link from "next/link";
import styles from "./page.module.css";

function FeatureCard({
  icon,
  title,
  desc,
}: {
  icon: string;
  title: string;
  desc: string;
}) {
  return (
    <div className={styles.featureCard}>
      <div className={styles.featureIcon}>{icon}</div>
      <h3 className={styles.featureTitle}>{title}</h3>
      <p className={styles.featureDesc}>{desc}</p>
    </div>
  );
}

function SourceCard({
  name,
  desc,
  url,
}: {
  name: string;
  desc: string;
  url: string;
}) {
  return (
    <div className={styles.sourceCard}>
      <div className={styles.sourceName}>{name}</div>
      <p className={styles.sourceDesc}>{desc}</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className={styles.sourceLink}
      >
        Voir le site →
      </a>
    </div>
  );
}

export default function HomePage() {
  return (
    <div className={styles.page}>
      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.heroContent}>
          <div className={styles.eyebrow}>🔨 Plateforme de diagnostic</div>
          <h1 className={styles.heroTitle}>
            Évaluez les risques climatiques<br />
            et trouvez les <em>artisans</em> qu&apos;il vous faut
          </h1>
          <p className={styles.heroLead}>
            Une plateforme complète : diagnostic climatique de votre bien,
            scoring multirisques, et mise en relation avec des entreprises RGE
            et professionnels qualifiés pour vos travaux.
          </p>
          <div className={styles.heroCtas}>
            <Link href="/artisans" className="btn btn-primary" style={{ fontSize: 15, padding: "15px 26px" }}>
              🔍 Rechercher des artisans
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className={styles.features}>
        <h2 className={styles.sectionTitle}>Comment ça marche</h2>
        <div className={styles.featureGrid}>
          <FeatureCard
            icon="📋"
            title="1. Diagnostic du bien"
            desc="Analyse complète des risques climatiques : inondation, retrait-gonflement des argiles, séisme, tempête, radon, feu de forêt."
          />
          <FeatureCard
            icon="🔍"
            title="2. Matching artisans"
            desc="Pour chaque recommandation de travaux, notre moteur trouve des entreprises RGE (ADEME) et non-RGE (Recherche d'Entreprises)."
          />
          <FeatureCard
            icon="📊"
            title="3. Score objectif"
            desc="Chaque entreprise reçoit un score basé sur des critères vérifiables : validité de qualification, proximité géographique, ancienneté."
          />
          <FeatureCard
            icon="🔗"
            title="4. Annuaires de référence"
            desc="Pour les métiers sans label RGE, des liens vers les annuaires professionnels reconnus (USG, CINOV, etc.)."
          />
          <FeatureCard
            icon="🛡️"
            title="5. Données officielles"
            desc="Aucune donnée inventée. Toutes les informations proviennent des API open data de l'ADEME et de la Direction Générale des Entreprises."
          />
          <FeatureCard
            icon="📱"
            title="6. Rapport professionnel"
            desc="Rapport consolidé avec vue filtrée RGE / Non-RGE, détails des scores, coordonnées et sites web des entreprises."
          />
        </div>
      </section>

      {/* Data sources */}
      <section className={styles.sources}>
        <h2 className={styles.sectionTitle}>Sources de données</h2>
        <div className={styles.sourceGrid}>
          <SourceCard
            name="ADEME"
            desc="Liste des entreprises Reconnues Garantes de l'Environnement (RGE) — données ouvertes sous licence Etalab"
            url="https://data.ademe.fr"
          />
          <SourceCard
            name="Recherche d'Entreprises"
            desc="API officielle et gratuite de la Direction Générale des Entreprises — données SIREN/SIRET"
            url="https://recherche-entreprises.api.gouv.fr"
          />
          <SourceCard
            name="Géorisques"
            desc="Base de données des risques naturels et technologiques en France — BRGM"
            url="https://www.georisques.gouv.fr"
          />
        </div>
      </section>
    </div>
  );
}
