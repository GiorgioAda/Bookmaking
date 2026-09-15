"""Costruzione della schedina a quota obiettivo, con bonus multipla.

Il problema posto e': una schedina di al massimo dieci gambe che arrivi almeno
a quota 5 fra quote e bonus, e che sia il piu' facile possibile da incassare.

C'e' una tensione che va messa in chiaro subito, perche' decide tutto il resto.
A parita' di quota finale, **piu' gambe significa meno probabilita' di vincere**,
non di piu'. Le quote si moltiplicano, ma con loro si moltiplicano i margini del
banco. A quota 5 con margine del 5% per gamba:

    2 gambe  ->  18.1% di probabilita',  valore atteso  -9.8%
    5 gambe  ->  15.5%                                 -22.6%
    10 gambe ->  12.0%                                 -40.1%

Stessa vincita, stessa quota. Cambia solo quanto e' probabile incassarla, e
quanto costa provarci.

Il bonus multipla e' l'unica cosa che puo' invertire il conto, ed e' il motivo
per cui vale la pena tenerlo al centro. La soglia e' esatta e sorprendentemente
semplice:

    EV = bonus x prodotto(p_i x quota_i) - 1 = bonus x (1 - margine)^n - 1

quindi il bonus che pareggia i conti vale ``1 / (1 - margine)^n`` e **non
dipende dalle quote scelte**, solo dal numero di gambe e dal margine per gamba.
Con margine del 5%: +29% a cinque gambe, +51% a otto, +67% a dieci.

Da qui discendono le due cose che questo modulo fa davvero:

1. confronta il bonus del tuo conto con quella soglia, gamba per gamba, e dice
   dove il bonus vince e dove perde;
2. a parita' di obiettivo, sceglie la schedina con la probabilita' di vincita
   piu' alta, cioe' quella che spreca meno quota oltre l'obiettivo.

Un avvertimento sul vincolo nascosto: quasi tutti i bonus richiedono una quota
minima per gamba (di solito 1.20-1.30). Per arrivare a 5 con dieci gambe
servono quote da 1.175 l'una, che sotto quel minimo non si qualificano. Dieci
gambe a 1.20 portano la quota a 6.19 e la probabilita' al 9.7%. Il vincolo va
letto dalle condizioni del tuo conto e inserito in ``BonusSchedule``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from bookmaking.staking.ticket import Leg, Ticket, build_ticket

STEP = 0.005          # risoluzione della quota nella ricerca, in scala log


@dataclass
class BonusSchedule:
    """Bonus multipla del bookmaker.

    I valori vanno letti dalle condizioni del proprio conto: cambiano fra
    bookmaker, cambiano nel tempo e cambiano per campionato. Il default e'
    *nessun bonus*, di proposito: meglio un conto pessimistico che uno basato su
    numeri inventati.

    ``by_legs`` mappa il numero di gambe al moltiplicatore sulla vincita: 1.10
    significa +10%. ``min_leg_price`` e' la quota minima perche' una gamba
    conti ai fini del bonus.
    """

    by_legs: dict[int, float] = field(default_factory=dict)
    min_leg_price: float = 1.20
    min_legs: int = 2
    applies_to: str = "vincita"     # documentazione: quasi sempre sulla vincita

    def multiplier(self, n_qualifying: int) -> float:
        if n_qualifying < self.min_legs or not self.by_legs:
            return 1.0
        applicabili = [k for k in self.by_legs if k <= n_qualifying]
        if not applicabili:
            return 1.0
        return self.by_legs[max(applicabili)]

    def qualifying(self, legs: list[Leg]) -> int:
        return sum(1 for l in legs if l.price >= self.min_leg_price)

    def break_even(self, n_legs: int, margin_per_leg: float = 0.05) -> float:
        """Bonus minimo perche' una multipla di ``n_legs`` non sia in perdita.

        Dipende solo dal numero di gambe e dal margine per gamba: le quote
        scelte non c'entrano nulla.
        """
        return 1.0 / ((1.0 - margin_per_leg) ** n_legs)

    def verdict(self, max_legs: int = 10,
                margin_per_leg: float = 0.05) -> list[dict[str, float]]:
        """Dove il bonus batte il margine composto e dove no."""
        rows = []
        for n in range(self.min_legs, max_legs + 1):
            offerto = self.multiplier(n)
            soglia = self.break_even(n, margin_per_leg)
            rows.append({"gambe": n, "bonus_offerto": offerto,
                         "bonus_necessario": soglia,
                         "conviene": offerto >= soglia,
                         "scarto": offerto - soglia})
        return rows


@dataclass
class TicketPlan:
    """Una schedina candidata, con i conti gia' fatti."""

    legs: list[Leg]
    bonus: float
    target: float

    @property
    def raw_price(self) -> float:
        p = 1.0
        for l in self.legs:
            p *= l.price
        return p

    @property
    def effective_price(self) -> float:
        """Quota finale bonus incluso: e' quella che conta per l'obiettivo."""
        return self.raw_price * self.bonus

    @property
    def probability(self) -> float:
        p = 1.0
        for l in self.legs:
            p *= l.p_final
        return p

    @property
    def ev(self) -> float:
        return self.probability * self.effective_price - 1.0

    @property
    def one_in(self) -> float:
        return 1.0 / self.probability if self.probability > 0 else float("inf")

    @property
    def meets_target(self) -> bool:
        return self.effective_price >= self.target - 1e-9

    def to_ticket(self, stake: float) -> Ticket:
        return build_ticket(self.legs, stake)


