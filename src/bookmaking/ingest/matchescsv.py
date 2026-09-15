"""Risultati e quote storiche dal dataset Club Football Match Data.

Un unico CSV con oltre centomila partite delle nostre undici divisioni, dal 2000
a oggi, che porta insieme le due cose che servono: i risultati per stimare il
modello e le quote dell'epoca per misurarlo contro il mercato.

Due colonne meritano attenzione perche' non sono la stessa cosa:

- ``OddHome/OddDraw/OddAway`` sono le quote di riferimento di un singolo
  operatore. Servono a rappresentare "il mercato" quando si valuta se il
  modello e' piu' accurato del banco.
- ``MaxHome/MaxDraw/MaxAway`` sono le quote **piu' alte** disponibili sul
  mercato. Sono quelle su cui si gioca davvero, e la differenza fra le due
  famiglie e' esattamente il vantaggio che si ottiene confrontando i bookmaker
  invece di accettare il primo prezzo.

Misurare il modello contro le quote massime sarebbe un errore lusinghiero: la
quota massima ha gia' un margine quasi nullo, a volte negativo, e batterla e'
molto piu' difficile che batterne una media. Il confronto di accuratezza usa
quindi le quote di riferimento, mentre il calcolo del valore usa le massime.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from bookmaking.domain import Match, OddsQuote

# dal codice del dataset al nostro
DIVISION_MAP = {
    "I1": "IT1", "I2": "IT2", "E0": "EN1", "E1": "EN2",
    "D1": "DE1", "D2": "DE2", "SP1": "ES1", "SP2": "ES2",
    "F1": "FR1", "F2": "FR2", "P1": "PT1",
}
REQUIRED = ("Division", "MatchDate", "HomeTeam", "AwayTeam", "FTHome", "FTAway")


def season_of(when: datetime) -> str:
    """Le stagioni europee scavallano l'anno solare: luglio fa da spartiacque."""
    year = when.year if when.month >= 7 else when.year - 1
    return f"{year}-{year + 1}"


@dataclass
class MatchesCsv:
    """Lettore del CSV unico, filtrato sulle divisioni che ci interessano."""

    path: str
    name: str = "club-football-match-data"

    def load(self, divisions: tuple[str, ...] | None = None,
             since: str | None = None) -> tuple[list[Match], dict[str, list[OddsQuote]]]:
        df = pd.read_csv(self.path, low_memory=False)
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(f"colonne mancanti nel CSV: {missing}")

        df = df[df.Division.isin(DIVISION_MAP)].copy()
        df["div"] = df.Division.map(DIVISION_MAP)
        if divisions:
            df = df[df["div"].isin(divisions)]
        df["quando"] = pd.to_datetime(df.MatchDate, errors="coerce")
        df = df.dropna(subset=["quando", "HomeTeam", "AwayTeam", "FTHome", "FTAway"])
        if since:
            df = df[df["quando"] >= pd.Timestamp(since)]
        df = df.sort_values("quando")

        matches: list[Match] = []
        quotes: dict[str, list[OddsQuote]] = {}
        for row in df.itertuples(index=False):
            when = row.quando.to_pydatetime()
            try:
                hg, ag = int(row.FTHome), int(row.FTAway)
            except (TypeError, ValueError):
                continue
            home = str(row.HomeTeam).strip()
            away = str(row.AwayTeam).strip()
            mid = f"{row.div}|{when:%Y%m%d}|{home}|{away}"
            matches.append(Match(division=row.div, season=season_of(when), kickoff=when,
                                 home=home, away=away, home_goals=hg, away_goals=ag,
                                 match_id=mid))
            qs = []
            rif = self._prices(row, "OddHome", "OddDraw", "OddAway")
            if rif:
                qs.append(OddsQuote("riferimento", "1X2", rif, collected_at=when))
            mx = self._prices(row, "MaxHome", "MaxDraw", "MaxAway")
            if mx:
                qs.append(OddsQuote("massima", "1X2", mx, collected_at=when))
            ou = self._prices2(row, "Over25", "Under25")
            if ou:
                qs.append(OddsQuote("riferimento", "OverUnder 2.5", ou, collected_at=when))
            if qs:
                quotes[mid] = qs
        return matches, quotes

    @staticmethod
    def _prices(row, h: str, d: str, a: str) -> dict[str, float] | None:
        vals = []
        for c in (h, d, a):
            v = getattr(row, c, None)
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            if not (f > 1.0):
                return None
            vals.append(f)
        return {"1": vals[0], "X": vals[1], "2": vals[2]}

    @staticmethod
    def _prices2(row, o: str, u: str) -> dict[str, float] | None:
        vals = []
        for c in (o, u):
            v = getattr(row, c, None)
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            if not (f > 1.0):
                return None
            vals.append(f)
        return {"Over 2.5": vals[0], "Under 2.5": vals[1]}


def default_path() -> str | None:
    for p in ("data/raw/Matches.csv",
              "/home/user/xgabora/club-football-match-data-2000-2025/data/Matches.csv"):
        if Path(p).exists():
            return p
    return None
