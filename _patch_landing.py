# -*- coding: utf-8 -*-
"""Patch temporaire: ajoute un CTA "Analyser un plan d'usine" dans le hero de la landing."""
p = 'frontend/public/landing.html'
s = open(p, encoding='utf-8').read()

needle = 'Commen&ccedil;ons</div></div></a></div></div></div><div class="hero-layer-2"'

insert = (
    'Commen&ccedil;ons</div></div></a>'
    '<a data-w-id="usine-cta-01" href="/usine" target="_top" '
    'class="secondary-btn w-inline-block" style="margin-left:12px">'
    '<div class="btn-txt-container">'
    '<div style="transform:translate3d(0,0,0) scale3d(1,1,1) rotateX(0) rotateY(0) rotateZ(0) skew(0,0)" '
    'class="btn-txt">Analyser un plan d&rsquo;usine</div>'
    '</div></a>'
    '</div></div></div><div class="hero-layer-2"'
)

print('needle occurrences:', s.count(needle))
if s.count(needle) != 1:
    raise SystemExit('Needle not unique, abort')
s = s.replace(needle, insert, 1)
open(p, 'w', encoding='utf-8').write(s)
print('done, /usine count =', s.count('/usine'))
