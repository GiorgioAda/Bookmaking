# Bookmaking

Motore di pronostici calcistici: modello statistico, stima della quota equa,
ricerca del valore e gestione del bankroll.

Copre undici divisioni — prima e seconda serie di Italia, Inghilterra,
Germania, Spagna e Francia, piu' la Primeira Liga portoghese.

---

## Quello che devi sapere prima di tutto il resto

Il sistema e' stato validato in simulazione, in un mondo dove le probabilita'
vere sono note per costruzione. Il risultato piu' importante e' questo:

| errore del bookmaker | vantaggio dichiarato | vantaggio **vero** | ROI |
|---|---|---|---|
| 0.00 (banco perfetto) | +16.4% | **−4.8%** | +0.6% |
| 0.05 | +18.5% | **−1.4%** | +5.0% |
| 0.10 | +22.4% | **+5.4%** | +9.7% |
| 0.20 | +34.9% | **+27.3%** | +26.6% |

Si legge cosi': **il sistema sovrastima sistematicamente il proprio vantaggio
di 15-20 punti percentuali.** Contro un bookmaker che non sbaglia, dichiara
+16.4% mentre il vantaggio reale e' −4.8%, cioe' esattamente il margine del
banco.

Non e' un difetto da correggere: e' la maledizione del vincitore. Il sistema
sceglie di giocare proprio dove il modello dissente di piu' dal mercato, e
quelle sono anche le partite dove il modello ha piu' probabilita' di essere
lui, nel torto. Nessun filtro lo elimina: alzare la soglia di valore atteso
dal 3% al 15% riduce le giocate del 30% e lascia il vantaggio vero dov'era.

La conseguenza pratica: **il numero che l'app mostra come "valore atteso" non
e' il guadagno che ti aspetta.** Serve a ordinare le giocate dalla migliore
alla peggiore, non a prevedere il rendimento. Riprodurre la tabella:

```bash
python examples/simulazione_stagione.py
```

## Con 30 euro a settimana

Il budget cambia cosa e' possibile, in modi che vale la pena mettere in chiaro.

**Kelly va dimensionato sul capitale totale, non su una settimana.** Chi versa
30 euro a settimana per una stagione sta rischiando circa 1.200 euro, non 30.
Calcolare le puntate sui 30 euro produce importi sotto la puntata minima
giocabile, e un sistema che non gioca mai. Nel codice sono due parametri
distinti: `weekly_budget` (tetto di spesa) e `kelly_bankroll` (capitale su cui
Kelly dimensiona).

**La granularita' e' grossolana.** Con puntata minima di 2 euro e budget di 30,
la giocata piu' piccola vale il 6,7% del budget settimanale. Le scommesse a cui
Kelly assegna meno del minimo vengono saltate, non arrotondate al minimo:
forzarle significherebbe puntare sistematicamente piu' del dovuto.

**Aspettati poche giocate.** Tipicamente 3-6 a settimana, non una per partita.

## Come e' fatto

```
storico  ->  modello Dixon-Coles  ->  probabilita' del modello
quote    ->  rimozione margine    ->  probabilita' di mercato
                    \        /
                     fusione (pool logaritmico)
                         |
              confronto con la quota piu' alta fra i book italiani
                         |
                 vantaggio -> Kelly compresso -> puntata
```

Il passaggio finale e' quello che conta di piu': la probabilita' si stima sul
*consenso* di tutti i book, ma si gioca sulla *quota migliore* fra quelli dove
hai un conto. Nella simulazione, questa sola asimmetria — senza alcun modello,
peso del modello a zero — produce un vantaggio vero del +4.5%. Non richiede di
battere il mercato: basta che il mercato non sia unanime.

### Il modello

Dixon-Coles con decadimento temporale: due Poisson corrette sui quattro
punteggi bassi, dove l'indipendenza fra i marcatori e' palesemente falsa.

- **Stima per nazione, non per divisione.** Serie A e Serie B non si incontrano
  mai, quindi separate non sarebbero confrontabili. Sono promozioni e
  retrocessioni a fare da ponte: una squadra retrocessa porta il suo rating
  nella serie inferiore. Su piu' stagioni, la forza relativa delle due divisioni
  diventa identificabile.
- **La forma entra dal decadimento temporale**, non da una feature separata che
  conterebbe due volte le stesse partite. Ogni partita pesa
  `exp(-xi · giorni)`.
- **Un solo modello genera tutti i mercati** dalla stessa matrice dei punteggi:
  1X2, Over/Under, Goal/NoGoal, handicap asiatico, risultato esatto. Sono quindi
  automaticamente coerenti fra loro.

