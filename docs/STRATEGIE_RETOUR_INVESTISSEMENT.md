# Stratégie « Coût des travaux de résilience vs. gain économique » — version honnête et sourcée

Statut : **implémenté dans `backend/app/economie/`** (module + endpoint `POST /diagnostic/retour-investissement` + tests verts). Ce document reste le référentiel méthodologique : toute modification de formule doit s'accompagner d'une mise à jour ici et de la source correspondante.

Objectif : répondre à « si j'évite le risque climatique par des travaux, combien de coût je gagne ? » avec des chiffres **honnêtes**, c'est-à-dire chacun **tracé vers sa source** (papier de recherche, référentiel officiel ou donnée réelle du projet) — jamais inventé.

---

## 1. Principe d'honnêteté (contrainte absolue)

La règle du projet « aucune donnée simulée » (docs/GUIDE_ORCHESTRATEUR_API.md) s'étend au volet économique. Donc :

1. **Aucun montant inventé.** Chaque € affiché est le produit d'une formule documentée appliquée à des entrées réelles ou référencées.
2. **Trois statuts de sortie** seulement :
   - `calcule` — entrées réelles (DVF, CATNAT, scores, `cout_estime` sourcé) + formule référencée ;
   - `fourchette` — bornes issues d'une source publiée, hypothèses affichées, analyse de sensibilité ;
   - `null` — aucun input disponible → **on n'affiche pas de chiffre**.
