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

Fatto e testato: modello, mercati, rimozione margine, consenso, fusione,
Kelly, schedine con correlazione, backtest, simulatore, adattatori dati.

Da fare: app mobile (Expo/React Native) e API che la serve; taratura degli
iperparametri sui dati veri; alias dei nomi squadra fra fonti diverse.

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
