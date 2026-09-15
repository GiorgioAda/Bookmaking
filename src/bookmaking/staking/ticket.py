"""Costruzione della giocata a partire dalle partite selezionate.

Due cose che la schedina nasconde e che qui vengono rese esplicite.

La prima riguarda le multiple. Moltiplicando le quote si moltiplicano anche i
margini: tre gambe al 5% di margine ciascuna non fanno una giocata al 5%, ne
fanno una intorno al 16%. Una multipla conviene solo se *ogni* gamba ha valore
atteso positivo da sola, e anche allora aumenta enormemente la varianza. Il
confronto con le singole equivalenti viene calcolato e mostrato, non lasciato
all'intuito.

La seconda riguarda la correlazione. Due gambe sulla stessa partita (per dire
"1" e "Over 2.5") non sono indipendenti, e moltiplicare le loro probabilita' da'
un numero sbagliato, di solito troppo basso. Avendo la matrice congiunta dei
punteggi possiamo intersecare gli eventi sul serio. Fra partite diverse
l'indipendenza e' invece un'assunzione accettabile.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bookmaking.model.markets import selection_mask
from bookmaking.pricing.blend import Edge
from bookmaking.staking.kelly import BankrollPolicy


@dataclass(frozen=True)
class Leg:
    """Una gamba della giocata, agganciata alla partita da cui proviene."""

    match_id: str
    label: str              # es. "Inter - Milan"
    market: str
    selection: str
    bookmaker: str
    price: float
    p_final: float
    score_matrix: np.ndarray | None = None   # necessaria per le gambe correlate

    def as_edge(self) -> Edge:
        return Edge(market=self.market, selection=self.selection,
                    bookmaker=self.bookmaker, price=self.price,
                    p_model=self.p_final, p_market=1.0 / self.price,
                    p_final=self.p_final)


def combo_probability(legs: list[Leg]) -> float:
    """Probabilita' che tutte le gambe si verifichino.

    Le gambe sulla stessa partita vengono intersecate sulla matrice congiunta
    dei punteggi; fra partite diverse si moltiplica.
    """
    if not legs:
        return 0.0
    by_match: dict[str, list[Leg]] = {}
    for leg in legs:
        by_match.setdefault(leg.match_id, []).append(leg)

    total = 1.0
    for match_legs in by_match.values():
        if len(match_legs) == 1:
            total *= match_legs[0].p_final
            continue
        matrices = [l.score_matrix for l in match_legs]
        if any(m is None for m in matrices):
            # Senza congiunta non si puo' fare di meglio che moltiplicare, ma il
            # risultato e' distorto: chi chiama viene avvisato da build_ticket.
            for leg in match_legs:
                total *= leg.p_final
            continue
        m = matrices[0]
        mask = np.ones(m.shape, dtype=bool)
        for leg in match_legs:
            mask &= selection_mask(m, leg.market, leg.selection)
        total *= float(m[mask].sum())
    return total


@dataclass
class Ticket:
    """Una giocata proposta, con i conti in chiaro."""

    legs: list[Leg]
    stake: float
    probability: float
    warnings: list[str] = field(default_factory=list)

    @property
    def price(self) -> float:
        p = 1.0
        for leg in self.legs:
            p *= leg.price
        return p

    @property
    def potential_return(self) -> float:
        return self.stake * self.price

    @property
    def ev(self) -> float:
        """Valore atteso per euro puntato."""
        return self.probability * self.price - 1.0

    @property
    def expected_profit(self) -> float:
        return self.stake * self.ev

    @property
    def is_multiple(self) -> bool:
        return len(self.legs) > 1

    @property
    def independent_probability(self) -> float:
        p = 1.0
        for leg in self.legs:
            p *= leg.p_final
        return p


def singles_comparison(legs: list[Leg], total_stake: float) -> dict[str, float]:
    """Le stesse gambe giocate come singole, a parita' di capitale impegnato."""
    if not legs:
        return {"valore_atteso": 0.0, "profitto_atteso": 0.0}
    per_leg = total_stake / len(legs)
    ev = sum(per_leg * (leg.p_final * leg.price - 1.0) for leg in legs)
    return {"valore_atteso": ev / total_stake if total_stake else 0.0,
            "profitto_atteso": ev}


def build_ticket(legs: list[Leg], stake: float,
                 policy: BankrollPolicy | None = None) -> Ticket:
    """Costruisce la giocata e annota tutto cio' che l'utente deve sapere prima di giocarla."""
    policy = policy or BankrollPolicy()
    warnings: list[str] = []

    by_match: dict[str, list[Leg]] = {}
    for leg in legs:
        by_match.setdefault(leg.match_id, []).append(leg)
    for match_id, match_legs in by_match.items():
        if len(match_legs) > 1 and any(l.score_matrix is None for l in match_legs):
            warnings.append(
                f"{match_legs[0].label}: piu' gambe sulla stessa partita senza matrice "
                "congiunta, la probabilita' e' approssimata per difetto")

    prob = combo_probability(legs)
    ticket = Ticket(legs=legs, stake=stake, probability=prob, warnings=warnings)

    if ticket.is_multiple:
        singles = singles_comparison(legs, stake)
        if singles["profitto_atteso"] > ticket.expected_profit:
            warnings.append(
                f"giocate come singole le stesse selezioni rendono "
                f"{singles['profitto_atteso']:.2f} EUR attesi contro "
                f"{ticket.expected_profit:.2f} EUR della multipla")
        negative = [l for l in legs if l.p_final * l.price - 1.0 < 0]
        if negative:
            warnings.append(
                f"{len(negative)} gamb{'a' if len(negative) == 1 else 'e'} su "
                f"{len(legs)} ha valore atteso negativo da sola: trascina giu' "
                "tutta la multipla")
        if prob < 0.10:
            warnings.append(
                f"probabilita' di vincita {prob * 100:.1f}%: in media una giocata "
                f"vincente ogni {1 / prob:.0f} tentativi")

    if stake > policy.max_stake:
        warnings.append(f"puntata di {stake:.2f} EUR oltre il tetto per giocata "
                        f"({policy.max_stake:.2f} EUR)")
    if ticket.ev < 0:
        warnings.append(f"valore atteso negativo ({ticket.ev * 100:.1f}%): "
                        "secondo il modello questa giocata perde nel lungo periodo")
    return ticket