Validazione su dati simulati da parametri noti:

- il gradiente analitico coincide col numerico entro 4·10⁻⁶;
- i rating stimati correlano 0.83 con quelli veri;
- in walk-forward il modello cattura **l'82% del segnale teoricamente
  disponibile** (misurato contro un oracolo che conosce i parametri veri);
- la taratura del decadimento reagisce correttamente: squadre piu' volatili
  richiedono emivite piu' corte (693 → 347 → 116 giorni al crescere della
  deriva).

### Il valore atteso

La rimozione del margine non e' un dettaglio implementativo. Su un mercato
1.25 / 6.00 / 12.00 la quota equa stimata sull'outsider varia da 12.60 a 15.00 a
seconda del metodo — oltre il 10%, abbastanza da inventare valore che non
esiste. Il default e' il metodo di Shin. Sono implementati anche moltiplicativo,
additivo, potenza e odds-ratio.

I bookmaker non sono pareri indipendenti: Goldbet, Better e Lottomatica sono lo
stesso palinsesto. Nel consenso il peso viene diviso all'interno del gruppo,
altrimenti un parere solo conterebbe per tre.

## Schedina a quota obiettivo

Obiettivo tipico: una schedina che arrivi ad almeno quota 5 fra quote e bonus.
Il conto da fare prima di costruirla e' questo, a margine del 5% per gamba:

| gambe | quota | P(vincita) | 1 volta su | valore atteso |
|---|---|---|---|---|
| 2 | 5.01 | **18.1%** | 5.5 | −9.2% |
| 3 | 5.02 | 17.3% | 5.8 | −13.1% |
| 5 | 5.01 | 15.8% | 6.3 | −21.1% |
| 7 | 7.09 | 10.0% | 10.0 | −29.3% |
| 10 | 23.46 | **2.6%** | 38.2 | −38.5% |

Stessa vincita nelle prime tre righe: cambia solo quanto e' probabile
incassarla. **Piu' gambe, a parita' di quota, significa meno probabilita' di
vincere**, perche' insieme alle quote si moltiplicano i margini del banco.

Dalla settima gamba in poi la quota 5 non e' nemmeno raggiungibile: nel calcio
non esistono abbastanza eventi quasi certi, quindi la schedina sfora a 7, poi a
10, poi a 23 di quota, e la probabilita' crolla.

### Il bonus multipla e' l'unica via d'uscita

La soglia e' esatta e non dipende dalle quote scelte:

```
EV = bonus x (1 - margine)^gambe - 1   ->   bonus necessario = 1/(1-margine)^gambe
```

Con margine del 5%: **+29% a cinque gambe, +51% a otto, +67% a dieci.** Se il
bonus del tuo conto supera quella soglia, allungare la schedina conviene
davvero; se sta sotto, ogni gamba in piu' e' solo margine regalato.

C'e' un vincolo nascosto da leggere nelle condizioni: quasi tutti i bonus
richiedono una quota minima per gamba (1.20-1.30). Dieci gambe a 1.20 fanno gia'
quota 6.19 con probabilita' del 9.7%.

```python
from bookmaking.staking.schedina import BonusSchedule

bonus = BonusSchedule(by_legs={5: 1.10, 8: 1.30, 10: 1.50},
                      min_leg_price=1.20, min_legs=5)   # dal TUO conto
for r in bonus.verdict(margin_per_leg=0.05):
    print(r["gambe"], r["bonus_offerto"], r["bonus_necessario"], r["conviene"])

piani = advisor.target_tickets(partite, quote, target=5.0, max_legs=10, bonus=bonus)
```

### Provare a raddoppiare 30 euro

Puntando 2 euro a schedina, fino a raddoppiare o finire il capitale:

| schedina | quota | P(vincita) | raddoppia | va a zero |
|---|---|---|---|---|
| 2 gambe | 5.01 | 18.1% | **31.1%** | 68.9% |
| 3 gambe | 5.02 | 17.3% | 24.4% | 75.6% |
| 5 gambe | 5.01 | 15.8% | 13.9% | 86.1% |
| 10 gambe | 23.46 | 2.6% | 24.5% | 75.5% |

Il capitale si esaurisce circa due volte su tre nel caso migliore. La riga a
dieci gambe risale non perche' sia una scommessa migliore — ha il valore atteso
peggiore — ma perche' una sola vincita supera l'obiettivo: con valore atteso
negativo, puntare forte e poche volte massimizza la probabilita' di toccare un
traguardo, al prezzo di perdere tutto molto piu' spesso.

