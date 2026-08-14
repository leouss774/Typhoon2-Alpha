# Typhoon — Plan produit & frontend : priorité « Assurance », multi-profils

> Objectif : finaliser le produit autour d'une vraie user story — la compagnie
> d'assurance — tout en gardant les promoteurs immobiliers et les banques
> servis par la même brique de diagnostic. Ce document traduit la stratégie en
> changements concrets de l'interface (composants, routes, étapes) et en
> roadmap ordonnée.

---

## 1. Les trois profils — jobs-to-be-done

Le moteur de diagnostic (adresse → aléas Géorisques + fiche BDNB + score D03)
est **unique**. Ce qui change, c'est ce que l'utilisateur veut *faire* du
résultat.

| Profil | Job principal | Question qu'il se pose | Valeur livrée par Typhoon |
|---|---|---|---|
| **Assureur** (cible) | Souscrire, tarifer, gérer un portefeuille, traiter un sinistre | « À quel risque suis-je exposé sur ce bien / ce portefeuille, aujourd'hui et demain ? » | Score décisionnel + historique CatNat + trajectoire climatique + exports auditables |
| **Promoteur immobilier** | Préparer un projet, chiffrer les travaux, vendre la résilience | « Quels travaux, à quel coût, avec quel gain ? » | Recommandations chiffrées (coût/gain), artisans, plan d'adaptation |
| **Banque** | Monter un dossier de crédit, vérifier la conformité | « Le bien est-il finançable / assuré de façon réglementaire ? » | Rapport ERRIAL officiel + synthèse conformité pour le dossier de prêt |

Le frontend actuel est **déjà orienté promoteur** (étapes Recommandations →
Artisans). C'est bien : il faut le conserver tel quel, et **ajouter** des
« vues » assurance et banque sur le même moteur.

---

## 2. User story cible : l'assureur

### Persona

**Claire, chargée de souscription risques habitation** (mutuelle, 40 000
contrats). Elle reçoit une demande de couverture pour un appartement à Nice.
Elle doit répondre en < 10 min, documenter sa décision, et archiver une trace
auditable.

### Parcours (jour de travail type)

1. **Souscription** — elle colle l'adresse du prospect. Typhoon affiche une
   **carte de décision** : score /100, bande D03, aléas présents, arrêtés
   CatNat passés sur la commune. Elle accepte / refuse / renvoie vers une
   expertise. → *Décision justifiable, copiable, imprimable.*
2. **Tarification** — elle compare le bien à la moyenne communale et bascule
   un curseur **horizon 2026 → 2050 → 2100** : le score évolue avec les
   projections climatiques. → *Un élément de pricing, pas juste une alarme.*
3. **Portefeuille** — chaque lundi elle importe un CSV de 2 000 adresses
   (contrats entrants). Typhoon diagnostique le lot et rend un **tableau de
   bord** : répartition par bande D03, communes les plus exposées, top des
   biens à réviser. → *Exposition agrégée, triée par criticité.*
4. **Sinistre** — un client déclare un dégât des eaux après un arrêté CatNat.
   Elle re-ouvre l'adresse en mode « check sinistre » : historique des
   événements, dates d'arrêtés, fiche bâtiment. → *Réponse rapide, pièce
   justificative exportable.*
5. **Suivi** — elle ajoute les communes sensibles à une **watchlist** ;
   Typhoon l'alerte quand un nouvel arrêté CatNat paraît. → *Veille
   réglementaire sans recherche manuelle.*

### Ce que l'assureur n'a pas besoin

