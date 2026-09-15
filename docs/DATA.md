# Fonti dati

## Cosa serve, e perche' sono due problemi diversi

Il sistema ha bisogno di due flussi che vengono da fonti diverse e hanno
requisiti diversi.

**Risultati storici** — servono a stimare il modello. Ne servono molti (almeno
4-5 stagioni per nazione) ma non servono in tempo reale: si scaricano una volta
e si aggiornano una volta a settimana.

**Quote correnti** — servono a trovare il valore. Servono fresche (le quote si
muovono fino al calcio d'inizio) ma solo per le partite dei prossimi giorni.

## Risultati storici: football-data.co.uk

Un CSV per divisione e stagione, gratuito, con risultati *e* quote di chiusura
di diversi bookmaker. Le quote storiche valgono quanto i risultati: permettono
di misurare il modello contro il mercato dell'epoca invece che contro un
riferimento arbitrario.

URL: `https://www.football-data.co.uk/mmz4281/{stagione}/{divisione}.csv`
dove la stagione 2024-2025 diventa `2425`.

| codice interno | codice fonte | campionato |
|---|---|---|
| IT1 / IT2 | I1 / I2 | Serie A / Serie B |
| EN1 / EN2 | E0 / E1 | Premier League / Championship |
| DE1 / DE2 | D1 / D2 | Bundesliga / 2. Bundesliga |
| ES1 / ES2 | SP1 / SP2 | LaLiga / LaLiga 2 |
| FR1 / FR2 | F1 / F2 | Ligue 1 / Ligue 2 |
| PT1 | P1 | Primeira Liga |

**Liga Portugal 2 non e' coperta.** La fonte non la pubblica e non risulta una
sostituta gratuita affidabile. E' l'unico buco rispetto alla copertura
richiesta, ed e' meglio dichiararlo che riempirlo con dati di qualita' ignota.

```python
from bookmaking.ingest import FootballDataCsv

fonte = FootballDataCsv()
partite = fonte.fetch_results("IT1", "2024-2025", verify=True)
```

> **Da verificare al primo giro.** Nomi e presenza delle colonne seguono la
> documentazione della fonte, ma non e' stato possibile controllarli contro il
> sito dal vivo. `verify=True` stampa cosa ha trovato e quali book hanno le
> quote di chiusura, invece di caricare in silenzio dati sbagliati.

## Quote correnti: aggregatori

### Perche' non raschiare i siti dei bookmaker

Raschiare i palinsesti di Goldbet, Sisal o Snai viola i loro termini di
servizio, si rompe a ogni cambio di pagina e finisce bloccato dalle protezioni
anti-bot. Un aggregatore espone le stesse quote con un contratto stabile e
legittimo.

### The Odds API

Piano gratuito limitato, a pagamento per volumi seri. Regione `eu`.

```bash
export ODDS_API_KEY="..."
```
```python
from bookmaking.ingest import TheOddsApi
api = TheOddsApi()
quote = api.fetch_odds("IT1", markets=("h2h", "totals"))
print(api.last_quota)   # il credito residuo arriva negli header: guardalo
```

**Sulla copertura italiana.** La regione `eu` include i grandi book europei, ma
i concessionari ADM italiani minori possono non esserci. Questo non affonda il
progetto, perche' i due usi delle quote sono separati:

- la **quota vera** si stima meglio con i book affilati (exchange, Pinnacle),
  che nella regione `eu` ci sono;
- la **quota su cui si gioca** serve solo per i book dove hai un conto, e per
  quelli il prezzo si puo' sempre inserire a mano.

### Betfair Exchange

Ha una API ufficiale ed e' il riferimento piu' affilato disponibile: e' un
mercato, non un banco. Richiede un application key e un conto. Vale la pena
aggiungerla come fornitore quando il resto sara' in piedi — nel consenso ha il
peso massimo.

### Aggiungere una fonte

Si implementa `ResultsProvider` o `OddsProvider` (`bookmaking/ingest/base.py`).
Il resto del sistema non sa da dove arrivino i dati, quindi passare da una API
gratuita a una a pagamento, o estendersi ai campionati europei e poi mondiali,
significa scrivere una classe e non toccare altro.

## Nomi delle squadre

Fonti diverse scrivono la stessa squadra in modi diversi: "Inter",
"Internazionale", "Inter Milan". `normalise_team` fa una prima passata
togliendo i suffissi societari, ma la tabella di corrispondenza vera va in
`data/team_aliases.json` e si riempie mano a mano che i disallineamenti
compaiono. Indovinarli a priori non funziona.

Un disallineamento non genera un errore: genera una squadra "nuova" che riceve
il prior delle sconosciute, e previsioni silenziosamente sbagliate. Vale la pena
controllare periodicamente quante squadre sconosciute compaiono.
