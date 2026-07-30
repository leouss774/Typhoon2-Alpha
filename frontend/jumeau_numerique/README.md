# Jumeau numérique 3D — front de test

Front minimal et autonome pour tester la sortie du `digital_twin_agent`, indépendamment des parcours assurance/banque/immobilier. Un seul fichier HTML, aucune installation.

## Lancer

Ouvrir `index.html` directement dans le navigateur (double-clic). Les données mock sont embarquées dans la page — pas besoin de serveur.

Pour tester un autre diagnostic : utiliser le champ **"Charger un autre diagnostic (.json)"** en haut à gauche et sélectionner un fichier au format `exemple_diagnostic.json` (fourni dans ce dossier).

## Ce qui est branché

- **Emprise au sol réelle** : quand le contrat contient un bloc `geometry.footprint` (polygone BDNB), le bâtiment est extrudé sur sa forme exacte — murs suivant chaque façade réelle, cour intérieure percée, multipolygone géré. Chaque arête est rattachée à sa zone cardinale (`murs_nord/sud/est/ouest`) d'après sa normale sortante, donc les 7 zones cliquables restent valides sur une forme en L, en U ou quelconque. L'orientation vient des coordonnées elles-mêmes : aucune rotation n'est appliquée dans ce mode.
- **Toiture adaptée à l'emprise** : toit-terrasse pour les immeubles, les toits plats et les emprises à cour intérieure ; sinon croupe obtenue en rentrant le contour (le contour rentré devient le faîtage), ce qui donne une toiture correcte sur un L ou un U. Repli automatique en terrasse si l'emprise est trop étroite pour la pente demandée.
- **Géométrie paramétrique (repli)** : sans `footprint`, la maison reste reconstruite en boîte à partir de `largeur_m` / `longueur_m` / `orientation_deg` et du reste du bloc `geometry` (étages, type de toiture, pente, sous-sol, garage, jardin). Rien n'est codé en dur, contrairement au prototype `docs/typhoon_site.html`.
- **Texture de matériau réel** : murs et toiture sont recouverts d'une texture procédurale choisie par le slug de matériau réel de la BDNB (`geometry.materiau_mur` / `materiau_toiture` — brique, pierre de taille, meulière, pan de bois, ardoises, tuiles, zinc, bac acier, végétalisé...). Un matériau non déterminé (valeur BDNB fréquente) reste un enduit neutre plutôt qu'une texture devinée. Cette couche est opaque et ajoutée **sous** le halo translucide de scan de risque déjà en place, sans y toucher : le rendu combine désormais un bâtiment texturé et le dégradé de couleur par zone.
- **Fenêtres réelles** : générées uniquement quand le DPE du bâtiment renseigne `l_orientation_baie_vitree` et `pourcentage_surface_baie_vitree_exterieur` (couverture DPE partielle — souvent absente, notamment sur les maisons individuelles anciennes). Seules les façades listées dans la donnée reçoivent des fenêtres ; leur nombre est dérivé du ratio réel de surface vitrée et d'une taille de fenêtre type (1,2 × 1,4 m, seule valeur assumée du calcul). Un espacement minimal empêche tout chevauchement, quelle que soit la longueur de façade. Quand la donnée manque, le panneau de zone affiche une note explicite plutôt que de laisser un mur sans fenêtre passer pour une information.
- **Porte d'entrée** : placée sur la façade estimée orientée vers la rue (`geometry.entree_facade`), au rez-de-chaussée. Cette estimation compare le point d'adresse géocodé au centroïde du polygone BDNB (voir README racine) — jamais une position arbitraire, mais jamais garantie non plus : sans adresse exploitable, aucune porte n'est modélisée.
- **Balcon** : ajouté seulement si `geometry.ouvertures.has_balcony` est réellement `true`. La BDNB ne précise pas sur quelle façade/étage : il est rattaché à la façade rue si elle a aussi des fenêtres réelles, sinon à la première façade vitrée connue — approximation assumée et documentée dans le code, pas une donnée par bâtiment.
- **7 zones cliquables** (`fondations`, `murs_nord/sud/est/ouest`, `toiture`, `sous_sol`) : couleur pilotée par `risque`, panneau de détail avec `alea_principal`, `justification`, `recommandations`.
- **Bascule 2025 / 2050** sur `projection_2050`.
- **Effets visuels pilotés par le score** (fonction de mapping pure `mapRiskToEffect`, voir `next steps/README_noeud_jumeau_numerique.md` §5) :
  - fondations → decal de fissures, opacité croissante par palier
  - sous_sol → montée d'eau simulée (plan animé) selon le risque inondation
  - toiture → décoloration/usure des tuiles
  - murs → auréoles d'humidité
- **Température 2050** affichée avec sa source (`climat_2050`, ex. Copernicus).
- **Panneau démo** : un slider par zone pour faire varier le score en direct et calibrer les seuils sans repasser par le pipeline (bouton "Réinitialiser" pour revenir aux valeurs du JSON chargé).

## Ce qui reste à faire

- Remplacer `exemple_diagnostic.json` par la sortie réelle de `POST /diagnostic` une fois `digital_twin_agent` branché (même contrat, voir README racine § *Jumeau numérique 3D — contrat de sortie*).
- Ajouter un fallback IA (LLM) pour compléter un champ `geometry` manquant, comme décrit dans la spec — non implémenté ici, ce front consomme le JSON tel quel.
