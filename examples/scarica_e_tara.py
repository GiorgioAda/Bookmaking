"""Scarica i dati veri, tara il modello e verifica se batte il mercato.

Va eseguito in locale: serve accesso a internet verso football-data.co.uk.

Fa quattro cose, in ordine di importanza crescente:

1. scarica e verifica lo storico degli undici campionati, segnalando cosa manca
   invece di caricare in silenzio dati parziali;
2. controlla la coerenza dei nomi squadra fra stagioni, perche' un
   disallineamento non genera un errore: genera una squadra "nuova" che riceve
   il prior delle sconosciute e previsioni sbagliate senza avvisare;
3. tara il decadimento temporale e la regolarizzazione **per nazione**, in
   walk-forward;
4. confronta il modello con le quote di chiusura dell'epoca.

Il punto 4 e' quello che decide se il progetto ha senso. La quota di chiusura e'
il prezzo piu' affilato che il mercato produce, dopo che tutte le informazioni
(formazioni comprese) sono entrate nel prezzo. E' il confronto piu' severo che
esista: batterla e' molto piu' difficile che battere la quota di apertura, che e'
quella su cui si gioca davvero. Un modello che perde contro la chiusura ma di
poco puo' ancora essere utile; uno che perde di molto non lo e'.

    python examples/scarica_e_tara.py --stagioni 6
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookmaking.backtest.metrics import summarise                    # noqa: E402
from bookmaking.backtest.walkforward import WalkForward              # noqa: E402
from bookmaking.domain import Match                                  # noqa: E402
from bookmaking.ingest.footballdata import FootballDataCsv           # noqa: E402
from bookmaking.leagues import COUNTRIES, DIVISIONS, divisions_of    # noqa: E402
from bookmaking.model.dixon_coles import FitConfig                   # noqa: E402
from bookmaking.pricing.consensus import consensus_probabilities     # noqa: E402


def stagioni_recenti(n: int, ultima_inizio: int) -> list[str]:
    return [f"{y}-{y + 1}" for y in range(ultima_inizio - n + 1, ultima_inizio + 1)]


def scarica(stagioni: list[str], verifica: bool
            ) -> tuple[dict[str, list[Match]], dict[str, list]]:
    """Storico per nazione, piu' le quote di chiusura indicizzate per partita."""
    per_nazione: dict[str, list[Match]] = {c: [] for c in COUNTRIES}
    quote: dict[str, list] = {}
    fonte = FootballDataCsv()

    for div in DIVISIONS:
        for stagione in stagioni:
            try:
                testo = fonte._download(fonte.url_for(div.code, stagione))
            except Exception as exc:                      # noqa: BLE001
                print(f"  [salto] {div.code} {stagione}: {exc}")
                continue
            try:
                partite = fonte.parse(testo, div.code, stagione, verify=verifica)
            except ValueError as exc:
                print(f"  [errore] {div.code} {stagione}: {exc}")
                continue
            per_nazione[div.country].extend(partite)
            quote.update(fonte.parse_closing_odds(testo, div.code, stagione))
            print(f"  {div.code} {stagione}: {len(partite)} partite")
    return per_nazione, quote


def controlla_nomi(partite: list[Match]) -> list[tuple[str, int]]:
    """Squadre viste pochissime volte: quasi sempre sono nomi scritti male.

    Una squadra vera gioca almeno una trentina di partite a stagione. Chi ne ha
    tre o quattro in totale non e' una squadra: e' la stessa squadra scritta in
    due modi diversi in stagioni diverse.
    """
    conteggio = Counter()
    for m in partite:
        conteggio[m.home] += 1
        conteggio[m.away] += 1
    return [(nome, n) for nome, n in sorted(conteggio.items(), key=lambda kv: kv[1])
            if n < 10]


def tara(partite: list[Match], nazione: str) -> dict:
    migliore = None
    for xi in (0.0015, 0.0025, 0.0035, 0.005, 0.008):
        for l2 in (0.5, 2.0, 6.0):
            res = WalkForward(FitConfig(xi=xi, l2=l2), refit_every_days=7,
                              burn_in_days=400).run(partite)
            m = res.metrics()
            if not m.get("n"):
                continue
            if migliore is None or m["rps"] < migliore["rps"]:
                migliore = {"xi": xi, "l2": l2, **m}
    if migliore:
        print(f"  {nazione}: xi={migliore['xi']} l2={migliore['l2']} "
              f"RPS={migliore['rps']:.4f} logloss={migliore['log_loss']:.4f} "
              f"su {migliore['n']} partite")
    return migliore or {}


