# Far girare il progetto dal telefono

Tre strade, dalla meno faticosa alla più faticosa.

---

## Strada 1: non fare niente, sblocca la rete a me

Il mio ambiente di esecuzione ha la rete verso l'esterno bloccata: raggiungo i
registri dei pacchetti e la ricerca web, ma non i siti dei dati. È per questo
che non posso scaricare io lo storico dei campionati.

Quel blocco è una **impostazione dell'ambiente**, scelta quando l'ambiente è
stato creato, e si può cambiare. Se apri le impostazioni degli ambienti su
[code.claude.com](https://code.claude.com/docs/en/claude-code-on-the-web) e
consenti l'accesso di rete (o almeno il dominio `football-data.co.uk`), al
messaggio successivo scarico i dati, taro il modello e ti do i risultati senza
che tu apra un terminale.

È l'opzione che consiglio: zero lavoro per te e nessun problema di compilazione
delle librerie scientifiche su telefono.

---

## Strada 2: GitHub Codespaces dal browser del telefono

Un computer Linux vero che gira nel browser. Funziona su iPhone e Android, non
installa niente sul telefono.

1. Apri nel browser `github.com/GiorgioAda/Bookmaking`
2. Tocca il selettore del ramo e scegli `claude/goldbet-app-connection-5hluot`
3. Tocca il pulsante verde **Code** → scheda **Codespaces** → **Create codespace**
4. Aspetta che si apra l'editor (uno o due minuti)
5. Menu (le tre righe in alto a sinistra) → **Terminal** → **New Terminal**
6. Scrivi e invia:

```bash
bash avvio.sh
```

Alla fine, nell'elenco dei file a sinistra compare `rapporto.txt`: aprilo, tieni
premuto per selezionare tutto e copialo qui.

**Da sapere:** su schermo di telefono l'editor è scomodo, la tastiera copre
metà terminale e i caratteri sono piccoli. Gira in orizzontale. Codespaces ha
un piano gratuito mensile: controlla quanto ti resta nelle impostazioni del tuo
account GitHub, perché oltre quello si paga.

---

## Strada 3: un terminale nativo sul telefono

Sconsigliata, ma la descrivo per completezza. Il problema non è il terminale: è
che questo progetto usa `numpy` e `scipy`, librerie scientifiche che sul
telefono vanno compilate e spesso non compilano.

**Android — Termux.** Installalo da [F-Droid](https://f-droid.org), non dal
Play Store (la versione lì è vecchia e non aggiornabile). Poi:

```bash
pkg update && pkg install python git
git clone https://github.com/GiorgioAda/Bookmaking
cd Bookmaking
pip install numpy scipy pandas pytest
bash avvio.sh
```

Il passaggio che può fallire è `pip install scipy`. Se succede, prova prima
`pkg install python-numpy python-scipy` e poi ripeti.

**iPhone — a-Shell o iSH.** Su iOS non è possibile installare liberamente
software compilato, e `scipy` è proprio il caso peggiore. Se ci provi e
fallisce, non è colpa tua: passa alla strada 1 o 2.

---

## Come leggermi gli errori

Qualunque strada, se qualcosa va storto:

- **Fai uno screenshot** e mandamelo. Leggo le immagini, e spesso l'errore vero
  è tre righe sopra quella che sembra l'errore.
- Oppure copia `rapporto.txt`, che lo script scrive comunque anche quando si
  ferma a metà.
- Mandamelo **anche se è incompleto**: mi dice dove si è bloccato meglio di
  qualsiasi descrizione a parole.

Errori più comuni e cosa significano:

| cosa leggi | significa |
|---|---|
| `Python 3 non trovato` | manca Python: strada 2 ce l'ha già installato |
| `[non scaricati] ... 403` | la fonte non è raggiungibile: rete, firewall o VPN |
| `Connection refused` / `Timeout` | stessa cosa, problema di rete |
| `error: externally-managed-environment` | sistema che protegge i pacchetti: `avvio.sh` crea un ambiente separato apposta, rilancialo |
| `ModuleNotFoundError: scipy` | l'installazione non è andata a fondo, tipico della strada 3 |
| `N nomi sospetti` | **non è un errore**: è il controllo sui nomi squadra, me ne occupo io |
| `nessun nome sospetto` | è l'esito buono |
