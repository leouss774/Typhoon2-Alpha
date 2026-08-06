# 🎯 Améliorations UX — Jumeau Numérique Typhoon

> Document de recommandations UX pour `frontend/jumeau_numerique/index.html`  
> Généré suite à l'audit complet de l'interface

---

## 1. 🔥 Climat — Simplifier la métrique canicule

**Problème :** La carte climatique affiche actuellement 4 métriques dans une grille 2×2 :
- Pic de chaleur max (🌡️)
- Précipitations (🌧️)
- **Jours canicule/an** (🔥)
- Sources

**Recommandation :**  ne garder que **la projection température 2050** qui est la métrique la plus parlante et immédiatement compréhensible par l'utilisateur.


## 2. 🏠 Page d'accueil (Home) 

- **Animation au scroll** : les sections apparaissent en fondu/défilement au lieu d'arriver brutalement

## 4. 🎮 Scène 3D — Interactions et retours utilisateur

**Problème :** La scène Three.js est riche mais les zones cliquables manquent de feedback visuel avant clic.

**Suggestions :**
- **Curseur personnalisé** : changer le curseur en `pointer` au survol d'une zone cliquable
- **Effet de glow/highlight** : la zone survolée s'illumine légèrement
- **Animation au clic** : la zone sélectionnée pulse ou se soulève de 2-3 px
- **Tooltip** : au survol prolongé (>1s), afficher le nom de la zone et son niveau de risque dans une infobulle flottante
- **Légende de couleurs en pied de scène** : rappeler la correspondance couleur ↔ niveau de risque (vert=faible → rouge=critique)

---

## 5. 📊 Panneau d'info (#info-panel) — Améliorer la lisibilité

**Problème :** Le panneau latéral droit est dense et le contenu peut devenir écrasant.

**Suggestions :**
- **Ajouter un filtre par niveau de risque** : boutons "Tous" / "Critique" / "Élevé" / "Modéré" en haut du panneau
- **Scores avec barres de progression** : remplacer le texte brut par des barres colorées (ex: `████████░░ 75/100`)
- **Regrouper les recommandations par type de travaux** : isolation, structure, étanchéité, etc.
- **Ajouter un total estimé des travaux** en bas du panneau avec fourchette de prix cumulée
- **Bouton "Exporter en PDF"** : générer un rapport synthétique du diagnostic

---

## 6. 💬 Chat IA — Plus proactif et contextuel

**Problème :** Le chat assistant est passif — l'utilisateur doit cliquer et poser une question.

**Suggestions :**
- **Message d'accueil proactif** : dès l'ouverture, le bot dit "Bonjour ! Je peux vous expliquer les risques de votre bien ou vous suggérer des travaux."
- **Suggestions contextuelles** : les chips en bas du chat devraient changer selon la zone sélectionnée
  - Si l'utilisateur clique sur "Toiture" → chips : "Quels travaux ?" / "Quel budget ?" / "Quelles aides ?"
- **Historique persistant** : garder les messages même après fermeture/ouverture du chat
- **Brancher une vraie API RAG** (déjà existante dans `backend/app/recommandations/rag_engine.py`)

---

## 7. 🕹️ Panneau démo (sliders) — Rendre la calibration plus intuitive

**Problème :** Les sliders de calibration sont techniques et peu visibles.

**Suggestions :**
- **Mode "expert" caché** : déplacer le panneau démo dans un tiroir avec un bouton "⚙ Mode calibration"
- **Presets** : ajouter des boutons "Risque min", "Risque max", "Moyenne PACA" pour réinitialiser rapidement
- **Aperçu en direct** : dès qu'on bouge un slider, la scène 3D se met à jour en temps réel (déjà partiellement implémenté)
- **Valeurs par défaut + historique** : pouvoir comparer avec les valeurs initiales du JSON chargé

---
---

---

## 10. 🗺️ Carte explorateur de zones (#zone-modal) — Améliorations

- **Marqueur "Vous êtes ici"** si la localisation du navigateur est autorisée

---

---

## 14. 🔧 Correctifs rapides & bugs UX

| # | Problème | Solution |
|---|----------|----------|
| 1 | La scène 3D a un `cursor: grab` même quand on ne peut pas interagir | Réserver ce curseur aux moments où la scène est active |
| 2 | Le panneau `#climat-panel` est en `display: none` par défaut mais n'a pas de déclencheur visible | Ajouter un bouton "Climat 2050" dans le toggle-panel |
| 5 | Le chargement de JSON externe n'a pas de feedback d'erreur clair si le format est invalide | Ajouter un message d'erreur explicite "Format JSON invalide, vérifiez le fichier" |
| 6 | la partie concernant le formulaire est inutilisée | Supprimer tout le bloc HTML #form-screen (lignes ~1096-1138)

Supprimer le CSS #form-screen / #form-card / .form-grid etc. (lignes ~503-569)

Supprimer le JS mort : openDiagnosticForm(), les écouteurs, formScreen, form, etc.