def contro_il_mercato(partite: list[Match], quote: dict[str, list],
                      config: FitConfig) -> dict:
    """Modello contro quota di chiusura, sulle stesse partite."""
    res = WalkForward(config, refit_every_days=7, burn_in_days=400).run(partite)
    p_modello, p_mercato, esiti = [], [], []
    for pred in res.predictions:
        q = quote.get(pred.match.match_id or "")
        if not q:
            continue
        try:
            mercato = consensus_probabilities(q)
        except ValueError:
            continue
        if set(mercato) != {"1", "X", "2"}:
            continue
        p_modello.append(pred.probs)
        p_mercato.append(mercato)
        esiti.append(pred.outcome)

    if not esiti:
        return {"n": 0}
    mod = summarise(p_modello, esiti)
    mer = summarise(p_mercato, esiti)
    return {"n": len(esiti), "modello": mod, "mercato": mer,
            "scarto_rps": mod["rps"] - mer["rps"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stagioni", type=int, default=6)
    ap.add_argument("--ultima-stagione", type=int, default=2024,
                    help="anno d'inizio dell'ultima stagione, es. 2024 per 2024-2025")
    ap.add_argument("--senza-verifica", action="store_true")
    args = ap.parse_args()

    stagioni = stagioni_recenti(args.stagioni, args.ultima_stagione)
    print(f"Stagioni richieste: {stagioni[0]} ... {stagioni[-1]}\n")

    print("1) Scaricamento")
    per_nazione, quote = scarica(stagioni, verifica=not args.senza_verifica)
    totale = sum(len(v) for v in per_nazione.values())
    print(f"\n  totale: {totale} partite, {len(quote)} con quote di chiusura")
    if totale == 0:
        print("\nNessun dato scaricato. Controlla la connessione e gli URL in "
              "docs/DATA.md prima di proseguire.")
        return

    print("\n2) Coerenza dei nomi squadra")
    for nazione, partite in per_nazione.items():
        sospetti = controlla_nomi(partite)
        if sospetti:
            print(f"  {nazione}: {len(sospetti)} nomi sospetti -> "
                  f"{[n for n, _ in sospetti[:6]]}")
        else:
            print(f"  {nazione}: nessun nome sospetto")
    print("  (i sospetti vanno risolti in data/team_aliases.json prima di fidarsi "
          "dei risultati)")

    print("\n3) Taratura per nazione (walk-forward)")
    tarature = {}
    for nazione, partite in per_nazione.items():
        if len(partite) < 500:
            print(f"  {nazione}: solo {len(partite)} partite, salto")
            continue
        tarature[nazione] = tara(partite, nazione)

    print("\n4) Modello contro quota di chiusura")
    print("   (la chiusura e' il prezzo piu' affilato del mercato: e' il confronto")
    print("    piu' severo possibile, piu' duro di quello che affronterai giocando)\n")
    confronti = {}
    for nazione, t in tarature.items():
        if not t:
            continue
        cfg = FitConfig(xi=t["xi"], l2=t["l2"])
        c = contro_il_mercato(per_nazione[nazione], quote, cfg)
        confronti[nazione] = c
        if not c.get("n"):
            print(f"  {nazione}: nessuna partita con quote, salto")
            continue
        verdetto = "il mercato vince" if c["scarto_rps"] > 0 else "IL MODELLO VINCE"
        print(f"  {nazione}: modello RPS {c['modello']['rps']:.4f} | "
              f"mercato RPS {c['mercato']['rps']:.4f} | "
              f"scarto {c['scarto_rps']:+.4f}  -> {verdetto}")

    out = Path("data/config_tarato.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"stagioni": stagioni, "taratura": tarature,
                               "contro_mercato": confronti}, indent=2))
    print(f"\nScritto {out}")
    print("\nCome leggere il punto 4: uno scarto positivo ma piccolo (sotto 0.005)")
    print("significa che il modello e' vicino al mercato, che e' gia' un buon")
    print("risultato — il vantaggio nascera' dal confronto fra book, non dal")
    print("battere la chiusura. Uno scarto grande significa che il modello non e'")
    print("pronto e che le puntate andrebbero fatte con molta piu' prudenza.")


if __name__ == "__main__":
    main()
