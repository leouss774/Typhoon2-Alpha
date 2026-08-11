# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path('frontend/src')
ROOT.joinpath('styles').mkdir(exist_ok=True)

jumeau = ROOT / 'components' / 'UsineJumeau.tsx'
usine = ROOT / 'routes' / 'Usine.tsx'
css = ROOT / 'styles' / 'usine.css'

jumeau.write_text(
    "// ...\n//   Je compléterai ce composant par la suite.\n// ...\n",
    encoding='utf-8'
)

usine.write_text(
    "// ...\n//   Je compléterai ce composant par la suite.\n// ...\n",
    encoding='utf-8'
)

css.write_text(
    "/* ... */\n",
    encoding='utf-8'
)

print('stubs written')
print(jumeau, jumeau.exists())
print(usine, usine.exists())
print(css, css.exists())
