"""Generatore di campionati sintetici con parametri noti.

Serve a verificare il sistema quando i dati veri non ci sono, e a rispondere a
una domanda che i dati veri non possono risolvere: *se* il modello fosse
corretto, quanto bene ne ricostruirebbe i parametri con il numero di partite
che abbiamo davvero? Qui la verita' e' nota per costruzione, quindi la stima si
puo' confrontare con essa.

La simulazione riproduce le caratteristiche che contano: due divisioni per
nazione, promozioni e retrocessioni a fine stagione, forza delle squadre che
deriva lentamente nel tempo, divisione inferiore mediamente piu' debole.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np

from bookmaking.domain import Match


@dataclass
class SimulatedWorld:
    matches: list[Match]
    true_lambda: dict[str, float]
    true_mu: dict[str, float]
    true_attack: dict[str, float]
    true_defence: dict[str, float]
    home_adv: float
    rho: float
    base: dict[str, float]


def simulate_country(n_seasons: int = 5,
                     teams_per_division: int = 18,
                     tier1: str = "IT1",
                     tier2: str = "IT2",
                     start: datetime = datetime(2019, 8, 15),
                     home_adv: float = 0.26,
                     rho: float = -0.11,
                     base_tier1: float = 0.18,
                     base_tier2: float = 0.10,
                     strength_sd: float = 0.30,
                     drift: float = 0.05,
                     n_promoted: int = 3,
                     seed: int = 42) -> SimulatedWorld:
    """Genera piu' stagioni di due divisioni collegate da promozioni e retrocessioni."""
    rng = np.random.default_rng(seed)
    n_total = teams_per_division * 2
    names = [f"Team{i:02d}" for i in range(n_total)]

    # Le squadre della prima divisione partono piu' forti; dentro ogni
    # divisione la forza e' dispersa.
    attack = {}
    defence = {}
    for i, name in enumerate(names):
        top = i < teams_per_division
        attack[name] = rng.normal(0.12 if top else -0.12, strength_sd)
        defence[name] = rng.normal(-0.12 if top else 0.12, strength_sd)

    divisions = {name: (tier1 if i < teams_per_division else tier2)
                 for i, name in enumerate(names)}
    base = {tier1: base_tier1, tier2: base_tier2}

    matches: list[Match] = []
    true_lambda: dict[str, float] = {}
    true_mu: dict[str, float] = {}
    day = start
    for season_ix in range(n_seasons):
        season = f"{start.year + season_ix}-{start.year + season_ix + 1}"
        season_start = day
        points: dict[str, float] = {n: 0.0 for n in names}

        for div in (tier1, tier2):
            squad = [n for n in names if divisions[n] == div]
            fixtures = [(h, a) for h in squad for a in squad if h != a]
            rng.shuffle(fixtures)
            span = 270  # una stagione occupa circa nove mesi
            for k, (h, a) in enumerate(fixtures):
                kickoff = season_start + timedelta(days=int(k * span / max(len(fixtures), 1)))
                lam = np.exp(base[div] + attack[h] - defence[a] + home_adv)
                mu = np.exp(base[div] + attack[a] - defence[h])
                hg, ag = _draw_score(rng, lam, mu, rho)
                mid = f"{div}-{season}-{k}-{h}-{a}"
                matches.append(Match(div, season, kickoff, h, a, hg, ag, match_id=mid))
                true_lambda[mid] = float(lam)
                true_mu[mid] = float(mu)
                points[h] += 3 if hg > ag else (1 if hg == ag else 0)
                points[a] += 3 if ag > hg else (1 if hg == ag else 0)

        day = season_start + timedelta(days=330)

        # deriva della forza fra una stagione e l'altra
        for n in names:
            attack[n] += rng.normal(0, drift)
            defence[n] += rng.normal(0, drift)

        if season_ix < n_seasons - 1:
            _promote_relegate(points, divisions, tier1, tier2, n_promoted)

    return SimulatedWorld(matches=matches, true_lambda=true_lambda, true_mu=true_mu,
                          true_attack=dict(attack),
                          true_defence=dict(defence), home_adv=home_adv,
                          rho=rho, base=base)


def _draw_score(rng: np.random.Generator, lam: float, mu: float,
                rho: float, max_goals: int = 12) -> tuple[int, int]:
    """Estrae un punteggio dalla congiunta Dixon-Coles (non da due Poisson libere)."""
    gx = np.arange(max_goals + 1)
    from scipy.stats import poisson
    m = np.outer(poisson.pmf(gx, lam), poisson.pmf(gx, mu))
    m[0, 0] *= 1.0 - lam * mu * rho
    m[0, 1] *= 1.0 + lam * rho
    m[1, 0] *= 1.0 + mu * rho
    m[1, 1] *= 1.0 - rho
    m = np.clip(m, 0.0, None)
    m /= m.sum()
    flat = rng.choice(m.size, p=m.ravel())
    return int(flat // m.shape[1]), int(flat % m.shape[1])


def _promote_relegate(points: dict[str, float], divisions: dict[str, str],
                      tier1: str, tier2: str, n: int) -> None:
    top = sorted([t for t in divisions if divisions[t] == tier1],
                 key=lambda t: points[t])
    bottom = sorted([t for t in divisions if divisions[t] == tier2],
                    key=lambda t: points[t], reverse=True)
    for t in top[:n]:
        divisions[t] = tier2
    for t in bottom[:n]:
        divisions[t] = tier1
