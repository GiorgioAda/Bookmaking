"""Test della schedina a quota obiettivo e del bonus multipla."""
from __future__ import annotations

import itertools
import math
import random

import pytest

from bookmaking.staking.schedina import BonusSchedule, TicketPlan, optimise, _best_subset
from bookmaking.staking.ticket import Leg


def gamba(match: str, price: float, edge: float = 0.0, sel: str = "1") -> Leg:
    """Gamba con probabilita' coerente con la quota, piu' un eventuale vantaggio."""
    return Leg(match_id=match, label=match, market="1X2", selection=sel,
               bookmaker="goldbet", price=price, p_final=(1.0 + edge) / price)


def campionario(n: int = 14, seed: int = 3) -> list[Leg]:
    rng = random.Random(seed)
    return [gamba(f"m{i}", round(rng.uniform(1.18, 3.2), 2), edge=-0.05)
            for i in range(n)]


def test_senza_bonus_il_moltiplicatore_resta_uno():
    b = BonusSchedule()
    assert b.multiplier(10) == 1.0


def test_il_bonus_richiede_il_numero_minimo_di_gambe():
    b = BonusSchedule(by_legs={5: 1.10, 8: 1.30}, min_legs=5)
    assert b.multiplier(4) == 1.0
    assert b.multiplier(5) == 1.10
    assert b.multiplier(7) == 1.10      # vale lo scaglione raggiunto
    assert b.multiplier(9) == 1.30


def test_solo_le_gambe_sopra_la_quota_minima_contano_per_il_bonus():
    b = BonusSchedule(by_legs={3: 1.10}, min_leg_price=1.20, min_legs=3)
    legs = [gamba("a", 1.15), gamba("b", 1.25), gamba("c", 1.30), gamba("d", 1.40)]
    assert b.qualifying(legs) == 3


def test_la_soglia_del_bonus_dipende_solo_da_gambe_e_margine():
    """E' il risultato centrale: EV = bonus x (1-margine)^n - 1.

    Le quote scelte non entrano nel conto. Con margine del 5% servono +29% a
    cinque gambe e +67% a dieci, comunque si componga la schedina.
    """
    b = BonusSchedule()
    assert b.break_even(5, 0.05) == pytest.approx(1 / 0.95 ** 5, rel=1e-12)
    assert b.break_even(10, 0.05) == pytest.approx(1.6701, abs=1e-4)
    assert b.break_even(10, 0.05) > b.break_even(5, 0.05)


def test_il_verdetto_riconosce_un_bonus_insufficiente():
    b = BonusSchedule(by_legs={10: 1.40}, min_legs=10)
    r = [x for x in b.verdict(max_legs=10) if x["gambe"] == 10][0]
    assert not r["conviene"]        # +40% non copre il +67% necessario
    generoso = BonusSchedule(by_legs={10: 2.0}, min_legs=10)
    r2 = [x for x in generoso.verdict(max_legs=10) if x["gambe"] == 10][0]
    assert r2["conviene"]


def test_la_schedina_raggiunge_sempre_l_obiettivo():
    piani = optimise(campionario(), target=5.0, max_legs=8)
    assert piani
    for p in piani:
        assert p.meets_target
        assert p.effective_price >= 5.0 - 1e-9


def test_mai_due_gambe_sulla_stessa_partita():
    """Sono correlate, i book non le accettano e il prodotto sarebbe sbagliato."""
    legs = campionario()
    legs += [gamba(l.match_id, l.price + 0.5, sel="X") for l in legs[:5]]
    for p in optimise(legs, target=5.0, max_legs=6):
        assert len({l.match_id for l in p.legs}) == len(p.legs)


def test_aggiungere_gambe_riduce_la_probabilita_a_parita_di_obiettivo():
    """Il punto che decide tutto: la quota e' la stessa, la probabilita' no."""
    piani = {len(p.legs): p for p in optimise(campionario(20), target=5.0, max_legs=6)}
    assert piani[2].probability > piani[5].probability


def test_il_numero_di_gambe_e_rispettato():
    for p in optimise(campionario(), target=5.0, max_legs=4):
        assert 2 <= len(p.legs) <= 4


def test_un_obiettivo_irraggiungibile_non_produce_schedine():
    assert optimise([gamba("a", 1.2), gamba("b", 1.2)], target=50.0, max_legs=2) == []


def test_il_bonus_abbassa_la_quota_richiesta_alle_gambe():
    """Col bonus le stesse cinque gambe possono essere piu' corte, quindi piu' probabili.

    Serve pero' che quote abbastanza basse esistano: con un campionario di soli
    favoriti larghi il vincolo non e' il bonus ma la disponibilita', ed e'
    esattamente cio' che rende irrealistiche le schedine lunghe a quota bassa.
    """
    corte = [gamba(f"m{i}", 1.15 + 0.02 * i, edge=-0.05) for i in range(16)]
    senza = {len(p.legs): p for p in optimise(corte, target=5.0, max_legs=8)}
    con = {len(p.legs): p for p in optimise(
        corte, target=5.0, max_legs=8,
        bonus=BonusSchedule(by_legs={5: 1.25}, min_legs=5))}
    assert con[5].raw_price < senza[5].raw_price
    assert con[5].probability > senza[5].probability
    assert con[5].meets_target


def test_le_gambe_corte_scarseggiano_e_il_vincolo_diventa_quello():
    """Una schedina lunga a quota bassa spesso non esiste proprio.

    Con quote realistiche, le cinque selezioni piu' corte disponibili possono gia'
    superare l'obiettivo: la schedina sfora, e la probabilita' crolla di
    conseguenza. Non e' un limite dell'ottimizzatore, e' il mercato.
    """
    legs = campionario(20)
    piani = {len(p.legs): p for p in optimise(legs, target=5.0, max_legs=8)}
    assert piani[3].effective_price == pytest.approx(5.0, abs=0.2)
    assert piani[8].effective_price > 10.0
    assert piani[8].probability < piani[3].probability / 5


def test_i_conti_del_piano_tornano():
    legs = [gamba("a", 2.0, edge=0.0), gamba("b", 2.5, edge=0.0)]
    p = TicketPlan(legs=legs, bonus=1.2, target=5.0)
    assert p.raw_price == pytest.approx(5.0)
    assert p.effective_price == pytest.approx(6.0)
    assert p.probability == pytest.approx(1 / 5.0)
    assert p.ev == pytest.approx(6.0 / 5.0 - 1.0)
    assert p.one_in == pytest.approx(5.0)


def test_l_ottimizzatore_coincide_con_la_ricerca_esaustiva():
    """Controllo di correttezza su istanze abbastanza piccole da enumerarle tutte."""
    rng = random.Random(11)
    for _ in range(15):
        n_partite = rng.randint(4, 7)
        gruppi = [[gamba(f"m{g}", round(rng.uniform(1.2, 3.0), 2), edge=-0.05)]
                  for g in range(n_partite)]
        n = rng.randint(2, min(4, n_partite))
        target = math.log(rng.uniform(2.0, 6.0))
        trovato = _best_subset(gruppi, n, target)

        migliore = None
        for combo in itertools.combinations(range(n_partite), n):
            legs = [gruppi[c][0] for c in combo]
            if sum(math.log(l.price) for l in legs) < target - 1e-12:
                continue
            v = sum(math.log(l.p_final) for l in legs)
            if migliore is None or v > migliore:
                migliore = v
        if migliore is None:
            assert trovato is None
            continue
        assert trovato is not None
        assert sum(math.log(l.p_final) for l in trovato) >= migliore - 1e-9
