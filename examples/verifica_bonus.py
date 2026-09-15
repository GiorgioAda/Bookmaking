"""Confronta il bonus multipla del tuo conto con la soglia di convenienza.

Il conto e' esatto e sta in una riga:

    valore atteso = bonus x (1 - margine)^gambe - 1

quindi il bonus che pareggia i conti vale ``1/(1-margine)^gambe`` e **non
dipende dalle quote che scegli**, solo dal numero di gambe e dal margine medio
per gamba. Sopra quella soglia allungare la schedina conviene davvero; sotto,
ogni gamba in piu' e' solo margine regalato al banco.

    python examples/verifica_bonus.py data/bonus_goldbet.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bookmaking.staking.schedina import BonusSchedule       # noqa: E402


def main() -> None:
    percorso = sys.argv[1] if len(sys.argv) > 1 else "data/bonus_goldbet.json"
    margini = (0.04, 0.05, 0.07)

    if not Path(percorso).exists():
        print(f"File non trovato: {percorso}")
        print("Copia data/bonus_goldbet.json e compilalo con i dati del tuo conto.")
        return

    bonus = BonusSchedule.from_file(percorso)
    print(f"Tabella caricata da {percorso}")
    print(f"  bonus da {bonus.min_legs} gambe in su, "
          f"quota minima per gamba {bonus.min_leg_price:.2f}\n")

    print("Il bonus batte il margine composto?\n")
    intestazione = f"{'gambe':>6}{'offerto':>10}"
    for m in margini:
        intestazione += f"{f'serve @{m * 100:.0f}%':>13}"
    print(intestazione)
    print("-" * len(intestazione))

    conviene_a = []
    for n in range(bonus.min_legs, 11):
        offerto = bonus.multiplier(n)
        riga = f"{n:6d}{(offerto - 1) * 100:+9.0f}%"
        for m in margini:
            serve = bonus.break_even(n, m)
            segno = "OK" if offerto >= serve else "  "
            riga += f"{(serve - 1) * 100:+10.0f}% {segno}"
            if m == 0.05 and offerto >= serve:
                conviene_a.append(n)
        print(riga)

    print("\n'serve @5%' e' la colonna da guardare: il 5% e' il margine tipico")
    print("sull'1X2 dei bookmaker italiani. Se il modello trova selezioni")
    print("quotate meglio della media, il margine effettivo scende e la soglia")
    print("si abbassa: e' li' che il modello e il bonus lavorano insieme.\n")

    if conviene_a:
        print(f"Con margine del 5% il bonus conviene a {conviene_a} gambe.")
        print("Sono i numeri di gambe su cui vale la pena costruire la schedina.")
    else:
        print("Con margine del 5% il bonus non copre mai il margine composto.")
        print("Conseguenza pratica: conviene la schedina piu' corta che raggiunge")
        print("l'obiettivo, non la piu' lunga. Il bonus non ripaga le gambe in piu'.")


if __name__ == "__main__":
    main()
