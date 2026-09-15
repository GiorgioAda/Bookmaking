"""Modello Dixon-Coles con decadimento temporale.

Per la partita fra la squadra di casa ``i`` e quella in trasferta ``j`` nella
divisione ``d``:

    log lambda = base_d + att_i + dif_j + casa_d      (gol attesi dei padroni di casa)
    log mu     = base_d + att_j + dif_i               (gol attesi degli ospiti)

I gol sono due Poisson corrette dal fattore ``tau`` di Dixon-Coles, che
ricalibra i quattro punteggi bassi (0-0, 1-0, 0-1, 1-1) dove l'indipendenza fra
i due marcatori e' palesemente falsa: con ``rho`` negativo i pareggi a basso
punteggio diventano piu' probabili di quanto due Poisson indipendenti
prevedano.

Ogni partita pesa ``exp(-xi * giorni_di_distanza)``: la forma recente conta
piu' di quella di due stagioni fa, ma il passato non viene buttato via. Questo
e' anche il modo in cui "lo stato di forma" entra nel modello, senza bisogno di
una feature separata che finirebbe per contare due volte le stesse partite.

Una penalizzazione L2 su ``att``/``dif`` fa da prior gaussiano: le squadre con
poche partite vengono tirate verso la media del campionato invece di ricevere
rating estremi stimati su un pugno di risultati.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime

import numpy as np
from scipy.optimize import minimize
from scipy.stats import poisson

from bookmaking.domain import Match

MAX_GOALS = 15


@dataclass(frozen=True)
class FitConfig:
    """Iperparametri della stima.

    xi: decadimento giornaliero. 0.0035 ~ emivita di 200 giorni.
    l2: forza del prior verso la media (1/(2*sigma^2)); piu' alto = piu'
        prudente sulle squadre con pochi dati.
    unknown_attack / unknown_defence: rating assegnato a una squadra mai vista
        (tipicamente una neopromossa dalla terza divisione). I valori di default
        descrivono una squadra sotto la media; vanno ricalibrati sul backtest.
    """

    xi: float = 0.0035
    l2: float = 2.0
    rho_bounds: tuple[float, float] = (-0.25, 0.25)
    unknown_attack: float = -0.12
    unknown_defence: float = 0.12
    max_iter: int = 500


@dataclass
class DixonColesFit:
    """Parametri stimati, pronti per la previsione."""

    teams: list[str]
    divisions: list[str]
    attack: np.ndarray
    defence: np.ndarray
    base: np.ndarray
    home_adv: np.ndarray
    rho: float
    config: FitConfig
    reference_day: date
    n_matches: int
    effective_n: float
    log_likelihood: float   # verosimiglianza pesata, al netto della penalizzazione
    converged: bool
    _team_ix: dict[str, int] = field(init=False, repr=False)
    _div_ix: dict[str, int] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._team_ix = {t: i for i, t in enumerate(self.teams)}
        self._div_ix = {d: i for i, d in enumerate(self.divisions)}

    def knows(self, team: str) -> bool:
        return team in self._team_ix

    def rating(self, team: str) -> tuple[float, float]:
        """(attacco, difesa) di una squadra; difesa positiva = subisce di piu'."""
        ix = self._team_ix.get(team)
        if ix is None:
            return self.config.unknown_attack, self.config.unknown_defence
        return float(self.attack[ix]), float(self.defence[ix])

    def strength(self, team: str) -> float:
        """Indice sintetico di forza: attacco meno difesa. Solo per la UI."""
        att, dfn = self.rating(team)
        return att - dfn

    def expected_goals(self, home: str, away: str, division: str) -> tuple[float, float]:
        att_h, def_h = self.rating(home)
        att_a, def_a = self.rating(away)
        div = self._div_ix.get(division)
        if div is None:
            base, adv = float(np.mean(self.base)), float(np.mean(self.home_adv))
        else:
            base, adv = float(self.base[div]), float(self.home_adv[div])
        lam = math.exp(base + att_h + def_a + adv)
        mu = math.exp(base + att_a + def_h)
        return lam, mu

    def score_matrix(self, home: str, away: str, division: str,
                     max_goals: int = MAX_GOALS) -> np.ndarray:
        """Distribuzione congiunta dei punteggi: ``M[x, y] = P(casa=x, ospiti=y)``.

        E' la rappresentazione da cui si ricava *ogni* mercato (1X2, Over/Under,
        Goal/NoGoal, handicap, risultato esatto) in modo internamente coerente:
        un solo modello, niente stime scollegate mercato per mercato.
        """
        lam, mu = self.expected_goals(home, away, division)
        gx = np.arange(max_goals + 1)
        px = poisson.pmf(gx, lam)
        py = poisson.pmf(gx, mu)
        m = np.outer(px, py)
        m[0, 0] *= 1.0 - lam * mu * self.rho
        m[0, 1] *= 1.0 + lam * self.rho
        m[1, 0] *= 1.0 + mu * self.rho
        m[1, 1] *= 1.0 - self.rho
        m = np.clip(m, 0.0, None)
        total = m.sum()
        if total <= 0:
            raise ValueError("matrice dei punteggi degenere")
        return m / total


def _tau(x: np.ndarray, y: np.ndarray, lam: np.ndarray, mu: np.ndarray,
         rho: float) -> np.ndarray:
    t = np.ones_like(lam)
    m00 = (x == 0) & (y == 0)
    m01 = (x == 0) & (y == 1)
    m10 = (x == 1) & (y == 0)
    m11 = (x == 1) & (y == 1)
    t[m00] = 1.0 - lam[m00] * mu[m00] * rho
    t[m01] = 1.0 + lam[m01] * rho
    t[m10] = 1.0 + mu[m10] * rho
    t[m11] = 1.0 - rho
    return t


