# Quota Vera — l'app

Pagina pubblicata su claude.ai: <https://claude.ai/artifact/2kcNkHW9LUndVGPjiPiPzz>

Si apre dal browser del telefono, non installa niente, ed e' privata finche' non
viene condivisa.

## Versione 2: calendario, confronto quote, schedina

L'app ora parte dal **calendario delle prossime partite** invece che da una
partita per volta, e costruisce la schedina da ricopiare a mano nel bookmaker.
Non piazza scommesse e non si collega ad alcun conto.

Le quattro schede: **Partite** (calendario con il pronostico del modello; si
apre una partita, si inseriscono le quote di piu' bookmaker e si ottengono
consenso, prezzo migliore, valore e puntata), **Schedina** (ottimizzatore
multi-gamba con il testo pronto da ricopiare), **Bonus**, **Registro**.

Per Champions, Europa e Conference League — e per le divisioni senza calendario
pubblicato — si aggiunge la partita a mano: il modello non le copre, ma le
quote dei bookmaker si', e sono la stima piu' accurata disponibile.

### Perche' il peso del modello e' a zero

Misurato su 33.300 partite in walk-forward: ogni punto di peso dato al modello
peggiora la previsione, in modo monotono (RPS da 0,2029 a peso zero fino a
0,2082 a peso pieno). Il modello vede solo gol e date; il mercato vede anche
formazioni e infortuni. Il cursore resta nel Registro perche' la scelta e'
dell'utente, ma il default e' quello che i dati indicano.

Il modello non diventa inutile: resta il confronto che segnala quando una quota
battuta a mano diverge troppo dal ragionevole, che con l'inserimento manuale e'
quasi sempre un errore di digitazione.

## Cosa faceva la versione 1

Funziona **senza dati storici**, che e' il motivo per cui esiste gia' mentre il
resto del progetto aspetta la taratura. Il trucco: invece di stimare la forza
delle squadre dai risultati passati, ricava i **gol attesi impliciti nelle quote
stesse del banco**, cercando la coppia (lambda, mu) la cui matrice Dixon-Coles
riproduce le probabilita' di mercato. Da quei gol attesi discendono tutti gli
altri mercati, coerenti fra loro per costruzione.

Il limite va tenuto presente e la pagina lo dichiara: trova le **incoerenze
interne** del listino di un bookmaker — i mercati secondari prezzati con meno
cura del principale — non un vantaggio assoluto. Se l'1X2 del banco e' giusto,
non c'e' niente da trovare. Il modello statistico sui risultati storici e'
l'altra meta' del progetto e in app non c'e' ancora.

## Le quattro schede

- **Partita** — quote 1X2 in ingresso; in uscita margine del banco, probabilita'
  vere (Shin), gol attesi impliciti, quota equa di sedici mercati derivati e la
  quota minima oltre la quale ciascuno conviene. Segnala quando la
  ricostruzione non torna, cioe' quando 1X2 e Over/Under raccontano due partite
  diverse.
- **Schedina** — gambe, quota, probabilita', valore atteso col bonus applicato;
  la combinazione piu' probabile che raggiunge la quota obiettivo (ricerca
  esaustiva su tutti i sottoinsiemi) e la frontiera per numero di gambe.
- **Bonus** — offerto contro necessario, con il limite di praticabilita'.
- **Registro** — giocate, esito, e il confronto fra rendimento reale e
  rendimento che l'app aveva promesso.

## Rapporto col motore Python

Il calcolo e' un porting di `src/bookmaking/`, verificato valore per valore
contro l'originale: rimozione del margine con Shin, matrice dei punteggi
Dixon-Coles, mercati derivati, handicap con le linee a quarto, Kelly compresso.
I test di riferimento stanno in `tests/`.

Il solutore dei gol attesi e' invece specifico dell'app e non ha un
corrispettivo in Python: ricostruisce i parametri veri entro 1e-6 sui casi di
prova, in circa 30 ms.

## Aggiornarla

Ripubblicare lo stesso file dalla conversazione che l'ha creata mantiene
l'indirizzo. Da un'altra conversazione serve passare l'URL, altrimenti nasce una
pagina separata.
