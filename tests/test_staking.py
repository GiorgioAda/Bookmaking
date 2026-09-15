"""Test della gestione del capitale: puntate, budget settimanale, schedine."""
from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import poisson

from bookmaking.model.markets import outcome_1x2, over_under
from bookmaking.pricing.blend import Edge
from bookmaking.staking.kelly import (BankrollPolicy, plan_stakes, shrunk_kelly)
from bookmaking.staking.ticket import Leg, build_ticket, combo_probability


def matrice(lam=1.7, mu=1.0, rho=-0.11, mg=15):
    gx = np.arange(mg + 1)
    m = np.outer(poisson.pmf(gx, lam), poisson.pmf(gx, mu))
    m[0, 0] *= 1 - lam * mu * rho
    m[0, 1] *= 1 + lam * rho
    m[1, 0] *= 1 + mu * rho
    m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    return m / m.sum()


def edge(price=2.50, p=0.45, n_books=6):
    return Edge("1X2", "1", "goldbet", price, p, 1.0 / price, p, n_books=n_books)


def test_kelly_classico_su_un_caso_noto():
    """Quota 2.00 con probabilita' 0.55: Kelly pieno vale 0.10 del capitale."""
    e = Edge("1X2", "1", "goldbet", 2.00, 0.55, 0.50, 0.55)
    assert e.kelly() == pytest.approx(0.10, abs=1e-9)


def test_la_compressione_riduce_sempre_la_puntata():
    e = edge()
    politica = BankrollPolicy(edge_shrinkage=0.5, kelly_fraction=0.25)
    grezzo, usato = shrunk_kelly(e, politica)
    assert usato < grezzo * 0.25 + 1e-12
    assert usato > 0


def test_senza_compressione_resta_kelly_frazionario():
    e = edge()
    grezzo, usato = shrunk_kelly(e, BankrollPolicy(edge_shrinkage=0.0, kelly_fraction=0.25))
    assert usato == pytest.approx(grezzo * 0.25, rel=1e-9)


def test_il_budget_settimanale_non_viene_mai_superato():
    politica = BankrollPolicy(weekly_budget=30.0)
    edges = [Edge("1X2", str(i), "goldbet", 2.6, 0.48, 1 / 2.6, 0.48, n_books=6)
             for i in range(20)]
    piano = plan_stakes(edges, politica)
    assert piano.total_stake <= politica.weekly_budget + 1e-9
    assert len(piano.bets) <= politica.max_bets_per_week


def test_nessuna_giocata_supera_il_tetto_per_scommessa():
    politica = BankrollPolicy(weekly_budget=30.0, max_stake_pct=0.20)
    piano = plan_stakes([edge(price=3.0, p=0.60)], politica)
    for b in piano.bets:
        assert b.stake <= politica.max_stake + 1e-9


def test_le_puntate_sotto_il_minimo_non_vengono_forzate():
    """Meglio non giocare che puntare piu' del dovuto per raggiungere il minimo."""
    politica = BankrollPolicy(weekly_budget=30.0, min_stake=2.0, min_ev=0.0)
    piano = plan_stakes([edge(price=2.50, p=0.405)], politica)   # vantaggio minimo
    assert piano.bets == []
    assert any("sotto il minimo" in motivo for _, motivo in piano.rejected)


def test_le_scommesse_senza_valore_vengono_scartate():
    politica = BankrollPolicy(min_ev=0.03)
    piano = plan_stakes([edge(price=2.00, p=0.48)], politica)
    assert piano.bets == []
    assert "valore atteso" in piano.rejected[0][1]


def test_il_consenso_debole_viene_scartato():
    politica = BankrollPolicy(min_books=3)
    piano = plan_stakes([edge(price=2.60, p=0.50, n_books=1)], politica)
    assert piano.bets == []
    assert "consenso troppo debole" in piano.rejected[0][1]


def test_le_quote_estreme_vengono_scartate():
    politica = BankrollPolicy()
    piano = plan_stakes([edge(price=25.0, p=0.10), edge(price=1.05, p=0.99)], politica)
    assert piano.bets == []
    assert len(piano.rejected) == 2


def test_le_puntate_sono_arrotondate_al_passo():
    politica = BankrollPolicy(stake_step=0.50, min_ev=0.0)
    piano = plan_stakes([edge(price=3.0, p=0.55)], politica)
    for b in piano.bets:
        assert abs(b.stake / 0.50 - round(b.stake / 0.50)) < 1e-9


def test_gambe_sulla_stessa_partita_non_sono_indipendenti():
    """Vittoria interna e Over 2.5 vanno d'accordo: il prodotto sottostima."""
    m = matrice()
    p1 = outcome_1x2(m)["1"]
    pov = over_under(m, 2.5)["Over 2.5"]
    a = Leg("m1", "A - B", "1X2", "1", "goldbet", 1.90, p1, m)
    b = Leg("m1", "A - B", "OverUnder 2.5", "Over 2.5", "goldbet", 1.85, pov, m)
    congiunta = combo_probability([a, b])
    assert congiunta > p1 * pov * 1.10


def test_gambe_su_partite_diverse_si_moltiplicano():
    m = matrice()
    p1 = outcome_1x2(m)["1"]
    a = Leg("m1", "A - B", "1X2", "1", "goldbet", 1.90, p1, m)
    b = Leg("m2", "C - D", "1X2", "1", "goldbet", 1.90, p1, m)
    assert combo_probability([a, b]) == pytest.approx(p1 * p1, rel=1e-9)


def test_la_multipla_avvisa_quando_le_singole_rendono_di_piu():
    m = matrice()
    p1 = outcome_1x2(m)["1"]
    gambe = [Leg(f"m{i}", f"P{i}", "1X2", "1", "goldbet", 1.60, p1, m) for i in range(3)]
    t = build_ticket(gambe, 5.0)
    assert t.is_multiple
    assert any("singole" in w for w in t.warnings)


def test_la_multipla_segnala_il_valore_atteso_negativo():
    m = matrice()
    p1 = outcome_1x2(m)["1"]
    gambe = [Leg(f"m{i}", f"P{i}", "1X2", "1", "goldbet", 1.50, p1, m) for i in range(4)]
    t = build_ticket(gambe, 5.0)
    assert t.ev < 0
    assert any("valore atteso negativo" in w for w in t.warnings)


def test_i_conti_della_schedina_tornano():
    m = matrice()
    p1 = outcome_1x2(m)["1"]
    gambe = [Leg("m1", "A - B", "1X2", "1", "goldbet", 2.00, p1, m),
             Leg("m2", "C - D", "1X2", "1", "sisal", 1.80, p1, m)]
    t = build_ticket(gambe, 4.0)
    assert t.price == pytest.approx(3.60, rel=1e-9)
    assert t.potential_return == pytest.approx(14.40, rel=1e-9)
    assert t.ev == pytest.approx(t.probability * 3.60 - 1.0, rel=1e-9)
    assert t.expected_profit == pytest.approx(4.0 * t.ev, rel=1e-9)
