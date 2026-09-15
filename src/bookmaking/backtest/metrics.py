"""Misure di accuratezza delle previsioni.

"Quante ne ho indovinate" e' la metrica sbagliata: un modello che dice 1-X-2 al
40/30/30 non indovina quasi mai eppure puo' essere ottimo. Cio' che conta e' se
le probabilita' dichiarate corrispondono alle frequenze reali, e quanto sono
decise quando hanno ragione.

Le tre misure usate qui:

- **log loss**: punisce duramente la sicurezza mal riposta. E' la metrica da
  guardare per scegliere gli iperparametri.
- **Brier**: errore quadratico sulle probabilita', piu' stabile e leggibile.
- **RPS** (ranked probability score): tiene conto dell'ordine 1 < X < 2. Dare
  il 70% alla vittoria in casa quando vince il fuori casa e' un errore
  peggiore che darlo quando finisce in pareggio, e RPS e' l'unica delle tre a
  saperlo. Per l'1X2 e' lo standard in letteratura.

A queste si aggiunge la **calibrazione**: sulle partite a cui il modello ha
dato il 30%, l'esito si e' verificato davvero nel 30% dei casi? Un modello
scalibrato produce vantaggi fasulli e puntate sbagliate, anche quando ordina
correttamente le partite.
"""

from __future__ import annotations

import numpy as np

EPS = 1e-15
ORDER_1X2 = ("1", "X", "2")


def _matrix(probs: list[dict[str, float]], keys: tuple[str, ...]) -> np.ndarray:
    return np.array([[p.get(k, 0.0) for k in keys] for p in probs], dtype=float)


def _onehot(outcomes: list[str], keys: tuple[str, ...]) -> np.ndarray:
    ix = {k: i for i, k in enumerate(keys)}
    out = np.zeros((len(outcomes), len(keys)))
    for r, o in enumerate(outcomes):
        out[r, ix[o]] = 1.0
    return out


def log_loss(probs: list[dict[str, float]], outcomes: list[str],
             keys: tuple[str, ...] = ORDER_1X2) -> float:
    p = np.clip(_matrix(probs, keys), EPS, 1.0)
    y = _onehot(outcomes, keys)
    return float(-np.mean(np.sum(y * np.log(p), axis=1)))


def brier_score(probs: list[dict[str, float]], outcomes: list[str],
                keys: tuple[str, ...] = ORDER_1X2) -> float:
    p = _matrix(probs, keys)
    y = _onehot(outcomes, keys)
    return float(np.mean(np.sum((p - y) ** 2, axis=1)))


def rps(probs: list[dict[str, float]], outcomes: list[str],
        keys: tuple[str, ...] = ORDER_1X2) -> float:
    """Ranked probability score: piu' basso e' meglio, 0 = previsione perfetta."""
    p = _matrix(probs, keys)
    y = _onehot(outcomes, keys)
    cp = np.cumsum(p, axis=1)[:, :-1]
    cy = np.cumsum(y, axis=1)[:, :-1]
    return float(np.mean(np.sum((cp - cy) ** 2, axis=1) / (len(keys) - 1)))


def accuracy(probs: list[dict[str, float]], outcomes: list[str],
             keys: tuple[str, ...] = ORDER_1X2) -> float:
    p = _matrix(probs, keys)
    picked = [keys[i] for i in np.argmax(p, axis=1)]
    return float(np.mean([a == b for a, b in zip(picked, outcomes)]))


def calibration_table(probabilities: list[float], hits: list[bool],
                      bins: int = 10) -> list[dict[str, float]]:
    """Confronto fra probabilita' dichiarata e frequenza osservata, per fasce."""
    p = np.asarray(probabilities, dtype=float)
    h = np.asarray(hits, dtype=bool)
    edges = np.linspace(0.0, 1.0, bins + 1)
    rows = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = (p >= lo) & (p < hi if hi < 1.0 else p <= hi)
        n = int(sel.sum())
        if n == 0:
            continue
        rows.append({
            "da": float(lo), "a": float(hi), "n": n,
            "prob_media": float(p[sel].mean()),
            "frequenza_reale": float(h[sel].mean()),
            "scarto": float(h[sel].mean() - p[sel].mean()),
        })
    return rows


def summarise(probs: list[dict[str, float]], outcomes: list[str],
              keys: tuple[str, ...] = ORDER_1X2) -> dict[str, float]:
    return {
        "n": len(outcomes),
        "log_loss": log_loss(probs, outcomes, keys),
        "brier": brier_score(probs, outcomes, keys),
        "rps": rps(probs, outcomes, keys),
        "accuratezza": accuracy(probs, outcomes, keys),
    }


def baseline_uniform(n_outcomes: int = 3) -> dict[str, float]:
    return {k: 1.0 / n_outcomes for k in ORDER_1X2[:n_outcomes]}


def roi(stakes: list[float], returns: list[float]) -> dict[str, float]:
    """Rendimento di una serie di giocate. ``returns`` = incasso lordo, 0 se persa."""
    s = float(np.sum(stakes))
    r = float(np.sum(returns))
    return {
        "puntato": s,
        "incassato": r,
        "profitto": r - s,
        "roi": (r - s) / s if s > 0 else 0.0,
        "n_giocate": len(stakes),
    }
