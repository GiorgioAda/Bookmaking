"""Risultati storici da football-data.co.uk.

E' la fonte gratuita piu' pratica per gli undici campionati coperti: un CSV per
divisione e stagione, con risultati e quote di chiusura di diversi bookmaker.
Quelle quote storiche valgono quanto i risultati, perche' permettono di
misurare il modello contro il mercato dell'epoca invece che contro un
riferimento arbitrario.

NOTA: il formato e i nomi delle colonne qui sotto seguono la documentazione
della fonte, ma non sono stati verificati contro il sito dal vivo (l'ambiente in
cui questo modulo e' stato scritto non aveva accesso di rete verso l'esterno).
Il primo scaricamento va fatto con ``verify=True``, che controlla le colonne e
segnala cosa manca invece di caricare dati silenziosamente sbagliati.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from bookmaking.domain import Match, OddsQuote
from bookmaking.ingest.base import normalise_team
from bookmaking.leagues import BY_CODE

BASE_URL = "https://www.football-data.co.uk/mmz4281"

# Quote di chiusura per bookmaker, come compaiono nei CSV.
ODDS_COLUMNS: dict[str, tuple[str, str, str]] = {
    "bet365": ("B365CH", "B365CD", "B365CA"),
    "pinnacle": ("PSCH", "PSCD", "PSCA"),
    "williamhill": ("WHCH", "WHCD", "WHCA"),
    "marathonbet": ("MaxCH", "MaxCD", "MaxCA"),
}
FALLBACK_ODDS_COLUMNS: dict[str, tuple[str, str, str]] = {
    "bet365": ("B365H", "B365D", "B365A"),
    "pinnacle": ("PSH", "PSD", "PSA"),
    "williamhill": ("WHH", "WHD", "WHA"),
}
REQUIRED = ("Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG")


@dataclass
class FootballDataCsv:
    """Lettore dei CSV di football-data.co.uk, da URL o da file locale."""

    name: str = "football-data.co.uk"
    cache_dir: str | None = "data/raw"
    timeout: float = 30.0

    def url_for(self, division: str, season: str) -> str:
        """``season`` in forma "2024-2025" diventa "2425" nell'URL della fonte."""
        div = BY_CODE.get(division)
        if div is None or div.footballdata_code is None:
            raise ValueError(f"divisione senza codice football-data: {division}")
        start, end = season.split("-")
        code = f"{start[-2:]}{end[-2:]}"
        return f"{BASE_URL}/{code}/{div.footballdata_code}.csv"

    def fetch_results(self, division: str, season: str,
                      verify: bool = False) -> list[Match]:
        text = self._download(self.url_for(division, season))
        return self.parse(text, division, season, verify=verify)

    def load_file(self, path: str, division: str, season: str,
                  verify: bool = False) -> list[Match]:
        with open(path, "r", encoding="latin-1") as fh:
            return self.parse(fh.read(), division, season, verify=verify)

    def parse(self, text: str, division: str, season: str,
              verify: bool = False) -> list[Match]:
        df = pd.read_csv(io.StringIO(text), encoding_errors="ignore")
        df.columns = [c.strip() for c in df.columns]

        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            raise ValueError(
                f"colonne mancanti nel CSV di {division} {season}: {missing}. "
                f"Colonne trovate: {list(df.columns)[:15]}")
        if verify:
            self._report_columns(df, division, season)

        df = df.dropna(subset=list(REQUIRED))
        matches: list[Match] = []
        for row in df.itertuples(index=False):
            kickoff = self._parse_datetime(getattr(row, "Date"),
                                           getattr(row, "Time", None))
            if kickoff is None:
                continue
            home = normalise_team(str(getattr(row, "HomeTeam")))
            away = normalise_team(str(getattr(row, "AwayTeam")))
            try:
                hg, ag = int(getattr(row, "FTHG")), int(getattr(row, "FTAG"))
            except (TypeError, ValueError):
                continue
            matches.append(Match(
                division=division, season=season, kickoff=kickoff,
                home=home, away=away, home_goals=hg, away_goals=ag,
                match_id=f"{division}|{season}|{kickoff:%Y%m%d}|{home}|{away}",
            ))
        return matches

    def parse_closing_odds(self, text: str, division: str,
                           season: str) -> dict[str, list[OddsQuote]]:
        """Quote di chiusura storiche, indicizzate per identificativo partita.

        Servono al backtest: senza di esse si puo' misurare l'accuratezza del
        modello ma non se batteva davvero il mercato, che e' la domanda vera.
        """
        df = pd.read_csv(io.StringIO(text), encoding_errors="ignore")
        df.columns = [c.strip() for c in df.columns]
        out: dict[str, list[OddsQuote]] = {}
        for row in df.itertuples(index=False):
            kickoff = self._parse_datetime(getattr(row, "Date", None),
                                           getattr(row, "Time", None))
            if kickoff is None:
                continue
            home = normalise_team(str(getattr(row, "HomeTeam", "")))
            away = normalise_team(str(getattr(row, "AwayTeam", "")))
            key = f"{division}|{season}|{kickoff:%Y%m%d}|{home}|{away}"
            quotes: list[OddsQuote] = []
            for book, cols in ODDS_COLUMNS.items():
                prices = self._read_prices(row, cols) or \
                    self._read_prices(row, FALLBACK_ODDS_COLUMNS.get(book, ()))
                if prices:
                    quotes.append(OddsQuote(book, "1X2", prices, collected_at=kickoff))
            if quotes:
                out[key] = quotes
        return out

    @staticmethod
    def _read_prices(row, cols: tuple[str, ...]) -> dict[str, float] | None:
        if len(cols) != 3:
            return None
        vals = []
        for c in cols:
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
    def _parse_datetime(day, clock=None) -> datetime | None:
        if day is None or (isinstance(day, float) and pd.isna(day)):
            return None
        text = str(day).strip()
        # La fonte ha usato sia anni a due cifre sia a quattro nel corso degli anni.
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
        if clock is not None and not (isinstance(clock, float) and pd.isna(clock)):
            try:
                t = datetime.strptime(str(clock).strip(), "%H:%M").time()
                parsed = parsed.replace(hour=t.hour, minute=t.minute)
            except ValueError:
                pass
        return parsed

    @staticmethod
    def _report_columns(df: pd.DataFrame, division: str, season: str) -> None:
        found = {b: cols for b, cols in ODDS_COLUMNS.items()
                 if all(c in df.columns for c in cols)}
        print(f"[{division} {season}] {len(df)} righe, {len(df.columns)} colonne")
        print(f"  quote di chiusura disponibili per: {sorted(found) or 'nessun book'}")
        assenti = [b for b in ODDS_COLUMNS if b not in found]
        if assenti:
            print(f"  senza quote di chiusura: {assenti} (si usera' il ripiego)")

    def _download(self, url: str) -> str:
        import os
        import urllib.request

        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)
            cached = os.path.join(self.cache_dir, url.replace("/", "_").replace(":", ""))
            if os.path.exists(cached):
                with open(cached, "r", encoding="latin-1") as fh:
                    return fh.read()
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            raw = resp.read().decode("latin-1")
        if self.cache_dir:
            with open(cached, "w", encoding="latin-1") as fh:
                fh.write(raw)
        return raw
