"""Test delle metriche e del backtest walk-forward."""
from __future__ import annotations

import pytest

from bookmaking.backtest.metrics import (accuracy, brier_score, calibration_table,
                                         log_loss, roi, rps, summarise)
from bookmaking.backtest.walkforward import WalkForward
from bookmaking.model.dixon_coles import FitConfig
from bookmaking.simulate import simulate_country

PERFETTO = [{"1": 1.0, "X": 0.0, "2": 0.0}]
PESSIMO = [{"1": 0.0, "X": 0.0, "2": 1.0}]


def test_previsione_perfetta_azzera_gli_errori():
    assert log_loss(PERFETTO, ["1"]) == pytest.approx(0.0, abs=1e-9)
    assert brier_score(PERFETTO, ["1"]) == pytest.approx(0.0, abs=1e-9)
    assert rps(PERFETTO, ["1"]) == pytest.approx(0.0, abs=1e-9)


def test_rps_distingue_gli_errori_vicini_da_quelli_lontani():
    """Sbagliare di un gradino (X) deve costare meno che sbagliare del tutto (2).

    E' la ragione per cui l'RPS e' la metrica giusta sull'1X2: log loss e Brier
    trattano i due errori allo stesso modo, ma non lo sono.
    """
    vicino = rps([{"1": 0.7, "X": 0.2, "2": 0.1}], ["X"])
    lontano = rps([{"1": 0.7, "X": 0.2, "2": 0.1}], ["2"])
    assert vicino < lontano
    b_vicino = brier_score([{"1": 0.7, "X": 0.2, "2": 0.1}], ["X"])
    b_lontano = brier_score([{"1": 0.7, "X": 0.1, "2": 0.2}], ["2"])
    assert b_vicino == pytest.approx(b_lontano, abs=1e-9)   # Brier non li distingue


def test_l_incertezza_batte_la_sicurezza_sbagliata():
    incerto = [{"1": 1 / 3, "X": 1 / 3, "2": 1 / 3}]
    assert log_loss(incerto, ["1"]) < log_loss(PESSIMO, ["1"])


def test_accuratezza_prende_l_esito_piu_probabile():
    probs = [{"1": 0.5, "X": 0.3, "2": 0.2}, {"1": 0.2, "X": 0.3, "2": 0.5}]
    assert accuracy(probs, ["1", "2"]) == 1.0
    assert accuracy(probs, ["X", "X"]) == 0.0


def test_la_calibrazione_rileva_la_sovrastima():
    """Un modello che dice 80% e indovina il 40% deve risultare scalibrato."""
    tabella = calibration_table([0.8] * 10, [True] * 4 + [False] * 6, bins=5)
    riga = [r for r in tabella if r["n"] == 10][0]
    assert riga["scarto"] == pytest.approx(0.4 - 0.8, abs=1e-9)


def test_roi_su_una_serie_di_giocate():
    r = roi([10.0, 10.0], [25.0, 0.0])
    assert r["profitto"] == pytest.approx(5.0)
    assert r["roi"] == pytest.approx(0.25)
    assert r["n_giocate"] == 2


def test_il_backtest_non_guarda_il_futuro():
    """Ogni previsione deve nascere da una stima anteriore alla partita."""
    world = simulate_country(n_seasons=3, teams_per_division=12,
                             strength_sd=0.30, seed=9)
    res = WalkForward(FitConfig(xi=0.0025), refit_every_days=14,
                      burn_in_days=300).run(world.matches)
    assert res.predictions
    for p in res.predictions:
        assert p.fitted_on <= p.match.day


def test_il_backtest_batte_il_riferimento_a_frequenze_fisse():
    world = simulate_country(n_seasons=4, teams_per_division=14,
                             strength_sd=0.30, seed=17)
    res = WalkForward(FitConfig(xi=0.0025), refit_every_days=14,
                      burn_in_days=330).run(world.matches)
    modello = res.metrics()
    fisso = summarise([{"1": 0.45, "X": 0.26, "2": 0.29}] * len(res.outcomes),
                      res.outcomes)
    assert modello["rps"] < fisso["rps"]
    assert modello["log_loss"] < fisso["log_loss"]


def test_le_metriche_si_possono_leggere_per_divisione():
    world = simulate_country(n_seasons=3, teams_per_division=12,
                             strength_sd=0.30, seed=5)
    res = WalkForward(FitConfig(xi=0.0025), refit_every_days=21,
                      burn_in_days=300).run(world.matches)
    per_div = res.metrics_by_division()
    assert set(per_div) <= {"IT1", "IT2"}
    assert all(d["n"] > 0 for d in per_div.values())