3. **Tracabilité** : chaque paramètre porte sa référence (`sources: [...]`) dans le contrat JSON de sortie.
4. **`confidence` séparé** : solidité du résultat économique, indépendant du score de risque (même philosophie que `risk_model._compute_confidence`).
5. Le calcul économique est **déterministe et testable** — aucun LLM dans les montants (le LLM n'intervient que pour la sélection de mesures, déjà sourcées).

---

## 2. Méthode retenue — trois niveaux en cascade

| Niveau | Produit | Fiabilité | Statut d'affichage |
|---|---|---|---|
| A. Effet des travaux sur le risque | Δ score par zone (0–100) | déterminisme pur (risk_model existant) | `calcule` |
| B. Gain économique assurantiel/réglementaire | € précis (franchise, surprime, subventions, sinistre moyen évité) | chiffres officiels publiés | `calcule` / `fourchette` |
| C. Perte annuelle moyenne (AAL) — méthode académique | €/an de dommages évités (inondation principalement) | méthode de référence, entrées partiellement disponibles | `fourchette` + sensibilité |

Niveau A prouve **l'effet** des travaux, B donne le **gain en € vérifiable**, C donne le **dommage moyen évité** par la méthode scientifique de référence. La valeur à la revente n'est **pas** mise en avant (voir 3.5 : la littérature ne permet pas un % fiable en France).

---

## 3. Le processus et la source de chaque paramètre

### 3.1 Valeur du bien (ancre en €)

- **Valeur de reconstruction** = `surface_m2` (géométrie BDNB, `geometry_builder`) × coût de construction €/m².
  - Repli honnête (implémenté) : **médiane du prix au m² des ventes réelles** collectées par `collector_agent` (`building_data.dvf_local`, voir `valuateur.py` — ventes `Maison`/`Appartement`, surface plancher ≥ 9 m², prix au m² écrêté) × surface, marqué « valeur de marché, pas valeur de reconstruction ».
  - Si ni DVF ni coût de construction n'est disponible → `null` (pas de valeur de reconstruction → pas de montant en €, seulement le Δ de score du niveau A).

### 3.2 Niveau A — Effet des travaux (déterministe, existant)

- Ré-appeler `compute_risk_scores` (backend/app/scoring/risk_model.py) avec la mesure appliquée : chaque mesure est mappée au paramètre F ou V qu'elle modifie (ex. drainage périphérique → V fondations ; batardeaux/clapet anti-retour → F inondation ; écran racinaire → F RGA).
- Gain = Δ score (0–100) par zone → remplace le `gain_resilience` codé en dur du front (frontend/jumeau_numerique/typhoon_site.html:959-986).
- Efficacité des mesures : taux et coûts tirés des référentiels **MRN** (voir 3.4) ; sans source → pas de taux appliqué.

### 3.3 Niveau B — Gains assurantiels / réglementaires (chiffres officiels)

| Paramètre | Valeur | Source (vérifiée) |
|---|---|---|
| Franchise légale de sinistre (aléas courants) | **380 €** | Code des assurances art. D.125-5 — synthèse georisques.gouv.fr (màj 2024) |
| Franchise légale RGA | **1 520 €** | Code des assurances art. D.125-5 — georisques.gouv.fr (màj 2024) |
| Surprime CatNat | **12 % → 20 %** au 1/1/2025 | Arrêté du 28/12/2023, presse.economie.gouv.fr |
| Modulation future de franchise/surprime selon prévention | — (cadre) | Rapport Lavarde « Le régime CatNat : prévenir la catastrophe financière », Sénat r23-603 (mai 2024) ; PPL adoptée au Sénat le 29/10/2024 |
| Subvention FPRNM (fonds Barnier) — habitation | **80 %**, plafond **36 000 €** et 50 % valeur vénale | Plaquette FPRNM DDT de l'Ain (habitat) |
| Coût moyen d'un sinistre RGA | **16 500 €** | ecologie.gouv.fr (source : Cour des Comptes) |
| Coût moyen sinistre RGA (variante CCR) | **21 000 €** / maison (1990–2015) | CCR, cité SDES « Chiffres clés des risques naturels 2023 » |
| Coût moyen indemnisation CatNat | **10 900 €** (1989–2002), **10 200 €** (2003), **17 800 €** (procédure exceptionnelle) | BRGM RP-56771-FR (P. Plat), données CCR |
| Reprise en sous-œuvre (micropieux, injection) | **10 000–70 000 €** | Arbizzi & Kreziak (2009), annexe BRGM RP-56771-FR (projet ANR-ARGIC) |
| Probabilité de sinistre | fréquence réelle des arrêtés CATNAT de la commune | données CATNAT collectées par `collector_agent` (georisques.gouv.fr) |

Formule B (par zone/risque traité) :
```
Bénéfice_assurance = P_sinistre × (coût_moyen_sinistre_évité − franchise_évitée)
                     + surprime_modulée_économisée (cadre réglementaire, à venir)
Coût_net_travaux    = Σ cout_estime (sourcé index RAG) × (1 − subvention_FPRNM)
```
Le **coût des travaux** (`cout_estime`) est déjà garanti non inventé : `recommandations/service.py` recopie intégralement les fiches (MRN/BRGM/CEPRI/ADEME…) et renvoie `null` si aucune fiche ne fournit de coût.

### 3.4 Niveau C — Perte Annuelle Moyenne (AAL), méthode académique de référence

**Formule d'annuelisation** (approximation par classes de probabilité de dépassement) :

```
AAL ≈ (10%−4%)·(L10+L4)/2 + (4%−2%)·(L4+L2)/2 + (2%−1%)·(L2+L1)/2
    + (1%−0,2%)·(L1+L0,2)/2 + 0,2%·L0,2
```
avec `Lp = %dommage(profondeur_p) × valeur_de_reconstruction` (courbe profondeur-dommage).

Sources de chaque élément :

| Élément | Source (vérifiée) | Utilisation honnête |
|---|---|---|
| Formule d'annuelisation (annualized loss) | **FEMA (2018)**, *Guidance for Flood Risk Analysis and Mapping* — §Flood Risk Assessment | formule littérale |
| Courbes profondeur-dommage (résidentiel) | **USACE EGM 01-03 (2001)**, *Generic Depth-Damage Relationships* | courbes génériques calibrées sur sinistres réels US (à adapter avec réserve en France) |
| Méthode par distribution de Gumbel + intégration trapézoïdale, AAL par bâtiment | **Gnan, Friedland, Rahim, Mostafiz et al. (2022)**, Front. Water 4:919726, DOI 10.3389/frwa.2022.919726 | méthode ; exemples illustratifs US (cas unique, à ne pas transposer tel quel) |
| Ordre de grandeur AAL en zone A (zone inondable 100 ans) | **Al Assi, Mostafiz, Friedland & Rohli (2024)**, Int. J. Environ. Res. 18(2), DOI 10.1007/s41742-024-00577-7 | fourchette médiane **0,47–0,98 %** de la valeur de remplacement / an |
| Exemple bénéfice de rehaussement | **Gnan et al. (2022)** : 1 ft ≈ **1 000 $/an**, 4 ft ≈ **2 000 $/an** | chiffre illustratif US, affiché comme tel, jamais comme référence française |
| Cadre d'analyse coûts-bénéfices ex-ante (adaptation) | **Campos Rodrigues et al. (2026)**, *Critical Insights in Climate Change* 2(1), DOI 10.1080/29931495.2025.2590372 | baisse d'AAL = bénéfice vs coût d'implémentation (NPV, discount 3 %, maintenance 1 %) |
| Coûts / efficacité des mesures de prévention (inondation) | **MRN / France Assureurs**, *Référentiels de résilience du bâti aux aléas naturels* (2024) | coûts et taux d'efficacité réels par mesure |
| Coûts d'adaptation RGA (solutions horizontales) | **MRN (2023)**, guide adaptation-réhabilitation RGA (ecologie.gouv.fr) | ex. écran racinaire/bordure **2–5 k€ HT** ; gouttières/descentes **1 000 € HT** |

**Limite honnête assumée** : la profondeur d'inondation par scénario (input du AAL) n'est **pas disponible par adresse** dans le projet (pas de modèle hydraulique). → En l'absence de cote, on n'invente **pas** de profondeur : on affiche soit la fourchette publiée d'AAL en zone inondable (0,47–0,98 % de la valeur/an), soit `null` avec la raison. Le jour où une profondeur réelle est disponible (PPRI/cote), la formule complète s'exécute.

### 3.5 Valeur immobilière — non affichée comme fait certain (décision honnête)

La littérature existe mais ne permet **pas** un % de décote fiable et transposable en France :

| Source (vérifiée) | Résultat | Réserve |
|---|---|---|
| **Bernstein, Gustafson & Lewis (2019)**, J. Financial Economics 134(2) 253-272, DOI 10.1016/j.jfineco.2019.03.013 | décote **~7 %** (exposé élévation du niveau de la mer), **~4 %** même inondation lointaine | US, zones côtières, élévation du niveau de la mer uniquement |
| **Baldauf, Garlappi & Yannelis (2020)**, Rev. Financial Studies 33(3) 1256-1295, DOI 10.1093/rfs/hhz073 | écart **~7 %** entre quartiers « croyants » et « sceptiques » | décote liée aux *croyances*, pas un risque objectif |
| **Foerster, Ryan & Scheid (2025)**, ECB WP 3059, DOI 10.2866/3583063 | pénalité sur l'immobilier commercial exposé, croissante 2007–2023 | qualitatif/relatif, pas de % unique |
| **Clayton, Devaney, Sayce & Van de Wetering (2021)**, J. Portfolio Management 47(10), DOI 10.3905/jpm.2021.1.278 | synthèse : décote post-événement **modeste et temporaire** ; effets de long terme incertains | recommandation : ne pas afficher de % de décote comme certain |

**Décision** : le gain de valeur à la revente est présenté **qualitativement** (liste des études + fourchettes littérature avec leurs limites), jamais intégré dans le ROI chiffré.

---

## 4. Sources vérifiées 

**Papiers de recherche :**
1. Bernstein, A., Gustafson, M., Lewis, R. (2019). *Disaster on the Horizon: The Price Effect of Sea Level Rise.* J. Financial Economics 134(2), 253-272. DOI 10.1016/j.jfineco.2019.03.013.
2. Baldauf, M., Garlappi, L., Yannelis, C. (2020). *Does Climate Change Affect Real Estate Prices? Only If You Believe In It.* Rev. Financial Studies 33(3), 1256-1295. DOI 10.1093/rfs/hhz073.
3. Foerster, K., Ryan, E., Scheid, B. (2025). *Pricing or panicking? Commercial real estate markets and climate change.* ECB Working Paper 3059. DOI 10.2866/3583063.
4. Clayton, J., Devaney, S., Sayce, S., Van de Wetering, J. (2021). *Climate Risk and Real Estate Prices: What Do We Know?* J. Portfolio Management 47(10), 75-90. DOI 10.3905/jpm.2021.1.278.
5. Gnan, E., Friedland, C., Rahim, M.A., Mostafiz, R.B., Rohli, R., Orooji, F., Taghinezhad, A., McElwee, J. (2022). *Improved building-specific flood risk assessment and implications of depth-damage function selection.* Frontiers in Water 4:919726. DOI 10.3389/frwa.2022.919726.
6. Al Assi, A., Mostafiz, R.B., Friedland, C., Rohli, R. (2024). *Theoretical Boundaries of Annual Flood Risk for Single-Family Homes Within the 100-Year Floodplain.* Int. J. Environ. Res. 18(2). DOI 10.1007/s41742-024-00577-7.
7. Campos Rodrigues, L., Riera-Spiegelhalder, M., Navarro, F., et al. (2026). *Hybrid adaptation to urban riverine floods: a cost-benefit analysis in Vilanova i la Geltrú (Spain).* Critical Insights in Climate Change 2(1). DOI 10.1080/29931495.2025.2590372.

**Documents institutionnels :**
8. FEMA (2018). *Guidance for Flood Risk Analysis and Mapping* — formule annualized loss. fema.gov.
9. USACE (2001). *Economic Guidance Memorandum 01-03, Generic Depth-Damage Relationships.* planning.erdc.dren.mil.
10. BRGM — P. Plat, *Impacts du changement climatique, adaptation et coûts associés en France pour le risque de sécheresse géotechnique*, RP-56771-FR (coûts RGA, données CCR).
11. CCR / SDES (2023). *Chiffres clés des risques naturels* (coût moyen sinistre RGA 21 000 € ; sinistralité sécheresse +30 %/+60 % à 2050).
12. MRN / France Assureurs (2024). *Référentiels de résilience du bâti aux aléas naturels.*
13. MRN (2023). *Prévention, adaptation, réhabilitation face au RGA* — coûts des mesures (ecologie.gouv.fr).
14. Arrêté du 28/12/2023 (surprime CatNat 12 %→20 %) ; Sénat, rapport Lavarde r23-603 (mai 2024) ; PPL adoptée 29/10/2024.
15. Code des assurances art. D.125-5 et suivants (franchises 380 € / 1 520 € RGA) — synthèse georisques.gouv.fr.
16. Plaquette FPRNM / fonds Barnier (subvention 80 %, plafonds 36 000 € / 50 % valeur vénale) — DDT de l'Ain.

---

## 4.1 Registre des formules — source exacte et adaptation faite

Pour chaque formule : la formule exacte, sa source (réf. du §4), et **l'adaptation** que nous faisons de la source vers notre contexte (donnée française, hypothèse, ou écart volontaire).

### F-A1 — Score de risque par zone (existant, aucun montant en €)
```
R = 100 × (F/100)^α × (V/100)^β        avec α = β = 0,5   (moyenne géométrique non compensatoire)
```
- **Source** : aucune source externe — c'est le moteur du projet (`backend/app/scoring/risk_model.py`).
- **Adaptation** : aucune. C'est la base des niveaux A/B/C ; le Δ de score après travaux devient le `gain_resilience` réel.

### F-B1 — Valeur de reconstruction (ancre en €)
```
V = S × c
S = surface_m2 (géométrie BDNB, réelle) ; c = coût de construction €/m²
```
- **Source** : méthode HAZUS (replacement cost = surface × coût unitaire) — FEMA, *Hazus 7.0 Flood Model Technical Manual* (2025) [réf. 8]. Le coût unitaire français n'y figure pas.
- **Adaptation (implémentée)** : le coût unitaire `c` de construction français (indice BT01 / INSEE, à ajouter en source) n'est **pas encore** intégré : l'implémentation actuelle (`valuateur.py`) utilise directement le **repli honnête** `V = prix_m2_median_DVF × S` (médiane DVF réelle du projet), affiché comme *valeur de marché, pas de reconstruction*. Si aucun des deux → `null`.

### F-B2 — Bénéfice assurantiel annuel (niveau B)
```
B_assu = p × (c_sin − f) + Δs
p    = probabilité annuelle de sinistre = fréquence CATNAT communale réelle (collector_agent)
c_sin = coût moyen d'un sinistre RGA = 16 500 € (Cour des Comptes) ou 21 000 € (CCR)
f    = franchise = 380 € (aléas courants) / 1 520 € (RGA) — code des assurances D.125-5
Δs   = modulation de surprime liée à la prévention (0 aujourd'hui, cadre Lavarde/PPL 2024)
```
- **Source** : aucun papier unique ne fournit cette combinaison — c'est une **construction du projet** à partir de paramètres officiels publiés (chacun cité).
- **Adaptation** : seules les valeurs France (CCR/Cour des Comptes) sont utilisées, pas les coûts moyens étrangers. `Δs` reste 0 tant que la modulation n'est pas en vigueur → affiché `cadre réglementaire à venir`, jamais chiffré.

### F-B3 — Coût net des travaux à charge
```
C_net = Σ c_i × (1 − r_sub)     borné par le plafond FPRNM (36 000 € et 50 % valeur vénale)
c_i   = cout_estime sourcé (fiches MRN/BRGM/CEPRI/ADEME, data/index.json)
r_sub = 80 % (habitation, fonds Barnier/FPRNM)
```
- **Source** : FPRNM — plaquette DDT (fond Barnier) [réf. 16] ; coûts des mesures : MRN [réf. 12, 13].
- **Adaptation** : on n'applique la subvention qu'aux mesures éligibles au FPRNM ; le plafond s'applique avant affichage du montant à charge.

### F-C1 — Perte Annuelle Moyenne (AAL) par classes de probabilité
```
AAL ≈ (10%−4%)·(L10+L4)/2 + (4%−2%)·(L4+L2)/2 + (2%−1%)·(L2+L1)/2
    + (1%−0,2%)·(L1+L0,2)/2 + 0,2%·L0,2
Lp = DDF(profondeur_p) × V    (DDF = courbe profondeur-dommage)
```
- **Source** : FEMA (2018), *Guidance for Flood Risk Analysis and Mapping* [réf. 8] — formule d'annuelisation intégrale.
- **Adaptation** : formule reprise littéralement ; ce qui change est le contenu de `Lp` : DDF USACE [réf. 9] appliquée avec réserve en France (à terme : courbes « logements » du guide MTES d'analyse multicritère, à ajouter en source). **Sans profondeur par scénario → non exécutable** ; repli = F-C3.

### F-C2 — AAL par distribution de Gumbel + intégration trapézoïdale (méthode de référence améliorée)
```
AAL = ∫₀¹ Loss(e) de        avec e = P(profondeur ≥ d) ~ Gumbel(μ, α), Loss = DDF(d) × V
```
- **Source** : Gnan et al. (2022), Front. Water 4:919726 [réf. 5] (AAL par bâtiment ; chiffres illustratifs : 1 ft de rehaussement ≈ 1 000 $/an, 4 ft ≈ 2 000 $/an).
- **Adaptation** : non exécutable aujourd'hui — calibrer Gumbel exige **au moins deux profondeurs par période de retour**, indisponibles par adresse. Méthode cible documentée, à activer quand une profondeur réelle existe ; on n'utilise **pas** les $ illustratifs US.

### F-C3 — Repli AAL : fourchette publiée (quand aucune profondeur)
```
AAL ∈ [0,47 % ; 0,98 %] × V_reconstruction   par an, en zone inondable (A zone)
```
- **Source** : Al Assi, Mostafiz, Friedland & Rohli (2024), Int. J. Environ. Res. 18(2) [réf. 6] — médiane AAL d'une maison unifamiliale en zone A.
- **Adaptation** : fourchette US appliquée en ordre de grandeur, **explicitement marquée** `fourchette` avec réserve de transposabilité ; sans courbe, l'effet d'une mesure ne peut pas y être appliqué → le bénéfice AAL reste qualitatif en l'absence de profondeur.

### F-C4 — Bénéfice = AAL évité par la mesure
```
B_AAL = AAL_avant − AAL_après(profondeur, DDF modifiée par la mesure)
```
- **Source** : Campos Rodrigues et al. (2026) [réf. 7] — cadre CBA : bénéfice = réduction d'AAL, coûts = implémentation + maintenance, NPV au taux 3 %, maintenance 1 % de l'investissement.
- **Adaptation** : on reprend le principe (bénéfice = ΔAAL) ; le taux d'efficacité de chaque mesure vient des référentiels MRN [réf. 12] ; NPV/taux d'actualisation repris de la source en option.

### F-D1 — Retour sur investissement / temps de retour
```
TR (années) = C_net / (B_assu + B_AAL)         — si B_total > 0, sinon non défini
NPV = Σ_t (B_t − M_t)/(1+0,03)^t − C_net       (option, taux 3 %, M = maintenance 1 %/an)
```
- **Source** : temps de retour simple = pratique standard CBA ; NPV : Campos Rodrigues et al. (2026) [réf. 7] (taux 3 %, maintenance 1 %). van Ierland et al. (Wageningen) [§5, non vérifié] donnerait le cadre méthodologique complet — **non utilisé tant que non vérifié**.
- **Adaptation** : le TR n'est affiché que si `B_total > 0` et si les composantes sont `calculé`/`fourchette` ; jamais de durée inventée.

### F-D2 — Gain de valeur immobilière (exclu du ROI, qualitatif uniquement)
```
Fourchettes littérature : −7 % (exposé SLR) / −4 % (inondation lointaine)  [réf. 1]
                          écart ~7 % selon croyances                        [réf. 2]
                          pénalité CRE croissante (qualitatif)              [réf. 3]
```
- **Source** : Bernstein et al. 2019 [réf. 1], Baldauf et al. 2020 [réf. 2], Foerster et al. 2025 [réf. 3], Clayton et al. 2021 [réf. 4].
- **Adaptation** : **aucune** — ces valeurs ne sont pas transposables en un % fiable pour un bien français (littérature US/côtière, effets de croyances) ; présentées en liste avec leurs limites, jamais additionnées au ROI.

---

## 5. Références fournies mais NON vérifiées (à marquer « non vérifié » dans le code)

Ne pas citer comme source de paramètre tant qu'elles ne sont pas lues :
- van Ierland, E.C., Weikard, H.P., et al. *Cost benefit analysis for climate change adaptation.* (Wageningen) — fourni par l'utilisateur, non vérifié par recherche en ligne.
- UNEP FI (2021). *Climate Risk and Commercial Property Values* (Clayton et al., rapport) — le papier JPM n°4 en est dérivé ; le rapport UNEP FI lui-même non relu.
- Rapports GCA (Global Center on Adaptation) — non relus, cités en qualitatif uniquement.

---

## 6. Règles d'affichage (front + API)

1. Chaque bloc économique renvoie : `{ valeur, min, max, statut: calcule|fourchette|null, sources: [id], hypotheses, confidence }`.
2. Un montant n'est jamais affiché sans sa liste de sources.
3. Le ROI (temps de retour en années) n'est affiché que si `statut=calcule` ou `fourchette` avec bornes explicites ; sinon message explicatif, pas de chiffre.
4. Version française : les fourchettes US ($) sont converties à titre indicatif ou écartées ; jamais présentées comme valeurs françaises.

---

## 7. Implémentation (réalisée)

- `backend/app/economie/` :
  - `sources.py` — registre des références vérifiées + `source_refs()` (lève `KeyError` sur un id inconnu) ;
  - `schemas.py` — blocs standard `{ valeur, min, max, statut, sources, hypotheses, confidence }`, `sommes_blocs`, `calculer_confiance` ;
  - `valuateur.py` — F-B1 (médiane prix m² DVF × surface) ;
  - `benefice_assurance.py` — F-B2 (franchise D.125-5, sinistre moyen CCR/Cour des Comptes, fréquence CATNAT) ;
  - `aal.py` — F-C3 (fourchette publiée 0,47–0,98 % zone A) ;
  - `effet_travaux.py` — niveau A (Δ de score réel via `_combine_risk`/`_score_global` du moteur) ;
  - `roi.py` — F-B3/F-D1/F-D2 (`evaluate`) ;
  - `service.py` — `compute_retour_investissement` (orchestration).
- Endpoint `POST /diagnostic/retour-investissement` (`backend/app/api/routes/retour_investissement.py`, branché dans `backend/app/main.py`).
- Tests : `backend/tests/test_economie.py` (13 tests, dont « aucun montant non-null sans source » et déduplication du coût d'une reco dupliquée sur les zones `murs_*`).
