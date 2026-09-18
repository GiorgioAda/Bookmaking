"""Confronto fra i bonus multipla dei bookmaker, contro la soglia di convenienza.

La domanda non e' "chi offre il bonus piu' alto", perche' il bonus va sempre
confrontato con qualcosa: il margine composto che si accumula aggiungendo gambe.
La soglia e' esatta e non dipende dalle quote scelte:

    bonus necessario = 1/(1 - margine)^gambe

La seconda domanda, che i siti di comparazione non fanno mai, e' se il vantaggio
sia **incassabile**. Un bonus che diventa sufficiente solo a venticinque gambe
promette un valore atteso positivo su una schedina che vince una volta ogni
settecento: con quindici giocate a settimana, significa aspettare un anno per
una vincita. Il vantaggio c'e' sulla carta e non arriva mai nella pratica.

    python examples/confronta_bonus.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

MARGINE = 0.04          # margine per gamba ipotizzato sulle quote corte
GIOCATE_SETTIMANA = 15  # 30 euro a settimana, 2 euro a schedina


def interpola(ancoraggi: dict[int, float], n: int) -> tuple[float, bool]:
    """Bonus a ``n`` gambe. Restituisce anche se il valore e' interpolato.

    Fra due ancoraggi si interpola in scala logaritmica, perche' e' cosi' che
    queste scale crescono. Resta una stima, ed e' segnalata come tale.
    """
    if n in ancoraggi:
        return ancoraggi[n], False
    sotto = [k for k in ancoraggi if k < n]
    sopra = [k for k in ancoraggi if k > n]
    if not sotto:
        return 0.0, True
    if not sopra:
        return ancoraggi[max(sotto)], True
    a, b = max(sotto), min(sopra)
    import math
    va, vb = max(ancoraggi[a], 0.1), max(ancoraggi[b], 0.1)
    peso = (n - a) / (b - a)
    return math.exp(math.log(va) + peso * (math.log(vb) - math.log(va))), True


def necessario(n: int, margine: float = MARGINE) -> float:
    return (1.0 / (1.0 - margine) ** n - 1.0) * 100.0


def probabilita(n: int, quota_minima: float, margine: float = MARGINE) -> float:
    return ((1.0 - margine) / quota_minima) ** n


def attesa(p: float) -> str:
    settimane = 1.0 / p / GIOCATE_SETTIMANA
    if settimane < 1:
        return "< 1 settimana"
    if settimane <= 104:
        return f"{settimane:.0f} settimane"
    return f"{settimane / 52:.1f} anni"


def limite_praticabilita(quota_minima: float = 1.25,
                         margine: float = MARGINE) -> list[dict[str, float]]:
    """Fin dove la schedina resta incassabile, e quanto bonus servirebbe proprio li'.

    E' la domanda rovesciata, e ha un pregio: la risposta non dipende dai valori
    intermedi della tabella bonus, che i regolamenti pubblicano a scaglioni e le
    fonti secondarie riportano male. Dipende solo dalla quota minima richiesta e
    dal margine, che sono noti.
    """
    import math
    righe = []
    for ogni in (10, 25, 50, 100, 250, 1000):
        n = int(math.log(1 / ogni) / math.log((1 - margine) / quota_minima))
        p = ((1 - margine) / quota_minima) ** n
        righe.append({"una_vincita_ogni": ogni, "gambe_max": n,
                      "quota": quota_minima ** n, "p_vincita": p,
                      "bonus_necessario": necessario(n, margine),
                      "attesa": attesa(p)})
    return righe


def main() -> None:
    percorso = Path("data/bonus_bookmaker.json")
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    books = dati["bookmaker"]

    print("=" * 78)
    print("Bonus multipla: chi supera la soglia, e a quante gambe")
    print("=" * 78)
    print(f"\nMargine ipotizzato: {MARGINE * 100:.0f}% per gamba.")
    print("I valori fra ancoraggi noti sono interpolati e marcati con ~.\n")

    gambe = (5, 8, 10, 12, 15, 20, 25, 30)
    intestazione = f"{'bookmaker':<14}" + "".join(f"{g:>8}" for g in gambe)
    print(intestazione)
    print(f"{'serve':<14}" + "".join(f"{necessario(g):>6.0f}% " for g in gambe))
    print("-" * len(intestazione))

    incroci: dict[str, int | None] = {}
    for nome, b in books.items():
        ancoraggi = {int(k): float(v) for k, v in b["ancoraggi"].items()}
        riga = f"{nome:<14}"
        incrocio = None
        for g in gambe:
            if g < b["gambe_minime"]:
                riga += f"{'-':>7} "
                continue
            val, stimato = interpola(ancoraggi, g)
            # il marcatore va dopo il numero: come prefisso si attacca
            # visivamente alla colonna precedente e confonde la lettura
            marca = "~" if stimato else " "
            riga += f"{val:>6.0f}%{marca}"
            if incrocio is None and val >= necessario(g):
                incrocio = g
        incroci[nome] = incrocio
        print(riga)

    print("\n" + "=" * 78)
    print("Dove il bonus diventa sufficiente, e cosa costa arrivarci")
    print("=" * 78 + "\n")
    print(f"{'bookmaker':<14}{'gambe':>7}{'quota':>9}{'P(vincita)':>12}"
          f"{'1 su':>7}{'attesa':>14}")
    print("-" * 63)
    for nome, g in sorted(incroci.items(), key=lambda kv: (kv[1] is None, kv[1] or 0)):
        b = books[nome]
        if g is None:
            print(f"{nome:<14}{'mai':>7}{'':>9}{'':>12}{'':>7}"
                  f"{'non conviene':>14}")
            continue
        qmin = b["quota_minima_per_gamba"]
        p = probabilita(g, qmin)
        print(f"{nome:<14}{g:>7}{qmin ** g:>9.1f}{p * 100:>11.2f}%"
              f"{1 / p:>7.0f}{attesa(p):>14}")

    print("\nLa colonna 'attesa' e' calcolata su 15 schedine a settimana,")
    print("cioe' 30 euro settimanali a 2 euro l'una.\n")
    print("Conclusione: il bonus supera il margine composto solo dove la")
    print("schedina vince una volta ogni centinaia di tentativi. Il vantaggio")
    print("esiste sulla carta e non si concretizza in un tempo umano.")
    print("\n" + "=" * 78)
    print("La domanda rovesciata: fin dove la schedina e' incassabile?")
    print("=" * 78)
    print("\nQuesta risposta non dipende dai valori intermedi della tabella bonus,")
    print("che i regolamenti danno a scaglioni e le fonti secondarie riportano")
    print("male. Dipende solo dalla quota minima e dal margine, entrambi noti.\n")
    print(f"{'una vincita ogni':>17}{'gambe max':>11}{'quota':>9}"
          f"{'bonus serve':>13}{'attesa':>15}")
    print("-" * 65)
    for r in limite_praticabilita():
        print(f"{r['una_vincita_ogni']:>12} tentativi{r['gambe_max']:>11}"
              f"{r['quota']:>9.1f}{r['bonus_necessario']:>+12.0f}%{r['attesa']:>15}")
    print("\nIncrociando con la tabella sopra: nella fascia dove la schedina e'")
    print("ancora incassabile (fino a 14-17 gambe) il bonus offerto e' intorno al")
    print("+30/+50% e ne servirebbe il +77/+100%. Il divario non si stringe")
    print("avvicinandosi: si allarga, e si chiude solo a ridosso delle 30 gambe.")

    print("\nA poche gambe, dove la vincita arriva davvero, nessun bonus")
    print("italiano copre il margine: li' conviene la schedina piu' corta che")
    print("raggiunge l'obiettivo, ed e' il caso trattato in schedina_quota5.py.")
    print(f"\nParametri principali (5 eventi minimi, quota 1.25, tetto 50.000 EUR,")
    print(f"limite dei 7 giorni) confermati da fonti indipendenti; le percentuali")
    print(f"intermedie no. Vedi {percorso}.")


if __name__ == "__main__":
    main()
