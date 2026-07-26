# Jumeau numérique 3D — front de test

Front minimal et autonome pour tester la sortie du `digital_twin_agent`, indépendamment des parcours assurance/banque/immobilier. Un seul fichier HTML, aucune installation.

## Lancer

Ouvrir `index.html` directement dans le navigateur (double-clic). Les données mock sont embarquées dans la page — pas besoin de serveur.

Pour tester un autre diagnostic : utiliser le champ **"Charger un autre diagnostic (.json)"** en haut à gauche et sélectionner un fichier au format `exemple_diagnostic.json` (fourni dans ce dossier).

## Ce qui est branché

- **Géométrie paramétrique** : la maison est reconstruite à partir du bloc `geometry` (largeur/longueur, nombre d'étages, type de toiture — 2 pans / 4 pans-croupe / plat —, pente, sous-sol, garage, jardin, orientation). Rien n'est codé en dur, contrairement au prototype `docs/typhoon_site.html`.
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
