# Nœud Jumeau Numérique — Spécification

## Référence visuelle

Regarde `typhoon_site.html` pour te faire une idée du rendu attendu côté frontend (écran du diagnostic climatique). L'esprit à garder pour la scène 3D : un **effet transparent / holographique** — pas une maison "pleine" et opaque, mais quelque chose qui évoque un scan numérique du bien (matériaux semi-transparents, contours lumineux type wireframe, teintes bleutées/cyan). C'est ce rendu qui doit ensuite accueillir les fissures et l'eau décrites plus bas.

---

## 1. Ce que ce nœud doit produire

Le contrat de sortie est un **schéma JSON strict** que le code Three.js consomme tel quel, sans transformation supplémentaire côté frontend. Champs attendus :

- `footprint` : coordonnées du polygone au sol (ou plus simple : largeur / longueur / rotation si on simplifie en boîte rectangulaire)
- `hauteur_totale_m`, `nombre_niveaux`
- `hauteur_sous_plafond_m` (pour découper les étages dans Three.js)
- `type_toiture` (2 pans, 4 pans/croupe, toit plat, mansardé…) + `pente_toit_deg`
- `orientation_deg` (pour orienter la maison correctement selon le cadastre)
- `materiau_mur`, `materiau_toiture` (pour choisir la texture)
- `presence_sous_sol` (bool)

Merci de ne pas dévier de ce schéma sans nous prévenir — c'est ce qui découple ton nœud du reste du pipeline (l'orchestrateur et le frontend s'appuient dessus tel quel).

---

## 2. D'où viennent les vraies valeurs

Tout est **déterministe**, récupéré via API — pas de génération IA à ce stade :

- **BDNB (Base de Données Nationale des Bâtiments, CSTB)** : source principale. Propose une API donnant un accès direct aux données géospatiales des bâtiments — morphologie en volumes 2.5D, surfaces, hauteurs, topologie des faces. Elle fournit : hauteur, nombre de niveaux (dérivable), année de construction, matériaux, et même des zonages de risques argiles déjà précalculés (à recouper avec ce que sort le nœud analyse).
- **IGN BD TOPO / Géoplateforme (couche bâtiment)** : donne le polygone au sol précis du bâtiment, utile si la BDNB ne suffit pas ou pour croiser/valider.
- **Base Adresse Nationale (BAN)** : géocode l'adresse saisie dans le formulaire en coordonnées précises, indispensable en amont pour requêter les bases ci-dessus.
- **Cadastre (API Carto)** : parcelle + emprise bâtie, en fallback.

---

## 3. Le calcul géométrique (partie déterministe)

Une fois le polygone au sol récupéré :

1. Calculer son **rectangle englobant minimal** (minimum bounding rectangle) → donne directement longueur, largeur, angle de rotation, les 3 paramètres dont Three.js a besoin pour extruder une boîte plutôt que de gérer un polygone complexe.
2. Hauteur totale (BDNB) divisée par une hauteur d'étage type (~2,5–3 m) → donne le **nombre d'étages** si l'attribut n'est pas fourni directement.
3. Le type de toiture est le point le plus dur à obtenir en donnée brute : à défaut, on récupère l'info directement dans le formulaire, sinon **fallback par défaut régional/typologique** (toit à 2 pans par défaut pour une maison individuelle, ajusté si "époque de construction" + région suggèrent autre chose).

---

## 4. Rôle de l'IA dans ce nœud

Ce nœud devient un vrai agent (et pas un simple script) uniquement à cet endroit : **quand une donnée manque** (couverture BDNB incomplète, valeur nulle ou aberrante), au lieu de planter ou de mettre une valeur par défaut arbitraire, on demande à un LLM de **compléter le paramètre manquant avec une valeur plausible**, en lui donnant tout le contexte déjà connu (région, année de construction, type de bien déclaré dans le formulaire — "maison individuelle", "longère"…), et en le forçant à répondre dans le schéma JSON exact (sortie structurée). Usage d'IA très ciblé : pas de créativité, juste de la complétion contrainte.

---

## 5. Agent projection 2050 — effets visuels sur le jumeau

Le score de risque (sorti par le nœud analyse) doit être un **paramètre d'entrée direct** de la scène 3D, pour piloter des effets visuels sur le jumeau numérique lui-même.

### Table de correspondance risque → effet

| Zone | Effet visuel |
|---|---|
| Fondations (risque argiles/tassement) | Intensité de fissures (0 à 100%) |
| Zone inondable / proximité rivière | Hauteur du niveau d'eau simulé autour du bien |
| Toiture (canicule/tempête) | Optionnel — tuiles manquantes ou décoloration |
| Murs/façade | Optionnel — auréoles d'humidité |

Pour chaque type, définir des **paliers** (ex : score 0–30 → aucun effet, 30–60 → effet léger, 60–100 → effet marqué).

À afficher également sur le côté de la scène : la **température maximale projetée en 2050**, avec la source précisée (**Copernicus**) pour la crédibilité du chiffre affiché.

### Comment fabriquer chaque effet

**Fissures sur les fondations**
Option simple (rapide, adaptée au hackathon) : une texture de fissure (décalque/decal) plaquée sur le mesh des fondations, dont l'**opacité** est pilotée par le score. Score bas = decal invisible, score haut = decal bien visible ; possibilité de superposer plusieurs decals pour un effet "plus fissuré".

**Montée des eaux**
Un plan (mesh plat semi-transparent, couleur eau) positionné autour de la maison, dont la **hauteur (position Y)** est interpolée entre 0 et une hauteur max en fonction du score d'inondation. Ajouter une légère animation (ondulation via shader simple, ou oscillation sinusoïdale de la hauteur) pour éviter l'effet "plaque plate figée".

### Étape 3 — Fonction de mapping (déterministe, pas un agent)

Fonction pure : prend `(type_de_zone, score)` en entrée, retourne les paramètres visuels (opacité fissure, hauteur eau, etc.) selon la table ci-dessus. Elle doit être appelée dès que le JSON fusionné arrive côté frontend, **avant** la construction de la scène — donc juste après le fetch de l'orchestrateur et avant l'appel qui construit les meshes.

### Étape 4 — Intégration dans la séquence de construction de la scène

Ordre logique dans le code Three.js :
1. Construire la géométrie de base (footprint, hauteur, toiture… fournis par ce nœud)
2. Nommer chaque mesh par zone (`fondations`, `toiture`…) — nomenclature commune avec le nœud analyse
3. **Nouvelle étape** : pour chaque mesh, appeler la fonction de mapping avec le score correspondant, et appliquer le résultat (decal de fissure, opacité, hauteur du plan d'eau…)
4. Puis seulement après, brancher l'interactivité existante (clic sur zone → panneau d'info)

### Étape 5 — Mode démo/réglage

Le `#toggle-panel` de test déjà présent dans le HTML doit être conservé pendant le développement : un slider ou des boutons qui font varier artificiellement le score d'une zone, pour voir l'effet visuel réagir en direct sans repasser par tout le pipeline IA à chaque fois. Ça permet de calibrer les seuils (à quel score les fissures deviennent "inquiétantes", à quelle hauteur l'eau devient "alarmante").

### Étape 6 — Séparation des responsabilités

Cet ajout ne touche à aucun des 3 nœuds IA existants (analyse, RAG recommandations, jumeau numérique) — c'est une couche purement de rendu, en aval de la fusion faite par l'orchestrateur. Argument pour la soutenance : "nos agents produisent un score de risque explicable, et notre couche de rendu 3D transforme ce score en signal visuel immédiat" — une architecture propre où l'IA reste responsable du diagnostic, pas de la mise en scène.
