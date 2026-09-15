"""Reinserisce i dati aggiornati nella pagina e rigenera la versione autonoma.

I dati vivono dentro la pagina, non accanto: la piattaforma degli artifact non
serve file ausiliari alle chiamate della pagina, quindi rating, calendario e
tabelle bonus stanno in un blocco JSON incorporato. Il rovescio della medaglia
e' che rigenerare ``app/dati.json`` non basta: finche' non si riscrive quel
blocco, la pagina continua a usare i dati vecchi e non se ne accorge nessuno.

    python examples/esporta_app.py      # rigenera i dati
    python examples/aggiorna_pagina.py  # li mette nella pagina
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PAGINA = Path("app/quota-vera.html")
AUTONOMA = Path("app/quota-vera-standalone.html")
PAGES = Path("docs/index.html")     # copia servita da GitHub Pages
DATI = Path("app/dati.json")

# Il CSS contiene graffe e simboli di percentuale, quindi niente formattazione
# con segnaposto: le due meta' si concatenano e basta.
TESTA = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
:root{color-scheme:light dark;padding-top:env(safe-area-inset-top,0px);
  padding-bottom:env(safe-area-inset-bottom,0px)}
html,body{margin:0}
body{font:14px system-ui,-apple-system,sans-serif}
img{max-width:100%}
[hidden]{display:none!important}
</style>
"""
CODA = """
</body>
</html>"""


def main() -> None:
    pagina = PAGINA.read_text(encoding="utf-8")
    dati = json.loads(DATI.read_text(encoding="utf-8"))
    compatto = json.dumps(dati, ensure_ascii=False, separators=(",", ":"))

    nuovo, n = re.subn(
        r'(<script id="datiApp" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + compatto + m.group(2),
        pagina, count=1, flags=re.S)
    if n != 1:
        raise SystemExit("blocco dei dati non trovato nella pagina")
    PAGINA.write_text(nuovo, encoding="utf-8")

    i = nuovo.index('<div class="wrap">')
    AUTONOMA.write_text(TESTA + nuovo[:i] + "</head>\n<body>\n" + nuovo[i:] + CODA,
                        encoding="utf-8")

    PAGES.parent.mkdir(exist_ok=True)
    PAGES.write_text(AUTONOMA.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"{len(dati['squadre'])} squadre, {len(dati['partite'])} partite, "
          f"{len(dati.get('bookmaker', {}))} bookmaker")
    print(f"  {PAGINA} ({PAGINA.stat().st_size / 1024:.0f} KB)")
    print(f"  {AUTONOMA} ({AUTONOMA.stat().st_size / 1024:.0f} KB)")
    print(f"  {PAGES} ({PAGES.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
