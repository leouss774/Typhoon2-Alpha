import type { ReactNode } from 'react';
import { useTyphoonTheme } from '../typhoon/useTyphoonTheme';
import { TyphoonFooter, TyphoonNavbar } from '../typhoon/TyphoonChrome';
import '../styles/typhoon-pages.css';

interface FaqCell {
  id: string;
  question?: ReactNode;
  answer?: ReactNode;
}

/**
 * Grille 3x3 fidèle à la maquette Webflow : 4 questions disposées
 * en quinconce, les autres cellules restant vides.
 *
 *     [ — ]  [a5]  [ — ]
 *     [a4]  [ — ]  [a6]
 *     [ — ]  [a7]  [ — ]
 *
 * L'ordre du DOM (a1 → a9) suit la maquette ; la grille desktop est
 * imposée par les classes grid-area, et sur mobile (colonne flex) les
 * cellules vides se replient pour laisser les 4 questions dans l'ordre.
 */
const FAQ_CELLS: FaqCell[] = [
  { id: 'a1' },
  { id: 'a2' },
  { id: 'a3' },
  {
    id: 'a4',
    question: 'Comment se déroule la première consultation ?',
    answer: (
      <>
        Nous analysons votre situation de manière <span className="is-white">non engageante</span> et vous repartez
        déjà avec un éclairage concret, quel que soit votre niveau de maturité. Nous vérifions aussi que la
        collaboration est la bonne.
      </>
    ),
  },
  {
    id: 'a5',
    question: "Dois-je changer d'assureur ?",
    answer: (
      <>
        Non, ce n'est pas nécessaire. Vous pouvez conserver vos contrats actuels et utiliser Typhoon sur un{' '}
        <span className="is-white">périmètre précis</span> (un portefeuille, une zone, un bien) ou sur l'ensemble de
        votre activité.
      </>
    ),
  },
  {
    id: 'a6',
    question: "Comment l'IA générative est-elle utilisée ?",
    answer: (
      <>
        Notre moteur d'IA générative, <span className="is-white">propulsé par Mistral AI</span>, traduit les données
        techniques en un diagnostic clair, un rapport narratif et des recommandations de travaux compréhensibles par
        tous.
      </>
    ),
  },
  {
    id: 'a7',
    question: 'Mes données sont-elles souveraines ?',
    answer: (
      <>
        Oui. Notre infrastructure est conçue pour la <span className="is-white">souveraineté des données</span> : vos
        données et celles de vos clients restent <span className="is-white">hébergées en Europe</span>, conformément au
        RGPD et aux exigences du secteur assurantiel.
      </>
    ),
  },
  { id: 'a8' },
  { id: 'a9' },
];

export function Faq() {
  const { wrapperClass, wrapperStyle } = useTyphoonTheme();

  return (
    <div className={wrapperClass} style={wrapperStyle}>
      <TyphoonNavbar current="faq" />
      <section className="main-content">
        <div className="faq">
          <div className="faq-outer">
            <div className="_3x3-grid v1">
              {FAQ_CELLS.map((cell) => (
                <div
                  key={cell.id}
                  id={`w-node-faq-${cell.id}`}
                  className={`faq-item ${cell.id}`}
                  aria-hidden={cell.question ? undefined : true}
                >
                  {cell.question ? (
                    <div className="faq-item-inner">
                      <h1 className="global-headline-s">{cell.question}</h1>
                      <div className="global-subline tm-05">
                        <p className="faq-txt">{cell.answer}</p>
                      </div>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>
      <TyphoonFooter />
    </div>
  );
}
