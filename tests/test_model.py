"""Test del modello statistico: gradienti, recupero dei parametri, coerenza."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from scipy.optimize import approx_fprime

from bookmaking.domain import Match, Outcome
from bookmaking.model.dixon_coles import DixonColes, FitConfig
from bookmaking.model.markets import (all_markets, asian_handicap, btts,
                                      double_chance, outcome_1x2, over_under,
                                      selection_mask)
from bookmaking.simulate import simulate_country


@pytest.fixture(scope="module")
def world():
    return simulate_country(n_seasons=4, teams_per_division=14,
                            strength_sd=0.30, seed=11)


@pytest.fixture(scope="module")
def fit(world):
    return DixonColes(FitConfig(xi=0.0025, l2=2.0)).fit(world.matches)


def test_gradiente_analitico_corrisponde_al_numerico():
    """Un gradiente sbagliato non fa fallire la stima: la fa convergere altrove."""
    import bookmaking.model.dixon_coles as dc

    rng = np.random.default_rng(3)
    teams = [f"T{i}" for i in range(8)]
    base = datetime(2024, 8, 1)
    ms = [Match("IT1", "2024", base + timedelta(days=i // 2),
                teams[int(rng.integers(8))], teams[int(rng.integers(8))],
                int(rng.poisson(1.4)), int(rng.poisson(1.1)))
          for i in range(200)]
    ms = [m for m in ms if m.home != m.away]

    captured = {}
    original = dc.minimize

    def spy(fun, x0, **kw):
        captured["fun"] = fun
        captured["x0"] = x0
        return original(fun, x0, **kw)

    dc.minimize = spy
    try:
        DixonColes(FitConfig(max_iter=1)).fit(ms)
    finally:
        dc.minimize = original

    f = lambda t: captured["fun"](t)[0]
    theta = captured["x0"] + rng.normal(0, 0.2, size=captured["x0"].shape)
    theta[-1] = float(np.clip(theta[-1], -0.2, 0.2))
    numeric = approx_fprime(theta, f, 1e-6)
    analytic = captured["fun"](theta)[1]
    assert np.max(np.abs(numeric - analytic)) < 1e-3 * max(1.0, np.max(np.abs(numeric)))


def test_la_stima_recupera_la_forza_delle_squadre(world, fit):
    """Su dati generati da parametri noti, i rating stimati devono ordinarli bene.

    Attenzione alle convenzioni: nel simulatore la difesa e' *qualita'*
    (sottratta ai gol attesi dell'avversario), nel modello e' *propensione a
    subire* (sommata). Le due forze complessive sono quindi att+dif_sim e
    att-dif_modello.
    """
    vera = np.array([world.true_attack[t] + world.true_defence[t] for t in fit.teams])
    stimata = np.array([fit.strength(t) for t in fit.teams])
    corr = float(np.corrcoef(vera, stimata)[0, 1])
    assert corr > 0.7, f"correlazione con la forza vera troppo bassa: {corr:.3f}"


def test_rho_e_vantaggio_campo_plausibili(fit, world):
    assert -0.25 < fit.rho < 0.05
    assert 0.1 < float(fit.home_adv.mean()) < 0.5
    assert fit.converged


def test_squadra_sconosciuta_usa_il_prior(fit):
    assert not fit.knows("Neopromossa Ignota")
    att, dfn = fit.rating("Neopromossa Ignota")
    assert att == fit.config.unknown_attack
    assert dfn == fit.config.unknown_defence
    lam, mu = fit.expected_goals("Neopromossa Ignota", fit.teams[0], "IT1")
    assert 0.1 < lam < 4.0 and 0.1 < mu < 4.0


def test_matrice_dei_punteggi_e_una_distribuzione(fit):
    m = fit.score_matrix(fit.teams[0], fit.teams[1], "IT1")
    assert m.shape[0] == m.shape[1]
    assert np.all(m >= 0)
    assert abs(m.sum() - 1.0) < 1e-9


def test_il_fattore_campo_favorisce_chi_gioca_in_casa(fit):
    a, b = fit.teams[0], fit.teams[1]
    casa = outcome_1x2(fit.score_matrix(a, b, "IT1"))
    fuori = outcome_1x2(fit.score_matrix(b, a, "IT1"))
    # la stessa sfida a campi invertiti: la squadra in casa deve stare meglio
    assert casa["1"] > fuori["2"]


def test_mercati_sommano_a_uno(fit):
    """Ogni mercato che sia una partizione degli esiti deve sommare a 1.

    La Doppia Chance e' l'eccezione dichiarata: le sue tre voci si sovrappongono
    a coppie e sommano a 2, perche' ogni esito compare in due di esse.
    """
    m = fit.score_matrix(fit.teams[0], fit.teams[3], "IT1")
    for name, probs in all_markets(m).items():
        atteso = 2.0 if name == "DoppiaChance" else 1.0
        assert abs(sum(probs.values()) - atteso) < 1e-6, f"{name} non somma a {atteso}"
        assert all(0.0 <= v <= 1.0 for v in probs.values())


def test_mercati_coerenti_fra_loro(fit):
    """Le probabilita' derivate dalla stessa matrice non possono contraddirsi."""
    m = fit.score_matrix(fit.teams[0], fit.teams[5], "IT1")
    p = outcome_1x2(m)
    dc = double_chance(m)
    assert abs(dc["1X"] - (p["1"] + p["X"])) < 1e-12
    ou = over_under(m, 2.5)
    assert abs(ou["Over 2.5"] + ou["Under 2.5"] - 1.0) < 1e-9
    # Goal implica almeno 2 gol totali, quindi non puo' superare Over 1.5
    assert btts(m)["Goal"] <= over_under(m, 1.5)["Over 1.5"] + 1e-12


def test_handicap_asiatico_a_zero_equivale_al_pareggio_rimborsato(fit):
    m = fit.score_matrix(fit.teams[2], fit.teams[7], "IT1")
    p = outcome_1x2(m)
    ah = asian_handicap(m, 0.0)
    assert abs(ah["Casa"] - p["1"]) < 1e-12
    assert abs(ah["Rimborso"] - p["X"]) < 1e-12


def test_maschere_coincidono_con_le_formule(fit):
    m = fit.score_matrix(fit.teams[1], fit.teams[4], "IT1")
    assert abs(float(m[selection_mask(m, "1X2", "1")].sum()) - outcome_1x2(m)["1"]) < 1e-12
    assert abs(float(m[selection_mask(m, "GoalNoGoal", "Goal")].sum()) - btts(m)["Goal"]) < 1e-12
    ou = over_under(m, 2.5)["Over 2.5"]
    assert abs(float(m[selection_mask(m, "OverUnder 2.5", "Over 2.5")].sum()) - ou) < 1e-12


def test_serve_almeno_una_partita_giocata():
    with pytest.raises(ValueError):
        DixonColes().fit([Match("IT1", "2024", datetime(2024, 1, 1), "A", "B")])