class DixonColes:
    """Stima del modello su uno storico di partite giocate."""

    def __init__(self, config: FitConfig | None = None) -> None:
        self.config = config or FitConfig()

    def fit(self, matches: list[Match], reference_day: date | None = None) -> DixonColesFit:
        played = [m for m in matches if m.played]
        if not played:
            raise ValueError("nessuna partita giocata su cui stimare il modello")

        ref = reference_day or max(m.day for m in played)
        teams = sorted({m.home for m in played} | {m.away for m in played})
        divisions = sorted({m.division for m in played})
        t_ix = {t: i for i, t in enumerate(teams)}
        d_ix = {d: i for i, d in enumerate(divisions)}
        n_t, n_d = len(teams), len(divisions)

        home = np.fromiter((t_ix[m.home] for m in played), dtype=np.int64, count=len(played))
        away = np.fromiter((t_ix[m.away] for m in played), dtype=np.int64, count=len(played))
        div = np.fromiter((d_ix[m.division] for m in played), dtype=np.int64, count=len(played))
        x = np.fromiter((m.home_goals for m in played), dtype=np.float64, count=len(played))
        y = np.fromiter((m.away_goals for m in played), dtype=np.float64, count=len(played))
        age = np.fromiter(((ref - m.day).days for m in played), dtype=np.float64, count=len(played))
        w = np.exp(-self.config.xi * np.clip(age, 0.0, None))

        # Punto di partenza: ogni squadra alla media, livello-gol della divisione
        # preso dai dati, vantaggio del fattore campo tipico del calcio europeo.
        theta0 = np.zeros(2 * n_t + 2 * n_d + 1)
        for d, ix in d_ix.items():
            sel = div == ix
            avg = max((x[sel].mean() + y[sel].mean()) / 2.0, 0.2)
            theta0[2 * n_t + ix] = math.log(avg)
            theta0[2 * n_t + n_d + ix] = 0.25
        theta0[-1] = -0.05

        def unpack(theta: np.ndarray):
            att = theta[:n_t]
            dfn = theta[n_t:2 * n_t]
            base = theta[2 * n_t:2 * n_t + n_d]
            adv = theta[2 * n_t + n_d:2 * n_t + 2 * n_d]
            return att, dfn, base, adv, float(theta[-1])

        def objective(theta: np.ndarray) -> tuple[float, np.ndarray]:
            att, dfn, base, adv, rho = unpack(theta)
            eta_l = base[div] + att[home] + dfn[away] + adv[div]
            eta_m = base[div] + att[away] + dfn[home]
            lam = np.exp(np.clip(eta_l, -8.0, 4.0))
            mu = np.exp(np.clip(eta_m, -8.0, 4.0))

            t = _tau(x, y, lam, mu, rho)
            t = np.clip(t, 1e-10, None)
            ll = w * (np.log(t) + x * eta_l - lam + y * eta_m - mu)
            total_ll = float(ll.sum())

            # Derivate di tau rispetto a lambda, mu, rho: non nulle solo sui
            # quattro punteggi che la correzione tocca.
            m00 = (x == 0) & (y == 0)
            m01 = (x == 0) & (y == 1)
            m10 = (x == 1) & (y == 0)
            m11 = (x == 1) & (y == 1)
            dt_dl = np.zeros_like(lam)
            dt_dm = np.zeros_like(lam)
            dt_dr = np.zeros_like(lam)
            dt_dl[m00] = -mu[m00] * rho
            dt_dl[m01] = rho
            dt_dm[m00] = -lam[m00] * rho
            dt_dm[m10] = rho
            dt_dr[m00] = -lam[m00] * mu[m00]
            dt_dr[m01] = lam[m01]
            dt_dr[m10] = mu[m10]
            dt_dr[m11] = -1.0

            g_l = w * (x - lam + lam * dt_dl / t)
            g_m = w * (y - mu + mu * dt_dm / t)
            g_r = float((w * dt_dr / t).sum())

            g_att = np.bincount(home, weights=g_l, minlength=n_t) + \
                np.bincount(away, weights=g_m, minlength=n_t)
            g_def = np.bincount(away, weights=g_l, minlength=n_t) + \
                np.bincount(home, weights=g_m, minlength=n_t)
            g_base = np.bincount(div, weights=g_l + g_m, minlength=n_d)
            g_adv = np.bincount(div, weights=g_l, minlength=n_d)

            pen = self.config.l2 * float((att ** 2).sum() + (dfn ** 2).sum())
            g_att -= 2.0 * self.config.l2 * att
            g_def -= 2.0 * self.config.l2 * dfn

            grad = np.concatenate([g_att, g_def, g_base, g_adv, [g_r]])
            # minimize() vuole il negativo: massimizziamo la verosimiglianza.
            return -(total_ll - pen), -grad

        lo, hi = self.config.rho_bounds
        bounds = [(-3.0, 3.0)] * (2 * n_t) + [(-3.0, 2.0)] * n_d + \
                 [(-1.0, 1.0)] * n_d + [(lo, hi)]

        res = minimize(objective, theta0, jac=True, method="L-BFGS-B",
                       bounds=bounds, options={"maxiter": self.config.max_iter})
        att, dfn, base, adv, rho = unpack(res.x)
        penalty = self.config.l2 * float((att ** 2).sum() + (dfn ** 2).sum())

        return DixonColesFit(
            teams=teams,
            divisions=divisions,
            attack=att.copy(),
            defence=dfn.copy(),
            base=base.copy(),
            home_adv=adv.copy(),
            rho=rho,
            config=self.config,
            reference_day=ref,
            n_matches=len(played),
            effective_n=float(w.sum()),
            log_likelihood=float(-res.fun + penalty),
            converged=bool(res.success),
        )