- Les artisans (c'est le promoteur qui les cherche) — *à masquer/condenser*.
- Le plan de travaux détaillé — *remplacé par un « risque résiduel après
  travaux » (optionnel, à terme)*.

---

## 3. Écart entre le frontend actuel et les besoins assureur

| Besoin assureur | État actuel | Écart |
|---|---|---|
| Score clair & bande D03 | ✅ Score /100 + bande D03 (step Cartographie) | Verdict trop « noyé » parmi les aléas ; pas de carte de décision |
| Historique CatNat | ✅ Liste d'arrêtés (step Cartographie) | Pas de timeline visuelle, pas de lien arrêté ↔ date de sinistre |
| Fiche bâtiment (BDNB) | ✅ BuildingFiche (step Analyse) | Présente, mais orientée technique (promoteur) |
| Rapport narratif + PDF | ✅ Rapport IA + export jsPDF + ERRIAL officiel | PDF générique, pas de template « compagnie » avec logo/mention |
| Projections climatiques | ❌ | Rien aujourd'hui : le score est statique (état actuel) |
| Analyse **portefeuille** (CSV) | ❌ | Le flux est mono-adresse strictement |
| Watchlist + alertes | ⚠️ | Le setting Notifications le mentionne (« Zones surveillées ») mais rien n'existe côté /zone |
| Traçabilité des sources | ⚠️ | `.meta` affiche GPS/INSEE/date ; pas de panneau « provenance » par aléa |
| Mode « check sinistre » rapide | ❌ | Pas de variante allégée du diagnostic |

---

## 4. Design frontend — la vue « Assurance »

### 4.1 Carte de décision (nouveau composant `UnderwritingCard`)

En tête de l'étape Cartographie **quand le profil = assurance**, remplacer le
bloc « Bandes D03 + aléas » par une carte type fiche de souscription :

- Verdict condensé : score /100, bande D03, badge « Acceptable / À
  expertiser / Refus possible » (règle configurable).
- Aléas présents sous forme de **pills** (flood · retrait-gonflement · feu) —
  réutiliser `AleaCard` mais compact.
- Bloc « Historique CatNat » en **timeline** (année → événement → arrêté),
  cliquable pour ouvrir la fiche Géorisques.
- **Actions** : « Copier la synthèse » (texte prêt à coller dans le fichier
  client) · « Exporter le rapport » (PDF compagnie) · « Ajouter à la
  watchlist ».
- `meta` de provenance conservé, augmenté d'un lien « Sources détaillées ».

### 4.2 Horizon temporel (toggle 2026 / 2050 / 2100)

- Un `md-segmented-button` dans la carte de décision.
- Le score et la bande D03 se recalculent selon la trajectoire (le backend
  expose déjà les aléas ; à compléter par des projections Copernicus — le
  champ `copernicus: false` existe déjà dans `/diagnostic/fast`, c'est le bon
  crochet).
- Chaque horizon affiche sa date de référence dans le `meta` — *trace
  d'audit*.

### 4.3 Tableau de bord portefeuille (nouveau composant `PortfolioDashboard`)

Nouvelle étape (ou nouvel écran `/portfolio`) accessible depuis la sidenav
**uniquement en profil assurance** :

1. Import CSV/GeoJSON (adresses + option valeur assurée).
2. Diagnostic par lot (boucle sur `/diagnostic/adresse`, throttled, avec
   progression — réutiliser le cache local `diagnosticCache` pour ne pas
   refacturer).
3. Vue agrégée : histogramme des bandes D03, top communes exposées, somme des
   valeurs assurées par bande, biens « à réviser » (score ≥ seuil).
4. Carte de chaleur du portefeuille (Mapbox : points colorés par bande —
   réutiliser `UnifiedMap` en mode points).
5. Export CSV/XLSX du tableau + PDF synthèse.

### 4.4 Watchlist & alertes (`WatchlistPanel`)

- Liste des communes/adresses suivies, persistée en `localStorage` (même
  pattern que `conversations.ts`).
- Badge dans la sidenav quand un nouvel arrêté touche une commune suivie
  (poll léger sur le backend ou check à l'ouverture).
- Raccorder les toggles existants de l'onglet Notifications à cette vraie
  donnée.

### 4.5 Rapport PDF « compagnie »

- Étendre `pdf-export.ts` avec un template assurance : logo, nom de la
  compagnie, n° de référence interne, verdict + score + bande + historique +
  synthèse IA, mention « ne remplace pas l'ERRIAL ».
- Un PDF par adresse, et un PDF de synthèse portefeuille.

### 4.6 Panneau provenance (`ProvenancePanel`)

- Pour chaque aléa : source (Géorisques, BRGM, DREAL…), date de génération,
  URL officielle. Plier/déplier dans la carte de décision.
- C'est ce qui rend le rapport « auditable » — argument de vente n°1 en
  assurance.

---

## 5. Architecture multi-profil (et comment rester simple)

### 5.1 Le profil vit dans le compte

- `mockUser.ts` : ajouter `profile: 'assurance' | 'banque' | 'promoteur'`.
- Onglet Compte (`SettingsPanel`) : un sélecteur « Métier / Profil » + le plan
  associé (cf. Billing : Pro 29 € → formule « Pro » devient « Promoteur »,
  ajouter « Assurance » et « Banque »).
- Persisté avec le thème (`useTyphoonTheme` ou nouveau `useUserProfile`).

### 5.2 Un moteur, des vues

- Le stepper `/zone` est **réordonné par profil** :
  - **Promoteur** (actuel) : Adresse → Carto → Analyse → Reco → Artisans → Rapport.
  - **Assurance** : Adresse → Carte de décision → Historique/timeline →
    Rapport (les étapes Reco/Artisans restent accessibles mais repliées).
  - **Banque** : Adresse → Conformité ERRIAL → Rapport officiel.
- Implémentation minimale : une table `STEP_ORDER[profile]` dans `Zone.tsx`
  (pas de routes parallèles). Les composants existants (`AleaCard`,
  `BuildingFiche`, `ZoneRecommendations`, `ZoneArtisans`) sont **réutilisés
  tels quels** ; seuls l'ordre et la mise en avant changent.

### 5.3 Sidenav par profil

- `ZoneSidenav.tsx` : les entrées de navigation dépendent du profil —
  « Portefeuille » et « Watchlist » en assurance, « Projets » en promoteur,
  « Dossiers » en banque.
- Le reste (historique, thème, compte) est partagé.

### 5.4 Feature flags

- Une simple map `FEATURES[profile]` (ex. `portfolio`, `watchlist`,
  `horizon`, `artisans`) pilotée par le profil — pas de branching dans les
  composants.

---

## 6. Feuille de route

### Phase A — Socle multi-profil (½ journée à 1 journée)

1. `mockUser.ts` : champ `profile` + sélecteur dans l'onglet Compte.
2. `FEATURES[profile]` + `STEP_ORDER[profile]` dans `Zone.tsx` (le promoteur
   ne voit aucune différence).
3. Sidenav : entrées conditionnelles.
4. Typecheck + test manuel des 3 profils sur `/zone`.

**Livrable :** l'app ne change pas visuellement pour le promoteur, mais
l'architecture accueille les profils.

### Phase B — Vue assurance minimale (2 à 3 jours)

5. `UnderwritingCard` : verdict, pills d'aléas, timeline CatNat, « Copier la
   synthèse », provenance repliable.
6. Bouton « Exporter PDF » branché sur un template compagnie (`pdf-export.ts`).
7. Toggle horizon 2026/2050/2100 (appel `copernicus: true` derrière, fallback
   gracieux si le backend ne renvoie pas de projection).
8. Watchlist + badge d'alerte (localStorage + check arrêtés).

### Phase C — Portefeuille (3 à 5 jours)

9. `PortfolioDashboard` : import CSV, diagnostic par lot (cache), histogramme
   D03, top communes, carte de chaleur, exports.

### Phase D — Vues banque & promoteur affinées (1 à 2 jours)

10. Banque : étape « Conformité ERRIAL » (lien direct vers le PDF officiel,
    checklist réglementaire) — surtout de la mise en forme de données déjà
    présentes.
11. Promoteur : rien à faire (c'est le flux actuel) — éventuellement mettre en
    avant « Vue d'ensemble des recommandations »
    (`RecommendationsOverview`).

---

## 7. Ce qui est volontairement hors périmètre (pour l'instant)

- **Modèle de pricing** (prime calculée) : nécessite l'actuariat + historique
  de sinistres — c'est un produit, pas une UI. Typhoon fournit l'input de
  risque, pas la prime.
- **API publique documentée** pour intégration aux systèmes de
  souscription : le setting « Clé API » existe déjà en UI
  (`SettingsPanel` → Sécurité), mais un vrai portail API (clés, quotas,
  webhooks, doc OpenAPI) est un chantier séparé — fortement recommandé après
  la Phase C, car les assureurs intégreront Typhoon dans leurs outils
  internes plutôt que de naviguer dans l'app.
- **Multi-utilisateurs / rôles d'équipe** (souscripteur vs gestionnaire) :
  nécessaire en production, mais bloque l'UX seule — le mock utilisateur
  reste mono-poste.

---

## 8. Résumé exécutif

1. **Ne rien casser** : le flux promoteur actuel (Reco → Artisans) est le
   différenciateur ; il reste la vue par défaut.
2. **Une seule brique** : le diagnostic mono-adresse ; l'assureur reçoit une
   **carte de décision** + **horizon climatique** + **provenance**, c'est-à-
   dire de quoi justifier une décision de souscription.
3. **La vraie nouveauté assurance = le portefeuille** (CSV → tableau de
   bord → carte de chaleur) et la **watchlist** ; c'est ce qui transforme un
   outil de diagnostic en outil de gestion.
4. **La banque est du marketing déguisé en feature** : le rapport ERRIAL
   officiel existe déjà ; une checklist conformité suffit.
5. **Architecture** : profil dans le compte → ordre du stepper + features
   pilotés par une table — pas de code dupliqué par profil.
