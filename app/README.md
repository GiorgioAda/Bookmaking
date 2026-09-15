# Quota Vera — l'app

Pagina pubblicata su claude.ai: <https://claude.ai/artifact/2kcNkHW9LUndVGPjiPiPzz>

Si apre dal browser del telefono, non installa niente, ed e' privata finche' non
viene condivisa.

## Cosa fa, e con quali dati

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
