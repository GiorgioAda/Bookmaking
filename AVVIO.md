# Cosa devi fare

> **Dal telefono?** Leggi [MOBILE.md](MOBILE.md): c'e' anche un modo per non
> fare niente e lasciare tutto a me.
>
> **La tabella bonus l'ho gia' raccolta io** per sette bookmaker (vedi
> `data/bonus_bookmaker.json` ed esegui `examples/confronta_bonus.py`). I dati
> vengono da siti di comparazione, non dai regolamenti ufficiali: il passo 1 qui
> sotto serve a sostituirli con quelli veri del tuo conto, ed e' utile ma non
> piu' urgente.

---

## 1. Compila la tabella bonus (facoltativo ora)

Apri **`data/bonus_goldbet.json`** e sostituisci i numeri con quelli veri del
tuo conto.

Li trovi sul sito o sull'app di Goldbet, di solito sotto *Bonus Multipla*,
*Promozioni*, oppure nelle condizioni del palinsesto. Cerchi tre cose:

| cosa cercare | dove finisce nel file |
|---|---|
| la percentuale di bonus per ogni numero di gambe | `bonus_per_gambe` |
| la quota minima perche' una gamba valga per il bonus | `quota_minima_per_gamba` |
| da quante gambe parte il bonus | `gambe_minime` |

Scrivi `15` per +15%. Metti solo gli scaglioni che Goldbet elenca davvero: per i
numeri intermedi il sistema applica lo scaglione raggiunto.

**I numeri che trovi ora nel file sono segnaposto inventati da me**, messi solo
per far girare gli esempi. Se non li sostituisci, tutti i conti successivi sono
finti.

Questa e' la cosa piu' importante delle due. E' il numero che decide se la
schedina lunga che vuoi ha senso oppure no: il bonus deve superare il margine
composto del banco, che a dieci gambe vale +67%.

---

## 2. Lancia un comando

Apri il Terminale nella cartella del progetto e scrivi:

```bash
bash avvio.sh
```

Ci mette qualche minuto. Installa quello che serve, esegue i test, controlla la
tua tabella bonus, scarica lo storico degli undici campionati e tara il modello
sui dati veri.

Alla fine trovi un file **`rapporto.txt`** nella cartella.

### Se qualcosa non va

| messaggio | cosa significa |
|---|---|
| `Python 3 non trovato` | installa Python da python.org, poi ripeti |
| `[non scaricati] ... 403` oppure `Connection refused` | la fonte non e' raggiungibile: rete, firewall o VPN aziendale |
| `nessun nome sospetto` | tutto a posto, e' l'esito buono |
| `N nomi sospetti` | normale al primo giro, me ne occupo io |

Se il rapporto si ferma prima della fine, mandamelo lo stesso: mi dice dove si e'
bloccato meglio di qualsiasi descrizione.

---

## 3. Mandami due cose

1. il file **`rapporto.txt`**
2. il tuo **`data/bonus_goldbet.json`** compilato

---

## Cosa succede dopo

Con il rapporto taro il modello sui parametri veri invece che su quelli
simulati, e ti dico se batte davvero le quote di chiusura dei bookmaker.

Con la tabella bonus ti dico a quante gambe conviene giocare: se il bonus di
Goldbet supera la soglia, la schedina lunga che volevi ha senso; se non la
supera, la schedina piu' corta che arriva a quota 5 e' sempre migliore, e i
numeri lo mostrano senza ambiguita'.

Poi costruisco l'app.

---

## Una cosa da sapere prima di giocare

Il sistema sovrastima il proprio vantaggio di 15-20 punti percentuali: e'
misurato, documentato nel README, e non e' un difetto correggibile. Il valore
atteso che vedrai serve a **ordinare** le giocate dalla migliore alla peggiore,
non a prevedere quanto guadagnerai.

Sul raddoppiare 30 euro: nella simulazione riesce nel 31% dei casi e il capitale
finisce a zero nel 69%. Non e' sfiducia nel progetto, e' il margine del banco che
lavora a ogni giocata.
