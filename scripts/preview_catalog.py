#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Cesk Freixas
"""Build an offline catalog preview from the reviewed multilingual copy."""
from html import escape
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from campbase import VERSION
catalog = root / 'docs/catalog'
copy = json.loads((catalog / 'copy.json').read_text())
names = {'ca': 'Català', 'es': 'Castellano', 'en': 'English', 'gl': 'Galego', 'eu': 'Euskara', 'oc': 'Aranés'}
parts = ['''<!doctype html>
<html lang="ca"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Campbase · Revisió de la fitxa</title>
<style>
:root{font-family:system-ui,sans-serif;color:#202124;background:#f4f5f6;line-height:1.6;color-scheme:light}
body{max-width:1050px;margin:32px auto;padding:0 24px}header{display:flex;gap:20px;align-items:center}
header img{width:80px;height:80px}h1{margin:0;font-size:2rem}h2{font-size:1.3rem;margin-top:0}
.notice{color:#59616b;font-size:.95rem}nav{display:flex;flex-wrap:wrap;gap:16px;margin:24px 0}
nav a{color:#146477}section{background:white;border:1px solid #ddd;border-radius:16px;padding:24px;margin:24px 0}
figure{margin:28px 0}figure img{display:block;width:100%;height:auto}figcaption{margin-top:8px;color:#59616b}
.requirement{padding:16px;border-radius:8px;background:#f0f4f5}a{overflow-wrap:anywhere}
</style>
<header><img src="../../data/icons/cat.ceskfreixas.Campbase.svg" alt=""><div><h1>Campbase</h1>
<p class="notice">Revisió local de la fitxa · @VERSION@ · Dades de demostració</p></div></header>
<p class="notice">Previsualització de la fitxa. Encara no enviada a Flathub.</p><nav>'''.replace('@VERSION@', escape(VERSION))]
for lang, name in names.items():
    parts.append(f'<a href="#{lang}" lang="{lang}">{name}</a>')
parts.append('</nav>')
for lang in names:
    c = copy[lang]
    parts.append(f'<section id="{lang}" lang="{lang}"><h2>{escape(names[lang])} · {escape(c["summary"])}</h2>')
    parts.append(f'<p>{escape(c["intro"])}</p><ul>')
    parts.extend(f'<li>{escape(item)}</li>' for item in c['features'])
    parts.append(f'</ul><p class="requirement">{escape(c["requirement"])}</p>')
    for kind, caption in zip(['board-light', 'card-light', 'board-dark'], c['captions']):
        file = f'screenshots/{lang}-{kind}.png'
        assert (catalog / file).is_file(), file
        parts.append(f'<figure><a href="{file}"><img loading="lazy" src="{file}" alt="{escape(caption, quote=True)}" width="1000" height="700"></a><figcaption>{escape(caption)}</figcaption></figure>')
    parts.append('</section>')
parts.append('</html>')
(catalog / 'index.html').write_text('\n'.join(parts)+'\n')
print('Local preview: '+str(catalog / 'index.html'))
