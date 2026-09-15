"""Quote in tempo reale da The Odds API.

Perche' una API aggregatrice e non i siti dei bookmaker: raschiare i palinsesti
di Goldbet, Sisal o Snai viola i loro termini di servizio, si rompe a ogni
cambio di pagina e finisce bloccato dalle protezioni anti-bot. Un aggregatore
espone le stesse quote con un contratto stabile e legittimo.

Cosa aspettarsi sulla copertura italiana: la regione ``eu`` include i grandi
book europei, ma i concessionari ADM italiani minori possono non esserci.
Questo non affonda il progetto, perche' i due usi delle quote sono diversi: la
*quota vera* si stima meglio con i book affilati (exchange, Pinnacle), mentre
la *quota su cui si gioca* serve solo per i book dove hai il conto. Per quelli
si puo' sempre inserire il prezzo a mano.

NOTA: le chiavi dei campi seguono la documentazione v4 della API. Non sono state
verificate contro il servizio dal vivo dall'ambiente in cui il modulo e' stato
scritto; ``fetch_raw`` stampa la struttura ricevuta quando ``debug=True``.
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from bookmaking.domain import Match, MatchOdds, OddsQuote
from bookmaking.ingest.base import normalise_team
from bookmaking.leagues import BY_CODE

BASE_URL = "https://api.the-odds-api.com/v4"

# Dal vocabolario della API al nostro
MARKET_MAP = {"h2h": "1X2", "totals": "OverUnder", "spreads": "HandicapAsiatico"}
OUTCOME_1X2 = {"home": "1", "draw": "X", "away": "2"}


@dataclass
class TheOddsApi:
    """Client minimale: solo le due chiamate che servono davvero."""

    api_key: str = field(default_factory=lambda: os.environ.get("ODDS_API_KEY", ""))
    name: str = "the-odds-api"
    regions: str = "eu"
    timeout: float = 20.0
    last_quota: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.api_key:
            raise ValueError(
                "chiave API mancante: imposta la variabile d'ambiente ODDS_API_KEY")

    def fetch_raw(self, division: str, markets: tuple[str, ...] = ("h2h",),
                  debug: bool = False) -> list[dict]:
        div = BY_CODE.get(division)
        if div is None or div.odds_api_key is None:
            raise ValueError(f"divisione senza sport corrispondente: {division}")
        params = urllib.parse.urlencode({
            "apiKey": self.api_key,
            "regions": self.regions,
            "markets": ",".join(markets),
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        })
        url = f"{BASE_URL}/sports/{div.odds_api_key}/odds?{params}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            # Il credito residuo arriva negli header: va guardato, il piano
            # gratuito si esaurisce in fretta se si interroga a ogni refresh.
            self.last_quota = {
                "richieste_rimaste": resp.headers.get("x-requests-remaining", "?"),
                "richieste_usate": resp.headers.get("x-requests-used", "?"),
            }
            data = json.loads(resp.read().decode("utf-8"))
        if debug and data:
            print(json.dumps(data[0], indent=2)[:1500])
        return data

    def fetch_odds(self, division: str,
                   markets: tuple[str, ...] = ("h2h",)) -> dict[str, MatchOdds]:
        out: dict[str, MatchOdds] = {}
        for event in self.fetch_raw(division, markets):
            match_id = self._match_id(division, event)
            quotes: list[OddsQuote] = []
            for book in event.get("bookmakers", []):
                key = str(book.get("key", "")).lower()
                updated = self._parse_iso(book.get("last_update"))
                for market in book.get("markets", []):
                    parsed = self._parse_market(market, event)
                    if parsed:
                        name, prices = parsed
                        quotes.append(OddsQuote(key, name, prices, collected_at=updated))
            if quotes:
                out[match_id] = MatchOdds(match_id=match_id, quotes=quotes)
        return out

    def fetch_fixtures(self, division: str, until: date | None = None) -> list[Match]:
        fixtures: list[Match] = []
        for event in self.fetch_raw(division, ("h2h",)):
            kickoff = self._parse_iso(event.get("commence_time"))
            if kickoff is None:
                continue
            if until is not None and kickoff.date() > until:
                continue
            fixtures.append(Match(
                division=division, season=self._season_of(kickoff), kickoff=kickoff,
                home=normalise_team(str(event.get("home_team", ""))),
                away=normalise_team(str(event.get("away_team", ""))),
                match_id=self._match_id(division, event),
            ))
        return fixtures

    def _parse_market(self, market: dict, event: dict) -> tuple[str, dict[str, float]] | None:
        key = str(market.get("key", ""))
        outcomes = market.get("outcomes", [])
        if not outcomes:
            return None
        home = str(event.get("home_team", ""))
        away = str(event.get("away_team", ""))

        if key == "h2h":
            prices: dict[str, float] = {}
            for o in outcomes:
                name = str(o.get("name", ""))
                price = o.get("price")
                if price is None:
                    continue
                if name == home:
                    prices["1"] = float(price)
                elif name == away:
                    prices["2"] = float(price)
                elif name.lower() in ("draw", "tie"):
                    prices["X"] = float(price)
            return ("1X2", prices) if len(prices) == 3 else None

        if key == "totals":
            point = outcomes[0].get("point")
            if point is None:
                return None
            prices = {}
            for o in outcomes:
                name = str(o.get("name", "")).lower()
                price = o.get("price")
                if price is None:
                    continue
                if name == "over":
                    prices[f"Over {float(point)}"] = float(price)
                elif name == "under":
                    prices[f"Under {float(point)}"] = float(price)
            return (f"OverUnder {float(point)}", prices) if len(prices) == 2 else None

        if key == "spreads":
            prices = {}
            line = None
            for o in outcomes:
                name = str(o.get("name", ""))
                price, point = o.get("price"), o.get("point")
                if price is None or point is None:
                    continue
                if name == home:
                    line = float(point)
                    prices["Casa"] = float(price)
                elif name == away:
                    prices["Ospiti"] = float(price)
            return (f"HandicapAsiatico {line}", prices) if len(prices) == 2 and line is not None else None

        return None

    @staticmethod
    def _match_id(division: str, event: dict) -> str:
        eid = event.get("id")
        if eid:
            return f"{division}|{eid}"
        return (f"{division}|{event.get('commence_time')}|"
                f"{event.get('home_team')}|{event.get('away_team')}")

    @staticmethod
    def _parse_iso(text: str | None) -> datetime | None:
        if not text:
            return None
        try:
            return datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone(
                timezone.utc).replace(tzinfo=None)
        except ValueError:
            return None

    @staticmethod
    def _season_of(when: datetime) -> str:
        """Le stagioni europee scavallano l'anno solare: luglio fa da spartiacque."""
        year = when.year if when.month >= 7 else when.year - 1
        return f"{year}-{year + 1}"
