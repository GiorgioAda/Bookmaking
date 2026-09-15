"""Prezzi inseriti a mano: il ponte verso i book senza feed.

Avere un conto su Goldbet permette di *vedere* le quote e di *giocarle*, non di
riceverle via API. Raschiare il sito e' escluso: viola i termini di servizio, si
rompe a ogni modifica della pagina e finisce bloccato dalle protezioni anti-bot.

Fortunatamente serve molto meno di quanto sembri. Nell'architettura del sistema
i book hanno due ruoli distinti, e Goldbet ne ricopre uno solo:

- stimare la *quota vera* e' compito del consenso fra molti book, dove pesano
  soprattutto quelli affilati. Un banco retail in piu' o in meno non sposta
  quasi nulla;
- fornire il *prezzo su cui si gioca* e' compito del book dove hai il conto, e
  riguarda solo le poche selezioni che il sistema ha gia' selezionato.

Con 3-6 giocate a settimana, quel secondo ruolo si copre battendo a mano
altrettanti numeri. Il sistema calcola in anticipo la **quota richiesta** di
ogni selezione, cioe' la soglia oltre la quale diventa conveniente: sull'app di
Goldbet resta solo da confrontare un numero e digitarlo.

Una quota parziale inserita cosi' non entra nel consenso — con una sola
selezione il margine non e' calcolabile — ma viene usata come prezzo giocabile.
La distinzione e' voluta e vale la pena tenerla ferma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from bookmaking.domain import MatchOdds, OddsQuote


@dataclass(frozen=True)
class PriceEntry:
    """Una quota letta dall'app del bookmaker e battuta a mano."""

    match_id: str
    market: str
    selection: str
    price: float
    bookmaker: str = "goldbet"
    entered_at: datetime | None = None

    def __post_init__(self) -> None:
        if not (self.price > 1.0):
            raise ValueError(f"quota non valida: {self.price}")


@dataclass
class ManualPrices:
    """Raccolta di quote inserite a mano, pronte da fondere col feed."""

    entries: list[PriceEntry] = field(default_factory=list)
    name: str = "manuale"

    def add(self, match_id: str, market: str, selection: str, price: float,
            bookmaker: str = "goldbet") -> PriceEntry:
        entry = PriceEntry(match_id=match_id, market=market, selection=selection,
                           price=price, bookmaker=bookmaker,
                           entered_at=datetime.now())
        # una nuova quota sulla stessa selezione sostituisce la precedente
        self.entries = [e for e in self.entries
                        if not (e.match_id == match_id and e.market == market
                                and e.selection == selection
                                and e.bookmaker == bookmaker)]
        self.entries.append(entry)
        return entry

    def merge_into(self, odds: dict[str, MatchOdds]) -> dict[str, MatchOdds]:
        """Aggiunge le quote manuali a quelle del feed, senza modificare l'originale."""
        merged = {k: MatchOdds(v.match_id, list(v.quotes)) for k, v in odds.items()}
        grouped: dict[tuple[str, str, str], dict[str, float]] = {}
        stamps: dict[tuple[str, str, str], datetime | None] = {}
        for e in self.entries:
            key = (e.match_id, e.bookmaker, e.market)
            grouped.setdefault(key, {})[e.selection] = e.price
            stamps[key] = e.entered_at

        for (match_id, book, market), prices in grouped.items():
            target = merged.get(match_id)
            if target is None:
                target = MatchOdds(match_id, [])
                merged[match_id] = target
            # una quota manuale sostituisce quella dello stesso book dal feed:
            # l'hai letta adesso, il feed puo' essere vecchio di ore
            target.quotes = [q for q in target.quotes
                             if not (q.bookmaker.lower() == book.lower()
                                     and q.market == market)]
            target.quotes.append(OddsQuote(book, market, prices,
                                           collected_at=stamps[(match_id, book, market)]))
        return merged


def books_in_feed(odds: dict[str, MatchOdds]) -> set[str]:
    """Quali bookmaker il feed sta effettivamente restituendo.

    Utile per sapere subito se il proprio book c'e' o va inserito a mano,
    invece di scoprirlo dall'assenza di giocate consigliate.
    """
    return {q.bookmaker.lower() for mo in odds.values() for q in mo.quotes}


def missing_books(odds: dict[str, MatchOdds], wanted: frozenset[str]) -> set[str]:
    return {b for b in wanted if b not in books_in_feed(odds)}
