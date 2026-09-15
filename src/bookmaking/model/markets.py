"""Dalla matrice dei punteggi ai mercati scommettibili.

Tutto qui dentro legge la stessa matrice ``M[x, y] = P(casa=x, ospiti=y)``.
Ne segue una proprieta' che vale la pena rendere esplicita: le probabilita' di
mercati diversi sulla stessa partita sono automaticamente coerenti (P(Over 2.5)
e P(1) non possono contraddirsi), ed e' possibile valutare le multiple con le
gambe sulla stessa partita senza assumerle indipendenti, perche' la congiunta
c'e' gia'.
"""

from __future__ import annotations

import numpy as np

MARKET_1X2 = "1X2"
MARKET_DC = "DoppiaChance"
MARKET_OU = "OverUnder"
MARKET_BTTS = "GoalNoGoal"
MARKET_AH = "HandicapAsiatico"


def outcome_1x2(m: np.ndarray) -> dict[str, float]:
    home = float(np.tril(m, -1).sum())   # x > y
    away = float(np.triu(m, 1).sum())    # x < y
    draw = float(np.trace(m))
    return {"1": home, "X": draw, "2": away}


def double_chance(m: np.ndarray) -> dict[str, float]:
    p = outcome_1x2(m)
    return {"1X": p["1"] + p["X"], "12": p["1"] + p["2"], "X2": p["X"] + p["2"]}


def over_under(m: np.ndarray, line: float) -> dict[str, float]:
    """Linee intere (2.0) incluse: la quota di push va trattata a parte."""
    n = m.shape[0]
    totals = np.add.outer(np.arange(n), np.arange(n))
    over = float(m[totals > line].sum())
    under = float(m[totals < line].sum())
    push = float(m[totals == line].sum())
    out = {f"Over {line}": over, f"Under {line}": under}
    if push > 0:
        out[f"Push {line}"] = push
    return out


def btts(m: np.ndarray) -> dict[str, float]:
    both = float(m[1:, 1:].sum())
    return {"Goal": both, "NoGoal": 1.0 - both}


def asian_handicap(m: np.ndarray, line: float) -> dict[str, float]:
    """Handicap sulla squadra di casa. line=-0.5 => la casa deve vincere.

    Le linee con quarto (es. -0.25) dividono la giocata in due meta'. I valori
    restituiti vanno letti come *quota attesa di puntata* vinta, persa e
    rimborsata: essendo il payout lineare nella puntata, il valore atteso
    calcolato su questi numeri resta esatto.
    """
    n = m.shape[0]
    diff = np.subtract.outer(np.arange(n), np.arange(n)).astype(float)
    adj = diff + line
    if abs(line * 4 - round(line * 4)) > 1e-9:
        raise ValueError("linea handicap non valida")
    quarter = abs((line * 2) - round(line * 2)) > 1e-9
    if quarter:
        lo, hi = line - 0.25, line + 0.25
        a = asian_handicap(m, lo)
        b = asian_handicap(m, hi)
        keys = ("Casa", "Ospiti", "Rimborso")
        mixed = {k: (a.get(k, 0.0) + b.get(k, 0.0)) / 2.0 for k in keys}
        return {k: v for k, v in mixed.items() if v > 0}
    win = float(m[adj > 0].sum())
    lose = float(m[adj < 0].sum())
    push = float(m[adj == 0].sum())
    out = {"Casa": win, "Ospiti": lose}
    if push > 0:
        out["Rimborso"] = push
    return out


def correct_score(m: np.ndarray, top: int = 10) -> dict[str, float]:
    flat = [(f"{x}-{y}", float(m[x, y])) for x in range(m.shape[0]) for y in range(m.shape[1])]
    flat.sort(key=lambda kv: kv[1], reverse=True)
    return dict(flat[:top])


def all_markets(m: np.ndarray,
                ou_lines: tuple[float, ...] = (0.5, 1.5, 2.5, 3.5, 4.5),
                ah_lines: tuple[float, ...] = (-1.5, -1.0, -0.5, 0.0, 0.5, 1.0)) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {
        MARKET_1X2: outcome_1x2(m),
        MARKET_DC: double_chance(m),
        MARKET_BTTS: btts(m),
    }
    for line in ou_lines:
        out[f"{MARKET_OU} {line}"] = over_under(m, line)
    for line in ah_lines:
        out[f"{MARKET_AH} {line}"] = asian_handicap(m, line)
    return out


def selection_mask(m: np.ndarray, market: str, selection: str) -> np.ndarray:
    """Maschera booleana dei punteggi che fanno vincere una selezione.

    Serve per valutare correttamente le multiple con piu' gambe sulla stessa
    partita: si interseca sulla congiunta invece di moltiplicare probabilita'
    che non sono affatto indipendenti.
    """
    n = m.shape[0]
    xs = np.arange(n)
    diff = np.subtract.outer(xs, xs)
    totals = np.add.outer(xs, xs)

    if market == MARKET_1X2:
        return {"1": diff > 0, "X": diff == 0, "2": diff < 0}[selection]
    if market == MARKET_DC:
        return {"1X": diff >= 0, "12": diff != 0, "X2": diff <= 0}[selection]
    if market == MARKET_BTTS:
        both = np.zeros((n, n), dtype=bool)
        both[1:, 1:] = True
        return both if selection == "Goal" else ~both
    if market.startswith(MARKET_OU):
        line = float(market.split()[-1])
        return totals > line if selection.startswith("Over") else totals < line
    if market.startswith(MARKET_AH):
        line = float(market.split()[-1])
        adj = diff + line
        return adj > 0 if selection == "Casa" else adj < 0
    raise ValueError(f"mercato non gestito: {market}")
