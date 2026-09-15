"""Simulazione a ciclo chiuso: piu' stagioni di scommesse con budget settimanale.

Questo script risponde alla domanda che conta davvero, e lo fa in un mondo dove
la verita' e' nota per costruzione: *dato quanto e' bravo il bookmaker, cosa
succede al mio capitale?*

Il meccanismo e' interamente onesto:
  - il mondo genera i risultati da probabilita' vere note;
  - il bookmaker quota quelle probabilita' con un errore suo e ci aggiunge il
    margine;
  - il modello non vede ne' le probabilita' vere ne' l'errore del bookmaker:
    stima solo dai risultati passati, come nella realta';
  - le giocate vengono regolate sui risultati veri.

La conclusione a cui si arriva non e' negoziabile ed e' il motivo per cui
questo script esiste: il profitto non dipende da quanto e' buono il modello in
assoluto, ma da quanto e' buono *rispetto al bookmaker*, e il margine del banco
e' la soglia da superare prima di guadagnare un centesimo.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookmaking.advisor import Advisor                    # noqa: E402
from bookmaking.domain import MatchOdds, OddsQuote        # noqa: E402
from bookmaking.model.dixon_coles import DixonColes, FitConfig   # noqa: E402
from bookmaking.model.markets import outcome_1x2          # noqa: E402
from bookmaking.simulate import simulate_country          # noqa: E402
from bookmaking.staking.kelly import BankrollPolicy       # noqa: E402

BOOKS = ("goldbet", "sisal", "snai", "eurobet", "planetwin365")


def true_probs(lam: float, mu: float, rho: float = -0.11, mg: int = 15) -> dict[str, float]:
    gx = np.arange(mg + 1)
    m = np.outer(poisson.pmf(gx, lam), poisson.pmf(gx, mu))
    m[0, 0] *= 1 - lam * mu * rho
    m[0, 1] *= 1 + lam * rho
    m[1, 0] *= 1 + mu * rho
    m[1, 1] *= 1 - rho
    m = np.clip(m, 0, None)
    return outcome_1x2(m / m.sum())


def book_odds(p_true: dict[str, float], rng: np.random.Generator,
              book_error: float, margin: float) -> dict[str, dict[str, float]]:
    """Quote dei bookmaker: probabilita' vera + errore del banco + margine.

    ``book_error`` e' la deviazione standard dell'errore del bookmaker in scala
    logaritmica. E' il parametro che decide tutto: a zero il banco e' perfetto e
    nessun modello puo' batterlo.
    """
    out = {}
    shared = rng.normal(0, book_error, 3)   # errore comune a tutto il mercato
    for book in BOOKS:
        own = rng.normal(0, book_error * 0.35, 3)   # scarto del singolo book
        logit = np.log([p_true["1"], p_true["X"], p_true["2"]]) + shared + own
        p = np.exp(logit - logit.max())
        p = p / p.sum()
        with_margin = p * (1.0 + margin)
        out[book] = {k: float(1.0 / v) for k, v in zip(("1", "X", "2"), with_margin)}
    return out


def run(book_error: float, margin: float, model_weight: float,
        n_seasons: int = 6, seed: int = 21, verbose: bool = False,
        policy: BankrollPolicy | None = None) -> dict:
    world = simulate_country(n_seasons=n_seasons, teams_per_division=18,
                             strength_sd=0.30, seed=seed)
    rng = np.random.default_rng(seed + 1000)
    played = sorted(world.matches, key=lambda m: m.kickoff)

    policy = policy or BankrollPolicy(weekly_budget=30.0)
    engine = DixonColes(FitConfig(xi=0.0025, l2=2.0))

    start = played[0].day + timedelta(days=420)
    history = [m for m in played if m.day < start]
    future = [m for m in played if m.day >= start]

    bankroll = 0.0
    staked = total_return = 0.0
    n_bets = n_won = 0
    weeks = 0
    ev_claimed = ev_true = 0.0
    curve = []

    fit = engine.fit(history, reference_day=start)
    advisor = Advisor(fit=fit, policy=policy, model_weight=model_weight)
    day = start
    last_fit = start

    while future:
        week_end = day + timedelta(days=7)
        week = [m for m in future if day <= m.day < week_end]
        future = [m for m in future if m.day >= week_end]
        if not week:
            day = week_end
            continue

        if (day - last_fit).days >= 7:
            fit = engine.fit(history, reference_day=day)
            advisor = Advisor(fit=fit, policy=policy, model_weight=model_weight)
            last_fit = day

        odds_map, truths = {}, {}
        for m in week:
            pt = true_probs(world.true_lambda[m.match_id], world.true_mu[m.match_id])
            truths[m.match_id] = pt
            quotes = [OddsQuote(b, "1X2", pr)
                      for b, pr in book_odds(pt, rng, book_error, margin).items()]
            odds_map[m.match_id] = MatchOdds(m.match_id, quotes)

        plan, _ = advisor.weekly_plan(week, odds_map)
        weeks += 1

        by_id = {m.match_id: m for m in week}
        for bet in plan.bets:
            match = by_id[bet.edge.match_id]
            staked += bet.stake
            n_bets += 1
            ev_claimed += bet.stake * bet.edge.ev
            p_real = truths[match.match_id][bet.edge.selection]
            ev_true += bet.stake * (p_real * bet.edge.price - 1.0)
            if match.result.value == bet.edge.selection:
                total_return += bet.stake * bet.edge.price
                n_won += 1
            bankroll = total_return - staked
        curve.append(bankroll)
        history.extend(week)
        day = week_end

    return {
        "settimane": weeks, "giocate": n_bets, "vinte": n_won,
        "puntato": staked, "incassato": total_return, "profitto": total_return - staked,
        "roi": (total_return - staked) / staked if staked else 0.0,
        "ev_dichiarato": ev_claimed / staked if staked else 0.0,
        "ev_reale": ev_true / staked if staked else 0.0,
        "curva": curve,
    }


if __name__ == "__main__":
    print("=" * 78)
    print("Scommettere 30 EUR a settimana: cosa succede davvero")
    print("=" * 78)

    print("\n1) L'errore del bookmaker e' la variabile decisiva.")
    print("   Misura quanto il banco sbaglia le sue probabilita'. A 0.00 e' perfetto.\n")
    print(f"{'errore banco':>13} {'giocate':>8} {'puntato':>9} {'profitto':>9} "
          f"{'ROI':>8} {'EV dich.':>9} {'EV vero':>9}")
    print("-" * 70)
    for book_error in (0.00, 0.05, 0.10, 0.20):
        r = run(book_error=book_error, margin=0.05, model_weight=0.65)
        print(f"{book_error:13.2f} {r['giocate']:8d} "
              f"{r['puntato']:8.0f}E {r['profitto']:+8.0f}E {r['roi']*100:+7.1f}% "
              f"{r['ev_dichiarato']*100:+8.1f}% {r['ev_reale']*100:+8.1f}%")
    print("\n   EV dich. = vantaggio che il sistema crede di avere")
    print("   EV vero  = vantaggio effettivo, calcolato con le probabilita' vere")
    print("\n   Con il banco perfetto il sistema dichiara un vantaggio a due cifre")
    print("   mentre quello vero e' negativo e pari al margine: e' la maledizione")
    print("   del vincitore. Selezionando le partite dove il modello dissente di")
    print("   piu' dal mercato si selezionano soprattutto i propri errori.")

    print("\n2) Quanto conviene far prevalere il modello sul mercato?\n")
    print(f"{'peso modello':>13} {'giocate':>8} {'EV dich.':>9} {'EV vero':>9} {'ROI':>8}")
    print("-" * 52)
    for mw in (0.0, 0.3, 0.5, 0.65, 0.85, 1.0):
        r = run(book_error=0.10, margin=0.05, model_weight=mw)
        print(f"{mw:13.2f} {r['giocate']:8d} {r['ev_dichiarato']*100:+8.1f}% "
              f"{r['ev_reale']*100:+8.1f}% {r['roi']*100:+7.1f}%")
    print("\n   Il vantaggio vero resta intorno al +5% per qualunque peso sopra 0.3:")
    print("   alzare il peso del modello non fa guadagnare di piu', gonfia solo il")
    print("   vantaggio dichiarato. E' un problema concreto, non estetico, perche'")
    print("   e' su quel numero che Kelly calcola quanto puntare.")
