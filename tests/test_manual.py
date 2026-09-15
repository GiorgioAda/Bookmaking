"""Test del canale dei prezzi inseriti a mano (il book senza feed)."""
from __future__ import annotations

from datetime import datetime

import pytest

from bookmaking.domain import Match, MatchOdds, OddsQuote
from bookmaking.ingest.manual import (ManualPrices, PriceEntry, books_in_feed,
                                      missing_books)
from bookmaking.pricing.consensus import consensus_probabilities

COMPLETO = {"1": 2.10, "X": 3.40, "2": 3.60}


def feed() -> dict[str, MatchOdds]:
    return {"m1": MatchOdds("m1", [OddsQuote(b, "1X2", COMPLETO)
                                   for b in ("sisal", "snai", "eurobet")])}


def test_quota_non_valida_respinta():
    with pytest.raises(ValueError):
        PriceEntry("m1", "1X2", "1", 0.95)


def test_la_quota_manuale_entra_nel_mercato():
    mp = ManualPrices()
    mp.add("m1", "1X2", "1", 2.35)
    merged = mp.merge_into(feed())
    assert ("goldbet", 2.35) == merged["m1"].best_price("1X2", "1")


def test_la_fusione_non_altera_il_feed_originale():
    originale = feed()
    ManualPrices().merge_into(originale)
    mp = ManualPrices()
    mp.add("m1", "1X2", "1", 9.99)
    mp.merge_into(originale)
    assert "goldbet" not in books_in_feed(originale)


def test_una_nuova_quota_sostituisce_la_precedente():
    mp = ManualPrices()
    mp.add("m1", "1X2", "1", 2.20)
    mp.add("m1", "1X2", "1", 2.40)
    assert len(mp.entries) == 1
    merged = mp.merge_into(feed())
    assert merged["m1"].best_price("1X2", "1")[1] == 2.40


def test_la_quota_manuale_sostituisce_quella_del_feed_dello_stesso_book():
    """L'hai letta adesso sull'app: il feed puo' essere vecchio di ore."""
    base = {"m1": MatchOdds("m1", [OddsQuote("goldbet", "1X2", COMPLETO)])}
    mp = ManualPrices()
    mp.add("m1", "1X2", "1", 2.50)
    merged = mp.merge_into(base)
    goldbet = [q for q in merged["m1"].quotes if q.bookmaker == "goldbet"]
    assert len(goldbet) == 1
    assert goldbet[0].prices == {"1": 2.50}


def test_una_quota_parziale_non_entra_nel_consenso():
    """Con una sola selezione il margine non e' calcolabile: non e' un parere."""
    mp = ManualPrices()
    mp.add("m1", "1X2", "1", 50.0)     # valore assurdo di proposito
    merged = mp.merge_into(feed())
    p = consensus_probabilities(merged["m1"].for_market("1X2"))
    atteso = consensus_probabilities(feed()["m1"].for_market("1X2"))
    assert p == pytest.approx(atteso, abs=1e-12)


def test_un_etichetta_sbagliata_non_rompe_il_consenso():
    """Un errore di battitura in una voce manuale non deve azzerare la partita."""
    mp = ManualPrices()
    mp.add("m1", "1X2", "1 (casa)", 2.30)
    merged = mp.merge_into(feed())
    p = consensus_probabilities(merged["m1"].for_market("1X2"))
    assert abs(sum(p.values()) - 1.0) < 1e-9
    assert set(p) == {"1", "X", "2"}


def test_si_sa_quali_book_mancano_dal_feed():
    assert missing_books(feed(), frozenset({"goldbet", "sisal"})) == {"goldbet"}
    assert books_in_feed(feed()) == {"sisal", "snai", "eurobet"}


def test_la_partita_assente_dal_feed_viene_creata():
    mp = ManualPrices()
    mp.add("nuova", "1X2", "1", 2.10)
    merged = mp.merge_into({})
    assert merged["nuova"].best_price("1X2", "1") == ("goldbet", 2.10)
