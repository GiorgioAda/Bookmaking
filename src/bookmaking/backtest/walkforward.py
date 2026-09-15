"""Backtest walk-forward: l'unico modo onesto di misurare il modello.

La regola e' una sola e non ammette eccezioni: per prevedere la partita del 12
marzo si puo' usare esclusivamente cio' che era noto l'11 marzo. Qualunque
scorciatoia (stimare una volta su tutto lo storico e poi "verificare" sulle
stesse partite) produce numeri splendidi e del tutto falsi, perche' il modello
ha gia' visto i risultati che deve indovinare.

Il modello viene ristimato periodicamente invece che a ogni partita: i rating
si muovono lentamente e ristimare ogni giorno costerebbe ore senza cambiare le
previsioni in modo apprezzabile. La finestra di ristima e' un parametro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

from bookmaking.backtest.metrics import calibration_table, summarise
from bookmaking.domain import Match
from bookmaking.model.dixon_coles import DixonColes, DixonColesFit, FitConfig
from bookmaking.model.markets import outcome_1x2


@dataclass
class Prediction:
    match: Match
    probs: dict[str, float]
    fitted_on: date
    train_size: int

    @property
    def outcome(self) -> str:
        return self.match.result.value


@dataclass
class WalkForwardResult:
    predictions: list[Prediction] = field(default_factory=list)
    n_fits: int = 0

    @property
    def probs(self) -> list[dict[str, float]]:
        return [p.probs for p in self.predictions]

    @property
    def outcomes(self) -> list[str]:
        return [p.outcome for p in self.predictions]

    def metrics(self) -> dict[str, float]:
        if not self.predictions:
            return {"n": 0}
        out = summarise(self.probs, self.outcomes)
        out["n_stime"] = self.n_fits
        return out

    def metrics_by_division(self) -> dict[str, dict[str, float]]:
        groups: dict[str, list[Prediction]] = {}
        for p in self.predictions:
            groups.setdefault(p.match.division, []).append(p)
        return {d: summarise([p.probs for p in ps], [p.outcome for p in ps])
                for d, ps in sorted(groups.items())}

    def calibration(self, selection: str = "1", bins: int = 10) -> list[dict[str, float]]:
        probs = [p.probs[selection] for p in self.predictions]
        hits = [p.outcome == selection for p in self.predictions]
        return calibration_table(probs, hits, bins)


class WalkForward:
    """Esegue il backtest su uno storico ordinato nel tempo."""

    def __init__(self, config: FitConfig | None = None,
                 refit_every_days: int = 7,
                 min_train_matches: int = 200,
                 burn_in_days: int = 365) -> None:
        self.config = config or FitConfig()
        self.refit_every_days = refit_every_days
        self.min_train_matches = min_train_matches
        self.burn_in_days = burn_in_days

    def run(self, matches: list[Match], verbose: bool = False) -> WalkForwardResult:
        played = sorted((m for m in matches if m.played), key=lambda m: m.kickoff)
        if not played:
            raise ValueError("nessuna partita giocata")

        start_day = played[0].day + timedelta(days=self.burn_in_days)
        result = WalkForwardResult()
        fit: DixonColesFit | None = None
        fitted_on: date | None = None
        engine = DixonColes(self.config)

        by_day: dict[date, list[Match]] = {}
        for m in played:
            by_day.setdefault(m.day, []).append(m)

        history: list[Match] = []
        for day in sorted(by_day):
            todays = by_day[day]
            needs_refit = (
                day >= start_day
                and len(history) >= self.min_train_matches
                and (fit is None or fitted_on is None
                     or (day - fitted_on).days >= self.refit_every_days)
            )
            if needs_refit:
                fit = engine.fit(history, reference_day=day)
                fitted_on = day
                result.n_fits += 1
                if verbose:
                    print(f"  stima al {day}: {len(history)} partite, "
                          f"{len(fit.teams)} squadre")

            if fit is not None and fitted_on is not None:
                for m in todays:
                    matrix = fit.score_matrix(m.home, m.away, m.division)
                    result.predictions.append(Prediction(
                        match=m, probs=outcome_1x2(matrix),
                        fitted_on=fitted_on, train_size=fit.n_matches))

            history.extend(todays)

        return result


def tune_xi(matches: list[Match], candidates: tuple[float, ...] = (0.0015, 0.0025, 0.0035, 0.005, 0.008),
            l2: float = 2.0, **kwargs) -> list[dict[str, float]]:
    """Cerca il decadimento temporale che minimizza l'errore fuori campione.

    Non esiste un valore universalmente giusto: quanto conta il passato dipende
    dal campionato e dalla mobilita' delle rose. Va misurato, non scelto.
    """
    rows = []
    for xi in candidates:
        wf = WalkForward(FitConfig(xi=xi, l2=l2), **kwargs)
        res = wf.run(matches)
        m = res.metrics()
        m["xi"] = xi
        m["emivita_giorni"] = float(np.log(2) / xi)
        rows.append(m)
    rows.sort(key=lambda r: r.get("rps", float("inf")))
    return rows
