"""Consenso di mercato: da molte quote a una sola probabilita' di riferimento.

Due avvertenze pratiche pesano piu' della matematica.

La prima: non tutti i bookmaker sono fonti di informazione equivalenti. Un
exchange (Betfair) e un banco che accetta volumi alti senza limitare i vincenti
(Pinnacle) hanno prezzi molto piu' informativi di un banco retail, che il
prezzo lo copia e ci carica sopra margine. Il consenso pesa di conseguenza.

La seconda, meno ovvia: molti bookmaker italiani non sono osservazioni
indipendenti. Goldbet, Better e Lottomatica appartengono allo stesso gruppo e
girano sullo stesso palinsesto; contarli come tre pareri separati significa
triplicare il peso di un parere solo. Per questo i book sono raggruppati e il
peso viene diviso all'interno del gruppo.

Resta la distinzione centrale di tutto il sistema:
  - la probabilita' di consenso serve a stimare la *quota vera*;
  - la quota su cui si gioca e' la *migliore disponibile* fra i book italiani.
La differenza fra le due e' il margine di vantaggio.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bookmaking.domain import MatchOdds, OddsQuote
from bookmaking.pricing.devig import DevigMethod, devig, margin

# Peso per qualita' informativa del prezzo. Non e' una classifica commerciale:
# misura quanto quel prezzo anticipa il risultato.
SHARPNESS: dict[str, float] = {
    "betfair_ex": 1.00, "betfair": 1.00, "pinnacle": 1.00, "smarkets": 0.85,
    "matchbook": 0.80, "bet365": 0.55, "unibet": 0.45, "williamhill": 0.40,
    "marathonbet": 0.45, "betfair_sb": 0.40,
    # book italiani ADM: prezzo retail, utile soprattutto per trovare la quota
    # piu' alta su cui giocare davvero
    "goldbet": 0.30, "lottomatica": 0.30, "better": 0.30, "sisal": 0.30,
    "snai": 0.32, "eurobet": 0.30, "planetwin365": 0.30, "betflag": 0.25,
    "admiralbet": 0.25, "netbet": 0.25, "bwin": 0.30, "starcasino": 0.25,
}

# Book che condividono palinsesto o proprieta': dentro il gruppo il peso si divide.
CORRELATION_GROUPS: dict[str, str] = {
    "goldbet": "lottomatica", "better": "lottomatica", "lottomatica": "lottomatica",
    "sisal": "sisal", "snai": "snai", "eurobet": "eurobet",
    "betfair_ex": "exchange", "smarkets": "exchange", "matchbook": "exchange",
}

ITALIAN_BOOKS: frozenset[str] = frozenset({
    "goldbet", "lottomatica", "better", "sisal", "snai", "eurobet",
    "planetwin365", "betflag", "admiralbet", "netbet", "bwin", "starcasino",
})

DEFAULT_SHARPNESS = 0.25


@dataclass
class BookWeights:
    """Politica di pesatura dei bookmaker nel consenso."""

    sharpness: dict[str, float] = field(default_factory=lambda: dict(SHARPNESS))
    groups: dict[str, str] = field(default_factory=lambda: dict(CORRELATION_GROUPS))
    default: float = DEFAULT_SHARPNESS
    margin_sensitivity: float = 0.5
    reference_margin: float = 0.03

    def raw(self, book: str) -> float:
        return self.sharpness.get(book.lower(), self.default)

    def weights_for(self, quotes: list[OddsQuote]) -> dict[str, float]:
        """Peso finale per bookmaker: qualita', margine stretto, anti-duplicazione."""
        out: dict[str, float] = {}
        for q in quotes:
            book = q.bookmaker.lower()
            w = self.raw(book)
            if self.margin_sensitivity > 0:
                m = max(margin(q.prices), 1e-4)
                # un margine piu' stretto del riferimento alza il peso, uno piu'
                # largo lo abbassa, in modo smorzato
                w *= (self.reference_margin / m) ** self.margin_sensitivity
            out[q.bookmaker] = w

        # peso diviso fra book dello stesso gruppo
        members: dict[str, list[str]] = {}
        for book in out:
            g = self.groups.get(book.lower())
            if g:
                members.setdefault(g, []).append(book)
        for group_books in members.values():
            if len(group_books) > 1:
                for b in group_books:
                    out[b] /= len(group_books)
        return out


def consensus_probabilities(quotes: list[OddsQuote],
                            weights: BookWeights | None = None,
                            method: DevigMethod | str = DevigMethod.SHIN,
                            min_books: int = 2) -> dict[str, float]:
    """Probabilita' di consenso su un mercato, a partire dalle quote di piu' book.

    Ogni book viene prima ripulito del suo margine, poi i pareri vengono mediati
    con i pesi. Mediare le quote grezze sarebbe sbagliato: si mediarebbero anche
    i margini, che sono rumore, non informazione.
    """
    if not quotes:
        raise ValueError("nessuna quota disponibile")
    weights = weights or BookWeights()
    selections = sorted({s for q in quotes for s in q.prices})
    w_map = weights.weights_for(quotes)

    acc = np.zeros(len(selections))
    tot = 0.0
    used = 0
    for q in quotes:
        if set(q.prices) != set(selections):
            continue        # mercato incompleto: non si puo' togliere il margine
        p = devig(q.prices, method)
        w = w_map.get(q.bookmaker, weights.default)
        acc += w * np.array([p[s] for s in selections])
        tot += w
        used += 1

    if used == 0 or tot <= 0:
        raise ValueError("nessun book con mercato completo")
    if used < min_books:
        # Con un solo book il "consenso" e' solo l'opinione di quel book: si
        # restituisce comunque, ma chi chiama deve saperlo (vedi n_books).
        pass
    p = acc / tot
    p = p / p.sum()
    return {s: float(v) for s, v in zip(selections, p)}


def fair_odds(probabilities: dict[str, float]) -> dict[str, float]:
    """Quota equa: l'inverso della probabilita', senza alcun margine."""
    return {k: (1.0 / v if v > 0 else float("inf")) for k, v in probabilities.items()}


def best_italian_price(odds: MatchOdds, market: str, selection: str,
                       allowed: frozenset[str] | None = None) -> tuple[str, float] | None:
    """Quota piu' alta fra i book italiani: e' il prezzo realmente giocabile."""
    allowed = allowed or ITALIAN_BOOKS
    best: tuple[str, float] | None = None
    for q in odds.for_market(market):
        if q.bookmaker.lower() not in allowed:
            continue
        price = q.prices.get(selection)
        if price is None:
            continue
        if best is None or price > best[1]:
            best = (q.bookmaker, price)
    return best


def market_summary(quotes: list[OddsQuote]) -> dict[str, float | int]:
    return {
        "n_books": len(quotes),
        "margine_medio": float(np.mean([margin(q.prices) for q in quotes])) if quotes else 0.0,
        "margine_minimo": float(np.min([margin(q.prices) for q in quotes])) if quotes else 0.0,
    }
