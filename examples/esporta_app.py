"""Prepara i dati che l'app usa: rating delle squadre e partite in calendario.

L'app gira nel browser e non puo' eseguire scipy, quindi la stima del modello
avviene qui, una volta, e in pagina finiscono solo i parametri gia' pronti:
attacco e difesa di ogni squadra, livello-gol e fattore campo di ogni divisione.
Con quelli il browser costruisce la matrice dei punteggi da solo, che e' poca
aritmetica.

I pesi sono quelli tarati sui dati veri (``data/config_tarato.json``), diversi
per nazione perche' la velocita' con cui le squadre cambiano non e' la stessa
ovunque.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookmaking.ingest.aliases import carica                        # noqa: E402
from bookmaking.ingest.matchescsv import MatchesCsv, default_path   # noqa: E402
from bookmaking.ingest.openfootball import OpenFootball             # noqa: E402
from bookmaking.leagues import BY_CODE                              # noqa: E402
from bookmaking.model.dixon_coles import DixonColes, FitConfig      # noqa: E402

PAESI = {"IT": ("IT1", "IT2"), "EN": ("EN1", "EN2"), "DE": ("DE1", "DE2"),
         "ES": ("ES1", "ES2"), "FR": ("FR1", "FR2"), "PT": ("PT1",)}
FINESTRA = 1460


def main(giorni: int = 10) -> None:
    tarature = json.loads(Path("data/config_tarato.json").read_text())
    src = MatchesCsv(default_path())
    oggi = datetime.now()

    squadre: dict[str, dict] = {}
    divisioni: dict[str, dict] = {}
    for paese, divs in PAESI.items():
        t = tarature[paese]
        ms, _ = src.load(divisions=divs)
        limite = oggi.timestamp() - FINESTRA * 86400
        ms = [m for m in ms if m.kickoff.timestamp() >= limite]
        fit = DixonColes(FitConfig(xi=t["xi"], l2=t["l2"])).fit(ms, reference_day=oggi.date())
        for i, nome in enumerate(fit.teams):
            squadre[nome] = {"att": round(float(fit.attack[i]), 4),
                             "dif": round(float(fit.defence[i]), 4),
                             "paese": paese}
        for i, d in enumerate(fit.divisions):
            divisioni[d] = {"base": round(float(fit.base[i]), 4),
                            "casa": round(float(fit.home_adv[i]), 4),
                            "nome": BY_CODE[d].name if d in BY_CODE else d}
        print(f"  {paese}: {len(fit.teams)} squadre da {fit.n_matches} partite "
              f"(xi={t['xi']}, rho={fit.rho:+.3f})")

    rho = round(float(fit.rho), 4)
    alias = carica()
    of = OpenFootball(aliases=alias)
    prossime = of.upcoming(da=oggi, giorni=giorni)
    partite = []
    sconosciute = set()
    for m in prossime:
        noti = m.home in squadre and m.away in squadre
        if not noti:
            for t_ in (m.home, m.away):
                if t_ not in squadre:
                    sconosciute.add(f"{m.division}: {t_}")
        partite.append({"id": m.match_id, "div": m.division,
                        "quando": m.kickoff.isoformat(timespec="minutes"),
                        "casa": m.home, "ospiti": m.away, "noti": noti})

    # Le tabelle bonus servono in app perche' una multipla si gioca su un solo
    # bookmaker: quota, bonus e regole dipendono da quale.
    bonus = json.loads(Path("data/bonus_bookmaker.json").read_text(encoding="utf-8"))
    books = {k: {"gambe_minime": v["gambe_minime"],
                 "quota_minima": v["quota_minima_per_gamba"],
                 "ancoraggi": {int(a): b for a, b in v["ancoraggi"].items()},
                 "nota": v.get("note")}
             for k, v in bonus["bookmaker"].items()}

    dati = {"generato": oggi.isoformat(timespec="minutes"), "rho": rho,
            "squadre": squadre, "divisioni": divisioni, "partite": partite,
            "calendari_disponibili": sorted(of.available()),
            "bookmaker": books,
            "prior_sconosciuta": {"att": -0.12, "dif": 0.12}}
    out = Path("app/dati.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(dati, ensure_ascii=False, separators=(",", ":")))

    print(f"\n{len(squadre)} squadre, {len(divisioni)} divisioni, "
          f"{len(partite)} partite nei prossimi {giorni} giorni")
    print(f"calendari disponibili: {', '.join(sorted(of.available()))}")
    if sconosciute:
        print(f"\nATTENZIONE: {len(sconosciute)} squadre in calendario senza rating.")
        print("Riceveranno il prior delle sconosciute e previsioni poco affidabili:")
        for s in sorted(sconosciute):
            print(f"  {s}")
    else:
        print("tutte le squadre in calendario hanno un rating")
    print(f"\nscritto {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
