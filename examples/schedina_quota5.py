"""Schedina a quota 5: quante gambe, e cosa succede al capitale.

Risponde a due domande concrete.

**Quante gambe conviene giocare** per arrivare a quota 5. La risposta non e'
"il massimo consentito": a parita' di quota finale, ogni gamba in piu' e'
margine del banco pagato un'altra volta, e la probabilita' di incassare scende.
Solo un bonus multipla abbastanza generoso puo' invertire il conto, e la soglia
esatta e' calcolabile.

**Cosa succede provando a raddoppiare** il capitale giocando schedine cosi'.
Questa e' la domanda che di solito non viene fatta, ed e' quella che decide come
va a finire.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookmaking.model.dixon_coles import DixonColes, FitConfig       # noqa: E402
from bookmaking.model.markets import outcome_1x2                     # noqa: E402
from bookmaking.simulate import simulate_country                     # noqa: E402
from bookmaking.staking.schedina import BonusSchedule, optimise      # noqa: E402
from bookmaking.staking.ticket import Leg                            # noqa: E402

# Da sostituire con la tabella del proprio conto: cambia fra bookmaker, nel
# tempo e per campionato. Questi sono valori plausibili, non quelli di Goldbet.
BONUS_ESEMPIO = BonusSchedule(
    by_legs={5: 1.05, 6: 1.10, 7: 1.15, 8: 1.20, 9: 1.30, 10: 1.40},
    min_leg_price=1.20, min_legs=5,
)


def candidate_legs(margin: float = 0.05, seed: int = 31) -> list[Leg]:
    """Gambe candidate da un modello stimato, quotate da un banco con margine."""
    world = simulate_country(n_seasons=4, teams_per_division=18,
                             strength_sd=0.30, seed=seed)
    played = sorted(world.matches, key=lambda m: m.kickoff)
    cut = played[0].day + timedelta(days=400)
    fit = DixonColes(FitConfig(xi=0.0025)).fit([m for m in played if m.day < cut],
                                               reference_day=cut)
    prossime = [m for m in played if m.day >= cut][:40]

    legs: list[Leg] = []
    for m in prossime:
        matrix = fit.score_matrix(m.home, m.away, m.division)
        probs = outcome_1x2(matrix)
        for sel, p in probs.items():
            price = 1.0 / (p * (1.0 + margin))     # quota del banco, margine incluso
            if price < 1.10 or price > 8.0:
                continue
            legs.append(Leg(match_id=m.match_id or "", label=f"{m.home} - {m.away}",
                            market="1X2", selection=sel, bookmaker="goldbet",
                            price=round(price, 2), p_final=p, score_matrix=matrix))
    return legs


def frontiera(legs: list[Leg], target: float, bonus: BonusSchedule,
              etichetta: str) -> list:
    print(f"\n{etichetta}")
    print(f"{'gambe':>6}{'quota':>8}{'bonus':>8}{'quota eff.':>12}"
          f"{'P(vincita)':>12}{'1 volta su':>12}{'EV':>9}")
    print("-" * 68)
    piani = optimise(legs, target=target, max_legs=10, bonus=bonus)
    for p in piani:
        print(f"{len(p.legs):6d}{p.raw_price:8.2f}{(p.bonus - 1) * 100:+7.0f}%"
              f"{p.effective_price:12.2f}{p.probability * 100:11.1f}%"
              f"{p.one_in:12.1f}{p.ev * 100:+8.1f}%")
    return piani


def prova_a_raddoppiare(p_win: float, quota: float, capitale: float = 30.0,
                        puntata: float = 2.0, n_prove: int = 20000,
                        max_giocate: int = 400, seed: int = 7) -> dict:
    """Probabilita' di raddoppiare il capitale prima di esaurirlo."""
    rng = np.random.default_rng(seed)
    raddoppi = rovine = 0
    durate = []
    for _ in range(n_prove):
        c = capitale
        for giocata in range(max_giocate):
            if c < puntata:
                rovine += 1
                durate.append(giocata)
                break
            c -= puntata
            if rng.random() < p_win:
                c += puntata * quota
            if c >= 2 * capitale:
                raddoppi += 1
                durate.append(giocata + 1)
                break
        else:
            durate.append(max_giocate)
    return {"raddoppiato": raddoppi / n_prove, "rovinato": rovine / n_prove,
            "giocate_mediane": float(np.median(durate))}


if __name__ == "__main__":
    legs = candidate_legs()
    print(f"{len(legs)} selezioni candidate da "
          f"{len({l.match_id for l in legs})} partite\n")
    print("=" * 68)
    print("1) Quante gambe per arrivare a quota 5")
    print("=" * 68)

    senza = frontiera(legs, 5.0, BonusSchedule(), "Senza bonus")
    con = frontiera(legs, 5.0, BONUS_ESEMPIO,
                    "Con un bonus d'esempio (NON quello del tuo conto)")

    print("\n2) Il bonus batte il margine composto?")
    print("   Soglia esatta: bonus >= 1/(1-margine)^gambe. Non dipende dalle quote.\n")
    print(f"{'gambe':>6}{'offerto':>10}{'necessario':>13}{'esito':>12}")
    print("-" * 42)
    for r in BONUS_ESEMPIO.verdict(max_legs=10, margin_per_leg=0.05):
        if r["gambe"] < 5:
            continue
        esito = "conviene" if r["conviene"] else "non basta"
        print(f"{r['gambe']:6d}{(r['bonus_offerto'] - 1) * 100:+9.0f}%"
              f"{(r['bonus_necessario'] - 1) * 100:+12.0f}%{esito:>12}")

    print("\n" + "=" * 68)
    print("3) Provare a raddoppiare 30 EUR, 2 EUR per schedina")
    print("=" * 68)
    print("\nQuota 5 con 2 gambe e con 5 gambe e' la stessa vincita. Da 7 gambe in")
    print("su la quota 5 non e' nemmeno raggiungibile: nel calcio non esistono")
    print("abbastanza eventi quasi certi, e la schedina sfora a 7, 10, 23 di quota")
    print("con la probabilita' che crolla di conseguenza.\n")
    print(f"{'schedina':>22}{'quota':>8}{'P(vinc.)':>10}{'raddoppia':>11}{'va a zero':>11}")
    print("-" * 62)
    for piano in senza:
        if len(piano.legs) not in (2, 3, 5, 8, 10):
            continue
        r = prova_a_raddoppiare(piano.probability, piano.effective_price)
        etichetta = f"{len(piano.legs)} gambe"
        print(f"{etichetta:>22}{piano.effective_price:8.2f}"
              f"{piano.probability * 100:9.1f}%{r['raddoppiato'] * 100:10.1f}%"
              f"{r['rovinato'] * 100:10.1f}%")

    print("\n  Il capitale si esaurisce circa due volte su tre. Non e' sfortuna: e' il")
    print("  margine del banco che lavora a ogni giocata. Nessuna costruzione della")
    print("  schedina lo annulla, solo un bonus che lo superi. E piu' gambe metti,")
    print("  piu' alta deve essere la soglia del bonus per starci dentro.")
