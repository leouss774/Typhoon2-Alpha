import { useTyphoonTheme } from '../typhoon/useTyphoonTheme';
import { TyphoonFooter, TyphoonNavbar } from '../typhoon/TyphoonChrome';

const FAQ_ITEMS = [
  {
    id: 'a1',
    question: "Qu'est-ce que Typhoon&nbsp;?",
    answer: (
      <>
        Typhoon est une <span className="is-white">plateforme souveraine d&rsquo;&eacute;valuation des risques climatiques</span> qui croise
        les donn&eacute;es officielles (G&eacute;orisques, BDNB, DVF, M&eacute;t&eacute;o-France) avec{' '}
        <span className="is-white">l&rsquo;IA g&eacute;n&eacute;rative</span> pour produire un diagnostic pr&eacute;cis de chaque bien en
        quelques minutes.
      </>
    ),
  },
  {
    id: 'a2',
    question: 'Quelles donn&eacute;es sont utilis&eacute;es&nbsp;?',
    answer: (
      <>
        Nous nous appuyons sur les donn&eacute;es publiques de r&eacute;f&eacute;rence&nbsp;: <span className="is-white">G&eacute;orisques</span>{' '}
        pour les risques naturels, la <span className="is-white">BDNB</span> pour le b&acirc;ti, les{' '}
        <span className="is-white">DVF</span> pour les transactions, M&eacute;t&eacute;o-France et Copernicus pour le climat &mdash;
        crois&eacute;es avec les projections GIEC &agrave; l&rsquo;horizon 2050.
      </>
    ),
  },
  {
    id: 'a3',
    question: 'Comment se d&eacute;roule la premi&egrave;re consultation&nbsp;?',
    answer: (
      <>
        Nous analysons votre situation de mani&egrave;re <span className="is-white">non engageante</span> et vous repartez d&eacute;j&agrave;
        avec un &eacute;clairage concret, quel que soit votre niveau de maturit&eacute;. Nous v&eacute;rifions aussi que la collaboration
        est la bonne.
      </>
    ),
  },
  {
    id: 'a4',
    question: 'Dois-je changer d&rsquo;assureur&nbsp;?',
    answer: (
      <>
        Non, ce n&rsquo;est pas n&eacute;cessaire. Vous pouvez conserver vos contrats actuels et utiliser Typhoon sur un{' '}
        <span className="is-white">p&eacute;rim&egrave;tre pr&eacute;cis</span> (un portefeuille, une zone, un bien) ou sur l&rsquo;ensemble
        de votre activit&eacute;.
      </>
    ),
  },
  {
    id: 'a5',
    question: 'Comment l&rsquo;IA g&eacute;n&eacute;rative est-elle utilis&eacute;e&nbsp;?',
    answer: (
      <>
        Notre moteur d&rsquo;IA g&eacute;n&eacute;rative, <span className="is-white">propuls&eacute; par Mistral AI</span>, traduit les
        donn&eacute;es techniques en un diagnostic clair, un rapport narratif et des recommandations de travaux compr&eacute;hensibles
        par tous.
      </>
    ),
  },
  {
    id: 'a6',
    question: 'Mes donn&eacute;es sont-elles souveraines&nbsp;?',
    answer: (
      <>
        Oui. Notre infrastructure est con&ccedil;ue pour la <span className="is-white">souverainet&eacute; des donn&eacute;es</span>&nbsp;:
        vos donn&eacute;es et celles de vos clients restent <span className="is-white">h&eacute;berg&eacute;es en Europe</span>,
        conform&eacute;ment au RGPD et aux exigences du secteur assurantiel.
      </>
    ),
  },
  {
    id: 'a7',
    question: 'Combien de temps pour obtenir un diagnostic&nbsp;?',
    answer: (
      <>
        Quelques minutes. D&egrave;s l&rsquo;adresse renseign&eacute;e, Typhoon agr&egrave;ge les donn&eacute;es officielles et produit un{' '}
        <span className="is-white">score multi-p&eacute;rils</span>, une cartographie des risques et des recommandations prioris&eacute;es.
      </>
    ),
  },
  {
    id: 'a8',
    question: 'Comment obtenir la certification Climato-R&eacute;silient&nbsp;?',
    answer: (
      <>
        Engagez les travaux recommand&eacute;s par la plateforme, puis faites valider les mesures par nos experts. La{' '}
        <span className="is-white">certification Typhoon</span> atteste de la r&eacute;silience de votre bien et ouvre droit &agrave; une
        prime r&eacute;duite.
      </>
    ),
  },
  {
    id: 'a9',
    question: 'Combien co&ucirc;te Typhoon&nbsp;?',
    answer: (
      <>
        R&eacute;servez une <span className="is-white">d&eacute;mo gratuite et sans engagement</span>&nbsp;: nous pr&eacute;sentons la
        plateforme sur vos cas r&eacute;els, puis nous d&eacute;finissons ensemble l&rsquo;offre adapt&eacute;e &agrave; votre
        p&eacute;rim&egrave;tre.
      </>
    ),
  },
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
              {FAQ_ITEMS.map((item) => (
                <div key={item.id} id={`w-node-faq-${item.id}`} className={`faq-item ${item.id}`}>
                  <div className="faq-item-inner">
                    <h1 className="global-headline-s">{item.question}</h1>
                    <div className="global-subline tm-05">
                      <p className="faq-txt">{item.answer}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="black-spacer" />
      </section>
      <TyphoonFooter />
    </div>
  );
}
