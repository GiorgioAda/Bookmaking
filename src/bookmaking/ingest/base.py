"""Interfacce delle fonti dati.

Il resto del sistema non sa da dove arrivino risultati e quote: conosce solo
questi due protocolli. Cambiare fornitore, aggiungere un feed europeo o passare
da una API gratuita a una a pagamento significa scrivere una classe nuova e
lasciare intatto tutto il resto.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from bookmaking.domain import Match, MatchOdds


@runtime_checkable
class ResultsProvider(Protocol):
    """Fonte di risultati storici, per stimare il modello."""

    name: str

    def fetch_results(self, division: str, season: str) -> list[Match]:
        ...


@runtime_checkable
class OddsProvider(Protocol):
    """Fonte di quote per le partite non ancora giocate."""

    name: str

    def fetch_odds(self, division: str, markets: tuple[str, ...]) -> dict[str, MatchOdds]:
        ...

    def fetch_fixtures(self, division: str, until: date | None = None) -> list[Match]:
        ...


def normalise_team(name: str) -> str:
    """Normalizza un nome squadra per confrontare fonti diverse.

    Fonti diverse scrivono la stessa squadra in modi diversi ("Inter",
    "Internazionale", "Inter Milan"). Questa e' solo la prima passata: la
    tabella di corrispondenza vera vive in ``data/team_aliases.json`` e va
    riempita mano a mano che si incontrano i disallineamenti, perche' indovinarli
    a priori non funziona.
    """
    cleaned = " ".join(name.strip().split())
    for suffix in (" FC", " CF", " AC", " SC", " AS", " US", " SSD", " Calcio"):
        if cleaned.upper().endswith(suffix.upper()):
            cleaned = cleaned[: -len(suffix)]
    return cleaned.strip()
