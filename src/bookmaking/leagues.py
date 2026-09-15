"""Campionati coperti dal sistema.

Il modello viene stimato *per nazione*, non per divisione: prima e seconda
divisione dello stesso paese condividono una sola stima. Le due divisioni non
si incontrano mai in campionato, quindi prese separatamente le loro scale di
forza non sarebbero confrontabili; sono le promozioni e le retrocessioni a fare
da ponte, perche' una squadra retrocessa porta con se' il proprio rating nella
serie inferiore. Stimando insieme piu' stagioni della stessa nazione, la forza
relativa delle due divisioni diventa identificabile.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Division:
    code: str           # codice interno, es. "IT1"
    country: str        # "IT"
    tier: int           # 1 = massima serie, 2 = seconda
    name: str
    footballdata_code: str | None   # codice CSV football-data.co.uk
    odds_api_key: str | None        # chiave sport su The Odds API


DIVISIONS: tuple[Division, ...] = (
    Division("IT1", "IT", 1, "Serie A", "I1", "soccer_italy_serie_a"),
    Division("IT2", "IT", 2, "Serie B", "I2", "soccer_italy_serie_b"),
    Division("EN1", "EN", 1, "Premier League", "E0", "soccer_epl"),
    Division("EN2", "EN", 2, "Championship", "E1", "soccer_efl_champ"),
    Division("DE1", "DE", 1, "Bundesliga", "D1", "soccer_germany_bundesliga"),
    Division("DE2", "DE", 2, "2. Bundesliga", "D2", "soccer_germany_bundesliga2"),
    Division("ES1", "ES", 1, "LaLiga", "SP1", "soccer_spain_la_liga"),
    Division("ES2", "ES", 2, "LaLiga 2", "SP2", "soccer_spain_segunda_division"),
    Division("FR1", "FR", 1, "Ligue 1", "F1", "soccer_france_ligue_one"),
    Division("FR2", "FR", 2, "Ligue 2", "F2", "soccer_france_ligue_two"),
    Division("PT1", "PT", 1, "Primeira Liga", "P1", "soccer_portugal_primeira_liga"),
    # Liga Portugal 2 non ha una fonte storica gratuita affidabile: va aggiunta
    # solo quando avremo un feed che la copra davvero (vedi docs/DATA.md).
)

BY_CODE = {d.code: d for d in DIVISIONS}
COUNTRIES = tuple(dict.fromkeys(d.country for d in DIVISIONS))


def divisions_of(country: str) -> tuple[Division, ...]:
    return tuple(d for d in DIVISIONS if d.country == country)
