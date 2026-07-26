# Roadmap MVP — 2 semaines, périmètre région PACA

Ce document complète le README (architecture cible) avec un plan d'exécution resserré pour livrer un MVP démontrable en 2 semaines. Il ne remplace pas la roadmap long terme du README, il la priorise pour tenir le délai.

## Décision de cadrage

Pour tenir les 2 semaines, le MVP se limite à la région **Provence-Alpes-Côte d'Azur (PACA)** — la plus exposée aux risques climatiques (RGA/sécheresse, feux de forêt, inondation, submersion marine, canicule) — sur les départements suivants :

- 04 — Alpes-de-Haute-Provence
- 05 — Hautes-Alpes
- 06 — Alpes-Maritimes
- 13 — Bouches-du-Rhône
- 83 — Var
- 84 — Vaucluse

Ce cadrage géographique s'applique **uniquement aux jeux de données qu'il faut télécharger et stocker en local** pour la collecte de données. Les appels aux API live (BDNB, Géorisques v1, IGN Altitude, Open-Meteo, CATNAT) se font par adresse et n'ont besoin d'aucune restriction géographique dans le code : ils fonctionnent nativement pour n'importe quelle adresse française. La restriction PACA sert uniquement à réduire le volume de ce qui doit être téléchargé, indexé ou pré-chargé pour la démo.

## Ce qui est restreint à PACA, et ce qui ne l'est pas

| Donnée | Mode d'accès | Restriction PACA | Justification |
|---|---|---|---|
| DVF | Lookup local (fichier téléchargé) | Oui — 6 départements PACA uniquement | Le jeu national est volumineux ; inutile pour une démo régionale. |
| Copernicus (CDS) | API officielle, mais mise en cache locale après le premier appel | Oui — bounding box PACA uniquement | Le dataset couvre toute l'Europe ; les requêtes CDS étant asynchrones (file d'attente), on télécharge une seule fois une zone PACA plutôt que l'Europe entière. Remplace DRIAS (qui n'avait aucune API, téléchargement 100 % manuel). |
| BDNB | Live (`api.bdnb.io`), procédure en 2 appels (géocodage BDNB puis donnée par adresse exacte) | Non | L'appel live n'a besoin d'aucune restriction géographique : il fonctionne adresse par adresse, PACA ou non. |
| Open-Meteo Climate API | Live par coordonnées | Non | Un appel live par adresse n'a pas besoin de restriction géographique. |
| Géorisques v1, IGN Altitude, CATNAT | Live | Non | Toujours appelés en direct par adresse, quel que soit le périmètre géographique. |

En résumé : le code du `collector_agent` reste générique France entière ; seul le fichier de lookup DVF et le cache régional Copernicus sont filtrés/bornés à PACA.

## Plan jour par jour

### Semaine 1 — Fondations & collecte

**J1 — Cadrage et scaffolding**
- Geler le périmètre : PACA + un seul cas d'usage démontré (assurance, qui dispose déjà d'un prototype front).
- Scaffolder le repo : backend FastAPI, arborescence `agents/`, `connectors/`, frontend `assurance/` initialisé à partir du prototype existant (`docs/typhoon_site.html`).
- Définir le schéma `TyphoonState` minimal : `building_data`, `risk_scores`, `recommendations`, `digital_twin`.

**J2 — `collector_agent` (API live)**
- Implémenter les connecteurs live : BDNB, Géorisques v1, IGN Altitude, Open-Meteo, CATNAT.
- Constituer un jeu de test de 6 adresses réelles, une par département PACA (ex. Marseille 13, Nice 06, Avignon 84, Toulon 83, Gap 05, Digne-les-Bains 04), et mettre leurs réponses en cache pour sécuriser la démo contre la latence/quotas API.

