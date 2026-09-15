"""Fusione fra modello statistico e mercato, e calcolo del vantaggio.

Il modello e il mercato sanno cose diverse. Il modello conosce cinque anni di
risultati e li pesa senza emotivita'; il mercato conosce l'undici titolare
uscito un'ora prima, l'infortunio in rifinitura e la squalifica, cose che nei
gol storici non compaiono. Ignorare del tutto il mercato significa scambiare
per vantaggio quello che spesso e' solo informazione mancante.

La fusione avviene in scala logaritmica (pool logaritmico):

    p ∝ p_modello^w · p_mercato^(1-w)

con ``w`` che decide chi prevale. Con ``w`` alto il modello comanda, come
richiesto; il termine di mercato resta come freno sui casi in cui il modello e'
clamorosamente fuori scala, e vale la pena tenerlo anche solo per quello.
Il pool logaritmico e' preferibile alla media semplice perche' non produce
probabilita' gonfiate quando le due fonti sono in forte disaccordo.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_MODEL_WEIGHT = 0.65


def blend_probabilities(model: dict[str, float],
                        market: dict[str, float],
                        model_weight: float = DEFAULT_MODEL_WEIGHT) -> dict[str, float]:
    """Pool logaritmico fra probabilita' del modello e del mercato."""
    if not 0.0 <= model_weight <= 1.0:
        raise ValueError("model_weight deve stare fra 0 e 1")
    keys = sorted(set(model) & set(market))
    if not keys:
        raise ValueError("modello e mercato non condividono selezioni")
    pm = np.array([max(model[k], 1e-9) for k in keys])
    pk = np.array([max(market[k], 1e-9) for k in keys])
    log_p = model_weight * np.log(pm) + (1.0 - model_weight) * np.log(pk)
    p = np.exp(log_p - log_p.max())
    p /= p.sum()
    return {k: float(v) for k, v in zip(keys, p)}


@dataclass(frozen=True)
class Edge:
    """Valutazione di una singola selezione a una quota concreta."""

    market: str
    selection: str
    bookmaker: str
    price: float
    p_model: float
    p_market: float
    p_final: float
    n_books: int = 0
    match_id: str = ""
    label: str = ""          # es. "Inter - Milan", per mostrarlo all'utente

    @property
    def fair_price(self) -> float:
        return 1.0 / self.p_final if self.p_final > 0 else float("inf")

    @property
    def ev(self) -> float:
        """Valore atteso per euro puntato: 0.04 = +4% atteso sulla puntata."""
        return self.p_final * self.price - 1.0

    @property
    def edge_vs_market(self) -> float:
        """Di quanto il modello si discosta dal mercato su questa selezione."""
        return self.p_final - self.p_market

    @property
    def price_ratio(self) -> float:
        """Quota offerta / quota equa. Sopra 1 significa prezzo favorevole."""
        return self.price / self.fair_price if self.fair_price else 0.0

    def kelly(self) -> float:
        """Frazione di Kelly piena. Negativa = nessuna scommessa."""
        b = self.price - 1.0
        if b <= 0:
            return 0.0
        return (self.p_final * self.price - 1.0) / b


def evaluate_selection(market: str, selection: str, bookmaker: str, price: float,
                       p_model: float, p_market: float, n_books: int = 0,
                       model_weight: float = DEFAULT_MODEL_WEIGHT) -> Edge:
    """Valuta una selezione binaria fondendo modello e mercato su quella sola voce.

    Per un mercato completo conviene fondere tutte le selezioni insieme con
    ``blend_probabilities``: qui la fusione e' fatta sul singolo esito contro il
    suo complemento, utile quando del mercato si ha solo quella quota.
    """
    blended = blend_probabilities(
        {"si": p_model, "no": 1.0 - p_model},
        {"si": p_market, "no": 1.0 - p_market},
        model_weight,
    )
    return Edge(market=market, selection=selection, bookmaker=bookmaker, price=price,
                p_model=p_model, p_market=p_market, p_final=blended["si"], n_books=n_books)


def find_edges(model_probs: dict[str, float],
               market_probs: dict[str, float],
               prices: dict[str, tuple[str, float]],
               market: str,
               model_weight: float = DEFAULT_MODEL_WEIGHT,
               n_books: int = 0) -> list[Edge]:
    """Valuta ogni selezione di un mercato completo e ordina per valore atteso."""
    final = blend_probabilities(model_probs, market_probs, model_weight)
    edges = []
    for sel, (book, price) in prices.items():
        if sel not in final:
            continue
        edges.append(Edge(market=market, selection=sel, bookmaker=book, price=price,
                          p_model=model_probs.get(sel, 0.0),
                          p_market=market_probs.get(sel, 0.0),
                          p_final=final[sel], n_books=n_books))
    edges.sort(key=lambda e: e.ev, reverse=True)
    return edges