```bash
python examples/schedina_quota5.py
```

## Usare Goldbet (o qualsiasi book senza feed)

Avere un conto permette di *vedere* e *giocare* le quote, non di riceverle via
API, e raschiare il sito e' escluso: viola i termini di servizio, si rompe a
ogni modifica della pagina e viene bloccato dalle protezioni anti-bot.

Serve pero' molto meno di quanto sembri, perche' nel sistema i book hanno due
ruoli distinti e Goldbet ne ricopre uno solo. La *quota vera* la stima il
consenso fra molti book, dove pesano soprattutto quelli affilati; il *prezzo su
cui si gioca* riguarda solo le poche selezioni gia' selezionate. Con 3-6
giocate a settimana, quel secondo ruolo si copre battendo a mano altrettanti
numeri.

Il sistema calcola in anticipo la **quota richiesta** di ogni selezione, cioe'
la soglia oltre la quale conviene. Sull'app di Goldbet resta un confronto:

```python
for c in advisor.shortlist(partite, quote):
    print(f"{c.label:<24} {c.selection}  serve almeno {c.required_price:.2f}")
```
```
Inter - Lecce              1   serve almeno 1.74
Bologna - Torino           X   serve almeno 3.56
```

Le quote lette si inseriscono e il sistema ricalcola vantaggio e puntata:

```python
from bookmaking.ingest import ManualPrices
prezzi = ManualPrices()
prezzi.add(partita.match_id, "1X2", "1", 1.85)
piano, _ = advisor.weekly_plan(partite, prezzi.merge_into(quote))
```

Una quota parziale inserita cosi' **non entra nel consenso** — con una sola
selezione il margine non e' calcolabile, quindi non e' un parere sul prezzo
vero — ma vale come prezzo giocabile. E se Goldbet comparisse nel feed
dell'aggregatore, la quota battuta a mano ha comunque la precedenza: l'hai
letta adesso, il feed puo' essere vecchio di ore.

## Uso

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest          # 60 test
.venv/bin/python examples/simulazione_stagione.py
```

```python
from bookmaking.model.dixon_coles import DixonColes, FitConfig
from bookmaking.advisor import Advisor
from bookmaking.staking.kelly import BankrollPolicy

fit = DixonColes(FitConfig(xi=0.0025)).fit(storico)
advisor = Advisor(fit=fit, policy=BankrollPolicy(weekly_budget=30.0))

piano, analisi = advisor.weekly_plan(partite, quote)
for b in piano.bets:
    print(f"{b.edge.label}: {b.edge.selection} @ {b.edge.price} "
          f"su {b.edge.bookmaker} — {b.stake:.2f} EUR")
```

## Stato

Fatto e testato (84 test): modello, mercati, rimozione margine, consenso,
fusione, Kelly, schedine con correlazione, backtest, simulatore, adattatori
dati, inserimento manuale delle quote, selezione con quota richiesta e
ottimizzatore di schedine a quota obiettivo con bonus multipla.

**Passo successivo, da eseguire in locale** — richiede accesso a internet, che
l'ambiente di sviluppo non aveva:

```bash
python examples/scarica_e_tara.py --stagioni 6
```

Scarica gli undici campionati, controlla i nomi squadra, tara `xi` e `l2` per
nazione in walk-forward e confronta il modello con le quote di chiusura
dell'epoca. Scrive `data/config_tarato.json`. Finche' non gira, gli
iperparametri restano quelli tarati in simulazione.

Poi: app mobile (Expo/React Native) e API che la serve.

Gli adattatori dati (`FootballDataCsv`, `TheOddsApi`) seguono i formati
documentati ma **non sono stati verificati contro i servizi dal vivo**:
l'ambiente in cui sono stati scritti non aveva accesso di rete verso
l'esterno. Il primo scaricamento va fatto con `verify=True`. Vedi
[docs/DATA.md](docs/DATA.md).

## Limiti

- Gli iperparametri (`xi`, `l2`, i prior sulle neopromosse) sono tarati su dati
  **simulati**. Vanno ri-tarati sui dati veri con `tune_xi` prima di dare peso
  ai risultati.
- Il modello usa solo gol e date. Non sa nulla di formazioni, infortuni,
  squalifiche, calendario europeo. E' anche il motivo per cui conviene non
  azzerare il peso del mercato: quelle informazioni nel prezzo ci sono gia'.
- La Liga Portugal 2 non e' coperta: manca una fonte storica gratuita
  affidabile.
- Nessun modello rende una scommessa un investimento. Con un banco efficiente
  il valore atteso resta negativo, come mostra la prima tabella.