def optimise(candidates: list[Leg], target: float = 5.0, max_legs: int = 10,
             bonus: BonusSchedule | None = None,
             min_legs: int = 2) -> list[TicketPlan]:
    """Per ogni numero di gambe, la schedina piu' probabile che raggiunge l'obiettivo.

    Restituisce la frontiera completa invece della sola schedina migliore: e'
    guardando come la probabilita' cala aggiungendo gambe che si capisce quanto
    costa davvero allungare la schedina.

    Al massimo una gamba per partita. Due gambe sulla stessa partita sono
    correlate, quasi nessun bookmaker le accetta in multipla, e il prodotto
    delle probabilita' sarebbe comunque sbagliato.
    """
    bonus = bonus or BonusSchedule()
    usable = [l for l in candidates if l.price > 1.0 and 0.0 < l.p_final < 1.0]
    if not usable:
        return []

    per_match: dict[str, list[Leg]] = {}
    for leg in usable:
        per_match.setdefault(leg.match_id, []).append(leg)
    groups = list(per_match.values())

    out: list[TicketPlan] = []
    for n in range(min_legs, min(max_legs, len(groups)) + 1):
        mult = bonus.multiplier(n)
        # l'obiettivo da raggiungere con le sole quote, scontato del bonus
        needed = target / mult if mult > 0 else target
        legs = _best_subset(groups, n, math.log(needed))
        if legs:
            out.append(TicketPlan(legs=legs, bonus=mult, target=target))
    return out


def _best_subset(groups: list[list[Leg]], n: int, log_target: float) -> list[Leg] | None:
    """Sceglie ``n`` gambe, al piu' una per partita, massimizzando la probabilita'.

    Programmazione dinamica su (partite esaminate, gambe usate, quota accumulata).
    La quota accumulata e' discretizzata **per difetto**: una soluzione che
    risulta sopra l'obiettivo lo e' davvero, senza sorprese da arrotondamento.

    Massimizzare la probabilita' equivale a sprecare meno quota possibile oltre
    l'obiettivo, ed e' il motivo per cui la schedina migliore tende ad avere
    poche gambe: ogni gamba in piu' e' margine del banco pagato due volte.
    """
    if n > len(groups):
        return None
    total = sum(max(math.log(l.price) for l in g) for g in groups)
    target_bucket = max(0, math.ceil(log_target / STEP))
    if target_bucket > int(total / STEP) + 1:
        return None
    cap = min(int(total / STEP) + 2, target_bucket + int(1.0 / STEP))

    NEG = -1e18
    n_groups = len(groups)
    dp = np.full((n + 1, cap + 1), NEG)
    dp[0, 0] = 0.0
    # per ogni stato: da quale secchiello veniva e quale gamba e' stata presa
    par_bucket = np.full((n_groups + 1, n + 1, cap + 1), -1, dtype=np.int32)
    par_leg = np.full((n_groups + 1, n + 1, cap + 1), -1, dtype=np.int32)

    for gi, group in enumerate(groups):
        nxt = dp.copy()
        par_bucket[gi + 1] = -1
        par_leg[gi + 1] = -1
        for legs_used in range(n):
            valid = np.where(dp[legs_used] > NEG / 2)[0]
            if valid.size == 0:
                continue
            for li, leg in enumerate(group):
                w = int(math.log(leg.price) / STEP)
                dest = np.minimum(valid + w, cap)
                cand = dp[legs_used][valid] + math.log(leg.p_final)
                for src, d, c in zip(valid, dest, cand):
                    if c > nxt[legs_used + 1, d]:
                        nxt[legs_used + 1, d] = c
                        par_bucket[gi + 1, legs_used + 1, d] = src
                        par_leg[gi + 1, legs_used + 1, d] = li
        dp = nxt

    # L'arrotondamento per difetto puo' far sembrare sotto obiettivo soluzioni
    # che in realta' lo raggiungono: si riparte da qualche secchiello piu' sotto
    # e si verifica la quota esatta, invece di scartarle.
    slack = max(0, target_bucket - n - 1)
    candidati = [b for b in range(slack, cap + 1) if dp[n, b] > NEG / 2]
    if not candidati:
        return None
    candidati.sort(key=lambda b: dp[n, b], reverse=True)

    for bucket in candidati[:64]:
        legs = _reconstruct(groups, par_leg, par_bucket, n, bucket, n_groups)
        if legs is None or len(legs) != n:
            continue
        if sum(math.log(l.price) for l in legs) >= log_target - 1e-12:
            return legs
    return None


def _reconstruct(groups: list[list[Leg]], par_leg: np.ndarray, par_bucket: np.ndarray,
                 n: int, bucket: int, n_groups: int) -> list[Leg] | None:
    legs: list[Leg] = []
    legs_used = n
    for gi in range(n_groups, 0, -1):
        li = int(par_leg[gi, legs_used, bucket])
        if li < 0:
            continue                      # questa partita non e' stata usata
        legs.append(groups[gi - 1][li])
        bucket = int(par_bucket[gi, legs_used, bucket])
        legs_used -= 1
        if legs_used == 0:
            break
    return legs if len(legs) == n else None
