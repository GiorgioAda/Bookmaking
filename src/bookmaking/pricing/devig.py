"""Rimozione del margine del bookmaker.

Le quote esposte non sono probabilita': la loro somma di probabilita' implicite
supera 1, e l'eccesso e' il margine del banco (in Italia tipicamente il 4-7%
sull'1X2). Per capire *cosa pensa davvero il mercato* bisogna togliere quel
margine, e il modo in cui lo si toglie non e' un dettaglio: metodi diversi
spostano la probabilita' stimata di punti percentuali interi sugli outsider, e
quindi spostano il presunto valore di una giocata.

Il metodo moltiplicativo e' il piu' semplice e il piu' sbagliato sugli
outsider, perche' assume che il margine sia distribuito in proporzione alla
probabilita'. In realta' i bookmaker caricano di piu' sulle quote alte
(favourite-longshot bias). Shin e il metodo potenza tengono conto di questa
asimmetria; per l'1X2 il default ragionevole e' Shin.
"""

from __future__ import annotations

from enum import Enum

import numpy as np
from scipy.optimize import brentq


class DevigMethod(str, Enum):
    MULTIPLICATIVE = "multiplicative"
    ADDITIVE = "additive"
    POWER = "power"
    SHIN = "shin"
    ODDS_RATIO = "odds_ratio"


def implied(prices: dict[str, float]) -> dict[str, float]:
    """Probabilita' implicite grezze, margine incluso (sommano a > 1)."""
    _validate(prices)
    return {k: 1.0 / v for k, v in prices.items()}


def _validate(prices: dict[str, float]) -> None:
    if len(prices) < 2:
        raise ValueError("servono almeno due selezioni per togliere il margine")
    for k, v in prices.items():
        if not np.isfinite(v) or v <= 1.0:
            raise ValueError(f"quota non valida per {k!r}: {v}")


def devig(prices: dict[str, float],
          method: DevigMethod | str = DevigMethod.SHIN) -> dict[str, float]:
    """Probabilita' eque (sommano a 1) implicite in un mercato quotato."""
    _validate(prices)
    method = DevigMethod(method)
    keys = list(prices)
    q = np.array([1.0 / prices[k] for k in keys], dtype=float)

    if method is DevigMethod.MULTIPLICATIVE:
        p = q / q.sum()
    elif method is DevigMethod.ADDITIVE:
        p = q - (q.sum() - 1.0) / len(q)
        if np.any(p <= 0):   # succede sui mercati molto sbilanciati
            p = q / q.sum()
    elif method is DevigMethod.POWER:
        p = _power(q)
    elif method is DevigMethod.SHIN:
        p = _shin(q)
    elif method is DevigMethod.ODDS_RATIO:
        p = _odds_ratio(q)
    else:  # pragma: no cover
        raise ValueError(method)

    p = np.clip(p, 1e-9, None)
    p = p / p.sum()
    return {k: float(v) for k, v in zip(keys, p)}


def _power(q: np.ndarray) -> np.ndarray:
    """Cerca k con ``sum(q_i^k) = 1``: comprime le quote alte piu' delle basse."""
    def f(k: float) -> float:
        return float(np.sum(q ** k) - 1.0)
    try:
        k = brentq(f, 0.2, 3.0, xtol=1e-12)
    except ValueError:
        return q / q.sum()
    return q ** k


def _shin(q: np.ndarray) -> np.ndarray:
    """Modello di Shin: il margine e' la difesa del banco dagli scommettitori informati.

    ``z`` e' la quota stimata di volume proveniente da chi sa qualcosa in piu'.
    Si ricava imponendo che le probabilita' corrette sommino a 1.
    """
    booksum = float(q.sum())
    if booksum <= 1.0:
        return q / booksum

    def p_of_z(z: float) -> np.ndarray:
        inner = z ** 2 + 4.0 * (1.0 - z) * (q ** 2) / booksum
        return (np.sqrt(inner) - z) / (2.0 * (1.0 - z))

    def f(z: float) -> float:
        return float(p_of_z(z).sum() - 1.0)

    try:
        z = brentq(f, 1e-12, 0.9, xtol=1e-12)
    except ValueError:
        return q / booksum
    return p_of_z(z)


def _odds_ratio(q: np.ndarray) -> np.ndarray:
    """Metodo odds-ratio: un solo fattore moltiplicativo sulle quote in scala logit."""
    def p_of_c(c: float) -> np.ndarray:
        odds = q / (1.0 - q)
        adj = odds / c
        return adj / (1.0 + adj)

    def f(c: float) -> float:
        return float(p_of_c(c).sum() - 1.0)

    try:
        c = brentq(f, 1e-6, 1e6, xtol=1e-12)
    except ValueError:
        return q / q.sum()
    return p_of_c(c)


def margin(prices: dict[str, float]) -> float:
    """Margine del bookmaker sul mercato, in frazione (0.05 = 5%)."""
    return sum(1.0 / v for v in prices.values()) - 1.0
