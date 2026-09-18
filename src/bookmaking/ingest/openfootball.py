"""Calendari delle partite future dai repository openfootball.

I file sono pensati per essere letti da una persona, non da un programma: una
riga per partita, con la data ripetuta solo quando cambia e il risultato
presente solo se la partita si e' gia' giocata. Proprio quest'ultima cosa li
rende utili qui, perche' distinguere il passato dal futuro non richiede una
fonte separata: le partite senza punteggio sono quelle da giocare.

    ▪ Matchday 4
      Sat Sep 19 2026
        18:30  Udinese Calcio          v Como 1907                1-1 (1-0)
               Genoa CFC               v SSC Napoli

Attenzione ai nomi: openfootball usa la ragione sociale completa ("FC
Internazionale Milano"), lo storico delle quote usa la forma breve ("Inter").
Senza una tabella di corrispondenza il modello non riconosce la squadra, le
assegna il prior delle sconosciute e produce previsioni sbagliate **senza
segnalare nulla**. La corrispondenza e' quindi parte del lettore, non un
dettaglio successivo.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from bookmaking.domain import Match

# dal nome del file openfootball alla nostra divisione
FILE_MAP = {
    "italy/1-seriea": "IT1", "italy/2-serieb": "IT2",
    "england/1-premierleague": "EN1", "england/2-championship": "EN2",
    "deutschland/1-bundesliga": "DE1", "deutschland/2-bundesliga2": "DE2",
    "espana/1-liga": "ES1", "espana/2-liga2": "ES2",
    "france/1-ligue1": "FR1", "france/2-ligue2": "FR2",
    "portugal/1-liga": "PT1",
}

MESI = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

RE_DATA = re.compile(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\w{3})\s+(\d{1,2})(?:\s+(\d{4}))?\s*$")
RE_ORA = re.compile(r"^\s*(\d{1,2}:\d{2})\s+(.*)$")
RE_RIS = re.compile(r"\s+(\d+)-(\d+)(?:\s+\(.*\))?\s*$")


@dataclass
class OpenFootball:
    """Lettore dei calendari, con la tabella dei nomi squadra."""

    root: str = "/home/user/openfootball"
    aliases: dict[str, str] = field(default_factory=dict)
    name: str = "openfootball"

    def season_dir(self, paese: str, stagione: str | None = None) -> Path | None:
        base = Path(self.root) / paese
        if not base.exists():
            return None
        if stagione:
            d = base / stagione
            return d if d.exists() else None
        stagioni = sorted(p for p in base.glob("20*-*") if p.is_dir())
        return stagioni[-1] if stagioni else None

    def available(self, stagione: str | None = None) -> dict[str, Path]:
        """Quali divisioni hanno davvero un calendario pubblicato."""
        trovati: dict[str, Path] = {}
        for chiave, div in FILE_MAP.items():
            paese, nome = chiave.split("/")
            d = self.season_dir(paese, stagione)
            if d is None:
                continue
            f = d / f"{nome}.txt"
            if f.exists():
                trovati[div] = f
        return trovati

    def load(self, stagione: str | None = None) -> list[Match]:
        partite: list[Match] = []
        for div, path in self.available(stagione).items():
            partite.extend(self.parse(path.read_text(encoding="utf-8"), div))
        partite.sort(key=lambda m: m.kickoff)
        return partite

    def parse(self, testo: str, division: str) -> list[Match]:
        anno_corrente = None
        giorno = None
        stagione = None
        out: list[Match] = []

        for riga in testo.splitlines():
            if not riga.strip() or riga.lstrip().startswith(("#", "=", "▪")):
                m = re.search(r"(\d{4})/(\d{2})", riga)
                if m:
                    stagione = f"{m.group(1)}-{int(m.group(1)) + 1}"
                m = re.search(r"(\w{3})\s+\d{1,2}\s+(\d{4})", riga)
                if m and anno_corrente is None:
                    anno_corrente = int(m.group(2))
                continue

            d = RE_DATA.match(riga)
            if d:
                mese, num, anno = MESI.get(d.group(2)), int(d.group(3)), d.group(4)
                if anno:
                    anno_corrente = int(anno)
                if mese is None or anno_corrente is None:
                    continue
                # la stagione scavalca il capodanno: da gennaio in poi l'anno avanza
                anno_eff = anno_corrente
                if giorno is not None and mese < giorno.month:
                    anno_eff = anno_corrente + 1
                    anno_corrente = anno_eff
                giorno = datetime(anno_eff, mese, num)
                continue

            if giorno is None:
                continue
            corpo, ora = riga, None
            o = RE_ORA.match(riga)
            if o:
                ora = o.group(1)
                corpo = o.group(2)
            if " v " not in corpo:
                continue

            hg = ag = None
            r = RE_RIS.search(corpo)
            if r:
                hg, ag = int(r.group(1)), int(r.group(2))
                corpo = corpo[: r.start()]
            try:
                casa, ospiti = corpo.split(" v ", 1)
            except ValueError:
                continue
            casa, ospiti = self.normalise(casa), self.normalise(ospiti)
            if not casa or not ospiti:
                continue

            quando = giorno
            if ora:
                h, mi = ora.split(":")
                quando = giorno.replace(hour=int(h), minute=int(mi))
            out.append(Match(division=division, season=stagione or "",
                             kickoff=quando, home=casa, away=ospiti,
                             home_goals=hg, away_goals=ag,
                             match_id=f"{division}|{quando:%Y%m%d}|{casa}|{ospiti}"))
        return out

    def normalise(self, nome: str) -> str:
        n = " ".join(nome.strip().split())
        return self.aliases.get(n, n)

    def upcoming(self, da: datetime | None = None, giorni: int = 8,
                 stagione: str | None = None) -> list[Match]:
        """Le partite ancora da giocare nella finestra richiesta."""
        da = da or datetime.now()
        fine = da.timestamp() + giorni * 86400
        return [m for m in self.load(stagione)
                if not m.played and da <= m.kickoff and m.kickoff.timestamp() <= fine]
