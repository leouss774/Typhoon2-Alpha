import styles from "./Footer.module.css";

export default function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <span className={styles.note}>
          © {new Date().getFullYear()} Typhoon — Données issues des API open
          data officielles (ADEME, Recherche d&apos;Entreprises, Géorisques)
        </span>
      </div>
    </footer>
  );
}
