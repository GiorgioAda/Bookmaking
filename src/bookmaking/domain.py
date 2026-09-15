"""Tipi di dominio condivisi da tutto il sistema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class Outcome(str, Enum):
    """Esiti 1X2."""

    HOME = "1"
    DRAW = "X"
    AWAY = "2"


@dataclass(frozen=True)
class Match:
    """Una partita giocata (con risultato) o da giocare (risultato a None)."""

    division: str
    season: str            # es. "2024-2025"
    kickoff: datetime
    home: str
    away: str
    home_goals: int | None = None
    away_goals: int | None = None
    match_id: str | None = None

    @property
    def played(self) -> bool:
        return self.home_goals is not None and self.away_goals is not None

    @property
    def result(self) -> Outcome | None:
        if not self.played:
            return None
        if self.home_goals > self.away_goals:
            return Outcome.HOME
        if self.home_goals < self.away_goals:
            return Outcome.AWAY
        return Outcome.DRAW

    @property
    def day(self) -> date:
        return self.kickoff.date()


@dataclass(frozen=True)
class OddsQuote:
    """Quote di un singolo bookmaker su un singolo mercato di una partita.

    ``prices`` mappa la selezione (es. "1", "X", "2", "Over 2.5") alla quota
    decimale offerta. Perche' il devigging abbia senso, le selezioni devono
    formare un mercato completo e mutuamente esclusivo.
    """

    bookmaker: str
    market: str
    prices: dict[str, float]
    collected_at: datetime | None = None

    @property
    def overround(self) -> float:
        """Somma delle probabilita' implicite grezze: 1.06 = 6% di margine."""
        return sum(1.0 / p for p in self.prices.values())

    @property
    def margin(self) -> float:
        return self.overround - 1.0


@dataclass
class MatchOdds:
    """Tutte le quote raccolte per una partita, raggruppate per mercato."""

    match_id: str
    quotes: list[OddsQuote] = field(default_factory=list)

    def for_market(self, market: str) -> list[OddsQuote]:
        return [q for q in self.quotes if q.market == market]

    def best_price(self, market: str, selection: str) -> tuple[str, float] | None:
        """Bookmaker e quota migliore disponibile per una selezione.

        E' il prezzo su cui si gioca davvero: a parita' di probabilita', la
        quota piu' alta e' l'unica fonte di vantaggio che non dipende dal
        modello.
        """
        best: tuple[str, float] | None = None
        for q in self.for_market(market):
            price = q.prices.get(selection)
            if price is None:
                continue
            if best is None or price > best[1]:
                best = (q.bookmaker, price)
        return best