**J3 — Lookups locaux restreints à PACA**
- Télécharger et filtrer DVF sur les 6 départements PACA uniquement.
- Lancer le téléchargement Copernicus (CDS) une fois sur la bounding box PACA et le mettre en cache local.
- Livrer `lookup/departments.json` (DVF) et le cache `data/lookup/copernicus/` en version PACA.

**J4 — `scoring_agent` (v1 à base de règles)**
- Modèle de scoring par règles pondérées (pas de ML pour le MVP), calibré sur les aléas dominants en PACA : RGA/sécheresse, inondation, feux de forêt, submersion marine, canicule.
- Valider les scores obtenus sur les 6 adresses de test.

**J5 — Checkpoint interne**
- Test bout en bout `collector_agent` → `scoring_agent` sur les 6 adresses.
- Jour tampon pour absorber le retard de J2-J4 avant d'attaquer le RAG.

### Semaine 2 — RAG, jumeau numérique, intégration

**J6-J7 — `rag_agent`**
- Ingestion documentaire restreinte aux 3 sources prioritaires : MRN (intégral), BRGM (sécheresse/RGA), CEPRI (inondation). ADEME, CCR, ANAH, AQC et France Assureurs sont reportés post-MVP.
- Pipeline retrieval + génération, prompt système aligné sur le parcours assurance.

**J8 — `digital_twin_agent` (contrat 3D, version simplifiée)**
- Géométrie par templates prédéfinis (3 à 4 formes selon type de bien / nombre d'étages issus du formulaire) plutôt qu'un générateur paramétrique complet, pour réduire le risque technique côté Three.js.
- Assemblage du contrat JSON (`geometry` + `zones` + `projection_2050`) à partir des sorties de `scoring_agent` et `rag_agent`.

**J9 — Intégration frontend**
- Remplacer `MOCK_DATA` du prototype par un appel réel à `POST /diagnostic`.
- Adapter `house-scene.js` pour lire le bloc `geometry` du contrat (même en version templates).
- Rebrancher le parcours complet : formulaire → écran de traitement → scène 3D.

**J10 — Devis, tests de bout en bout, polish**
- Logique de devis simplifiée à base de règles (score avant/après travaux, pourcentage de prime).
- Tests de bout en bout sur les 6 adresses PACA + quelques adresses additionnelles.
- Corrections de bugs, finitions UI, préparation de la démo.

## Hors périmètre du MVP (explicitement reporté)

- Couverture nationale (hors PACA) pour les données à télécharger localement.
- Cas d'usage banque et agents immobiliers : seul le parcours assurance est démontré à J10 ; les routes API des deux autres restent des stubs.
- Génération paramétrique complète de la géométrie 3D (formes complexes, combles, extensions) : templates simplifiés pour le MVP.
- Ingestion complète des 8 sources documentaires RAG : seules MRN, BRGM, CEPRI en semaine 2.
- Authentification, gestion multi-utilisateurs, persistance long terme : un mode démo suffit.
- Règles métier d'écartement client selon un seuil de risque : affichage du score uniquement, pas de décision automatisée.

## Risques et mitigations

- Quotas ou latence des API BDNB/Géorisques pendant la démo → mise en cache des réponses des adresses de démo dès J2.
- Générateur 3D paramétrique trop ambitieux pour 10 jours → repli sur des templates de géométrie fixes (J8).
- Ingestion documentaire RAG plus longue que prévu → repli sur la seule source MRN si nécessaire.
- Dérive de périmètre vers les 3 cas d'usage → un seul cas d'usage (assurance) est démontré à J10.

## Critères de succès à J10

- Un utilisateur saisit une adresse réelle d'un département PACA.
- Le diagnostic tourne de bout en bout à travers les 4 agents en un temps raisonnable pour une démo live.
- La scène 3D affiche une maison avec des zones colorées selon le score réel, plus de `MOCK_DATA`.
- Chaque zone à risque affiche au moins une recommandation sourcée (MRN, BRGM ou CEPRI).
- Le module de devis calcule une réduction de prime indicative selon les travaux sélectionnés.
