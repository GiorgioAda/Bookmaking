"""Il modello batte il mercato? Misurato sulle quote dell'epoca.

E' la domanda che decide se il progetto ha senso, e ha una risposta numerica.
Per ogni partita si confrontano due previsioni fatte *prima* del fischio
d'inizio: quella del modello, stimato solo su cio' che era noto il giorno prima,
e quella implicita nelle quote del bookmaker, ripulite del margine.

Il confronto usa le **quote di riferimento**, non le quote massime di mercato.
Le massime hanno margine quasi nullo e batterle e' molto piu' difficile: usarle
qui gonfierebbe la difficolta' e farebbe sembrare il modello peggiore di quanto
sia sul prezzo che incontra davvero.

Un modello che perde di poco non e' inutile. Il vantaggio pratico nasce dal
confrontare i bookmaker fra loro, non dal battere il consenso: basta che il
modello sia abbastanza vicino da riconoscere quando un banco si e' sbagliato.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookmaking.backtest.metrics import summarise                    # noqa: E402
from bookmaking.backtest.walkforward import WalkForward              # noqa: E402
from bookmaking.ingest.matchescsv import MatchesCsv, default_path    # noqa: E402
from bookmaking.model.dixon_coles import FitConfig                   # noqa: E402
from bookmaking.pricing.devig import DevigMethod, devig              # noqa: E402

PAESI = {"IT": ("IT1", "IT2"), "EN": ("EN1", "EN2"), "DE": ("DE1", "DE2"),
         "ES": ("ES1", "ES2"), "FR": ("FR1", "FR2"), "PT": ("PT1",)}


def confronta(paese: str, divs: tuple[str, ...], cfg: FitConfig,
              src: MatchesCsv) -> dict | None:
    ms, quote = src.load(divisions=divs, since="2016-07-01")
    res = WalkForward(cfg, refit_every_days=7, burn_in_days=730,
                      max_history_days=1460).run(ms)
    p_mod, p_mkt, esiti = [], [], []
    for pred in res.predictions:
        qs = quote.get(pred.match.match_id or "")
        if not qs:
            continue
        rif = next((q for q in qs
                    if q.bookmaker == "riferimento" and q.market == "1X2"), None)
        if rif is None:
            continue
        p_mod.append(pred.probs)
        p_mkt.append(devig(rif.prices, DevigMethod.SHIN))
        esiti.append(pred.outcome)
    if not esiti:
        return None
    mod, mkt = summarise(p_mod, esiti), summarise(p_mkt, esiti)
    return {"n": len(esiti), "modello": mod, "mercato": mkt,
            "scarto_rps": mod["rps"] - mkt["rps"],
            "scarto_ll": mod["log_loss"] - mkt["log_loss"]}


def main() -> None:
    tarature = json.loads(Path("data/config_tarato.json").read_text())
    src = MatchesCsv(default_path())
    print("=" * 74)
    print("Il modello contro il mercato, sulle stesse partite")
    print("=" * 74)
    print("\nRPS piu' basso = previsione migliore. Scarto positivo: vince il mercato.\n")
    print(f"{'paese':>6}{'n':>8}{'RPS mod.':>10}{'RPS merc.':>11}"
          f"{'scarto':>9}{'logloss mod':>13}{'merc':>8}")
    print("-" * 66)
    risultati = {}
    for paese, divs in PAESI.items():
        t = tarature.get(paese)
        if not t:
            continue
        c = confronta(paese, divs, FitConfig(xi=t["xi"], l2=t["l2"]), src)
        if not c:
            print(f"{paese:>6}  nessuna partita con quote")
            continue
        risultati[paese] = c
        print(f"{paese:>6}{c['n']:8d}{c['modello']['rps']:10.4f}"
              f"{c['mercato']['rps']:11.4f}{c['scarto_rps']:+9.4f}"
              f"{c['modello']['log_loss']:13.4f}{c['mercato']['log_loss']:8.4f}")

    if risultati:
        tot_n = sum(c["n"] for c in risultati.values())
        med = sum(c["scarto_rps"] * c["n"] for c in risultati.values()) / tot_n
        print("-" * 66)
        print(f"{'media':>6}{tot_n:8d}{'':10}{'':11}{med:+9.4f}")
        print(f"\nSu {tot_n:,} partite, il modello sta in media {abs(med):.4f} di RPS "
              f"{'sotto' if med < 0 else 'sopra'} il mercato.")
        vinte = [p for p, c in risultati.items() if c["scarto_rps"] < 0]
        if vinte:
            print(f"Batte il mercato in: {', '.join(vinte)}.")
        else:
            print("Non batte il mercato in nessun campionato.")
        print("\nUno scarto sotto 0.005 significa che il modello e' vicino al")
        print("mercato: abbastanza da riconoscere quando un singolo banco sbaglia,")
        print("che e' da dove nasce il vantaggio praticabile.")
    Path("data/contro_mercato.json").write_text(json.dumps(risultati, indent=2))


if __name__ == "__main__":
    main()
