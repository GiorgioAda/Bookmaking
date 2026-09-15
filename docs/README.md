# Pagina pubblicata

`index.html` e' la copia autonoma dell'app, servita da GitHub Pages.

Serve perche' le due strade precedenti non funzionano su telefono:

- la versione pubblicata su claude.ai gira in una sandbox che blocca ogni
  chiamata verso l'esterno, quindi lo scaricamento automatico delle quote non
  puo' funzionare li', per costruzione;
- un file HTML scaricato su iPhone non si apre comodamente: il sistema lo mostra
  in anteprima e JavaScript non gira come in una pagina vera.

Servita da Pages e' una pagina web normale: nessuna sandbox, si apre in Safari
come qualunque sito e si aggiunge alla schermata Home.

Va rigenerata insieme alla pagina: `examples/aggiorna_pagina.py` scrive la
versione autonoma, che va poi copiata qui.
