"""Test del livello prezzi: margine, consenso fra book, fusione col modello."""
from __future__ import annotations

import pytest

from bookmaking.domain import MatchOdds, OddsQuote
from bookmaking.pricing.blend import Edge, blend_probabilities, find_edges
from bookmaking.pricing.consensus import (BookWeights, best_italian_price,
                                          consensus_probabilities, fair_odds)
from bookmaking.pricing.devig import DevigMethod, devig, margin

MERCATO = {"1": 2.10, "X": 3.40, "2": 3.60}
SBILANCIATO = {"1": 1.25, "X": 6.00, "2": 12.00}


@pytest.mark.parametrize("metodo", list(DevigMethod))
def test_ogni_metodo_produce_probabilita_valide(metodo):
    p = devig(MERCATO, metodo)
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert all(0.0 < v < 1.0 for v in p.values())


@pytest.mark.parametrize("metodo", list(DevigMethod))
def test_il_devig_conserva_l_ordine_delle_quote(metodo):
    p = devig(MERCATO, metodo)
    assert p["1"] > p["X"] > p["2"]


def test_il_margine_viene_effettivamente_rimosso():
    assert margin(MERCATO) > 0.04
    for metodo in DevigMethod:
        assert abs(sum(devig(MERCATO, metodo).values()) - 1.0) < 1e-9


def test_i_metodi_divergono_sugli_outsider():
    """E' il motivo per cui il metodo di devig non e' un dettaglio implementativo.

    Sul favorito i metodi concordano; sull'outsider la quota equa stimata
    cambia di oltre il 10%, e con essa il presunto valore della giocata.
    """
    molt = 1.0 / devig(SBILANCIATO, DevigMethod.MULTIPLICATIVE)["2"]
    shin = 1.0 / devig(SBILANCIATO, DevigMethod.SHIN)["2"]
    assert shin > molt * 1.05


def test_quote_non_valide_vengono_respinte():
    with pytest.raises(ValueError):
        devig({"1": 0.9, "2": 2.0})
    with pytest.raises(ValueError):
        devig({"1": 2.0})


def test_i_book_dello_stesso_gruppo_non_contano_tre_volte():
    """Goldbet, Better e Lottomatica sono lo stesso palinsesto: un parere, non tre."""
    w = BookWeights(margin_sensitivity=0.0)
    soli = [OddsQuote("goldbet", "1X2", MERCATO)]
    gruppo = [OddsQuote(b, "1X2", MERCATO) for b in ("goldbet", "better", "lottomatica")]
    peso_solo = sum(w.weights_for(soli).values())
    peso_gruppo = sum(w.weights_for(gruppo).values())
    assert abs(peso_solo - peso_gruppo) < 1e-9


def test_i_book_affilati_pesano_di_piu():
    w = BookWeights(margin_sensitivity=0.0)
    assert w.raw("pinnacle") > w.raw("goldbet")
    assert w.raw("betfair_ex") > w.raw("sisal")


def test_il_consenso_si_sposta_verso_il_book_affilato():
    """Se l'exchange dissente dai book retail, il consenso deve dargli ascolto."""
    retail = {"1": 2.00, "X": 3.40, "2": 3.80}
    sharp = {"1": 2.50, "X": 3.30, "2": 2.90}
    quotes = [OddsQuote(b, "1X2", retail) for b in ("goldbet", "sisal", "snai")]
    solo_retail = consensus_probabilities(quotes)
    con_sharp = consensus_probabilities(quotes + [OddsQuote("pinnacle", "1X2", sharp)])
    assert con_sharp["1"] < solo_retail["1"]
    assert con_sharp["2"] > solo_retail["2"]


def test_la_quota_equa_e_l_inverso_della_probabilita():
    p = {"1": 0.5, "X": 0.25, "2": 0.25}
    assert fair_odds(p) == {"1": 2.0, "X": 4.0, "2": 4.0}


def test_il_consenso_ignora_i_mercati_incompleti():
    quotes = [OddsQuote("goldbet", "1X2", MERCATO),
              OddsQuote("sisal", "1X2", {"1": 2.05})]
    p = consensus_probabilities(quotes)
    assert abs(sum(p.values()) - 1.0) < 1e-9


def test_si_gioca_sulla_quota_italiana_piu_alta():
    odds = MatchOdds("m1", [
        OddsQuote("goldbet", "1X2", {"1": 2.10, "X": 3.40, "2": 3.60}),
        OddsQuote("sisal", "1X2", {"1": 2.25, "X": 3.30, "2": 3.50}),
        OddsQuote("pinnacle", "1X2", {"1": 2.35, "X": 3.45, "2": 3.55}),
    ])
    book, price = best_italian_price(odds, "1X2", "1")
    assert (book, price) == ("sisal", 2.25)   # Pinnacle non e' giocabile in Italia


def test_la_fusione_rispetta_il_peso_assegnato():
    modello = {"1": 0.60, "X": 0.25, "2": 0.15}
    mercato = {"1": 0.40, "X": 0.30, "2": 0.30}
    assert blend_probabilities(modello, mercato, 1.0)["1"] == pytest.approx(0.60, abs=1e-9)
    assert blend_probabilities(modello, mercato, 0.0)["1"] == pytest.approx(0.40, abs=1e-9)
    meta = blend_probabilities(modello, mercato, 0.5)["1"]
    assert 0.40 < meta < 0.60


def test_la_fusione_resta_una_distribuzione():
    modello = {"1": 0.60, "X": 0.25, "2": 0.15}
    mercato = {"1": 0.40, "X": 0.30, "2": 0.30}
    for w in (0.0, 0.25, 0.65, 1.0):
        p = blend_probabilities(modello, mercato, w)
        assert abs(sum(p.values()) - 1.0) < 1e-9


def test_peso_fuori_intervallo_rifiutato():
    with pytest.raises(ValueError):
        blend_probabilities({"1": 0.5, "2": 0.5}, {"1": 0.5, "2": 0.5}, 1.4)


def test_il_valore_atteso_ha_il_segno_giusto():
    buono = Edge("1X2", "1", "goldbet", 2.50, 0.45, 0.42, 0.45)
    cattivo = Edge("1X2", "1", "goldbet", 1.80, 0.45, 0.50, 0.48)
    assert buono.ev > 0 and buono.kelly() > 0
    # Kelly negativo e' l'informazione corretta: a quella quota conviene il lato
    # opposto. E' plan_stakes a tradurlo in "non si gioca".
    assert cattivo.ev < 0 and cattivo.kelly() < 0


def test_quota_equa_e_rapporto_di_prezzo():
    e = Edge("1X2", "1", "goldbet", 2.50, 0.45, 0.42, 0.40)
    assert e.fair_price == pytest.approx(2.50, abs=1e-9)
    assert e.ev == pytest.approx(0.0, abs=1e-9)
    assert e.price_ratio == pytest.approx(1.0, abs=1e-9)


def test_find_edges_ordina_per_valore():
    modello = {"1": 0.50, "X": 0.25, "2": 0.25}
    mercato = {"1": 0.45, "X": 0.28, "2": 0.27}
    prezzi = {"1": ("goldbet", 2.30), "X": ("sisal", 3.40), "2": ("snai", 3.50)}
    edges = find_edges(modello, mercato, prezzi, "1X2", model_weight=0.65)
    assert [e.ev for e in edges] == sorted([e.ev for e in edges], reverse=True)
    assert len(edges) == 3
