"""Dimensionamento della puntata: da vantaggio stimato a euro da giocare.

Il criterio di Kelly massimizza il tasso di crescita del capitale nel lungo
periodo, ma lo fa assumendo di *conoscere* la probabilita' vera. Noi la
stimiamo, e una probabilita' stimata per eccesso produce puntate troppo grandi
proprio dove il modello sbaglia di piu'. Da qui due difese, entrambe necessarie:

1. Kelly frazionario (un quarto e' lo standard prudente): riduce di molto la
   volatilita' rinunciando a poca crescita attesa.
2. Compressione del vantaggio: il vantaggio apparente viene dimezzato prima di
   entrare nella formula, perche' l'errore di stima gonfia sistematicamente i
   vantaggi misurati (sono le selezioni dove il modello sovrastima a finire in
   cima alla lista, non quelle dove ha ragione).

Con un budget di 30 euro alla settimana e una puntata minima di 2 euro, la
granularita' e' grossolana: Kelly puo' suggerire 1,40 euro, che non e'
giocabile. In quel caso la scommessa si salta. Forzarla al minimo significhera'
sistematicamente puntare piu' del dovuto.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from bookmaking.pricing.blend import Edge


@dataclass(frozen=True)
class BankrollPolicy:
    """Regole di gestione del capitale. I default sono tarati su 30 euro/settimana.

    Va tenuta ferma la distinzione fra due numeri diversi che e' facile
    confondere:

    - ``weekly_budget`` e' quanto si e' disposti a *spendere in una settimana*.
      E' un tetto di liquidita' e di disciplina.
    - ``kelly_bankroll`` e' il capitale su cui Kelly dimensiona le puntate: il
      totale che si mette in gioco sull'orizzonte considerato. Chi versa 30 euro
      a settimana per una stagione sta rischiando circa 1.200 euro, non 30.

    Dimensionare Kelly sui 30 euro settimanali sarebbe un errore grossolano e
    con conseguenze pratiche precise: ogni puntata verrebbe calcolata come se
    una settimana storta azzerasse tutto il capitale, e finirebbe sotto la
    puntata minima giocabile. Il risultato e' un sistema che non gioca mai.
    """

    weekly_budget: float = 30.0
    season_weeks: int = 40
    kelly_bankroll: float | None = None
    kelly_fraction: float = 0.25
    edge_shrinkage: float = 0.5
    min_ev: float = 0.03           # sotto il 3% atteso non vale il rischio
    min_stake: float = 2.0
    stake_step: float = 0.50
    max_stake_pct: float = 0.20    # nessuna singola giocata oltre il 20% del budget
    max_bets_per_week: int = 8
    min_books: int = 3             # un vantaggio visto da pochi book e' sospetto
    min_price: float = 1.30
    max_price: float = 15.0

    @property
    def bankroll(self) -> float:
        """Capitale di riferimento per Kelly."""
        if self.kelly_bankroll is not None:
            return self.kelly_bankroll
        return self.weekly_budget * self.season_weeks

    @property
    def max_stake(self) -> float:
        return self.weekly_budget * self.max_stake_pct


@dataclass(frozen=True)
class StakedBet:
    edge: Edge
    stake: float
    kelly_raw: float
    kelly_used: float

    @property
    def expected_profit(self) -> float:
        return self.stake * self.edge.ev

    @property
    def potential_win(self) -> float:
        return self.stake * (self.edge.price - 1.0)


@dataclass
class StakePlan:
    bets: list[StakedBet]
    rejected: list[tuple[Edge, str]]
    budget: float
    scaled_by: float = 1.0

    @property
    def total_stake(self) -> float:
        return sum(b.stake for b in self.bets)

    @property
    def expected_profit(self) -> float:
        return sum(b.expected_profit for b in self.bets)

    @property
    def budget_left(self) -> float:
        return self.budget - self.total_stake


def _round_stake(x: float, step: float) -> float:
    return math.floor(x / step + 1e-9) * step


def shrunk_kelly(edge: Edge, policy: BankrollPolicy) -> tuple[float, float]:
    """(Kelly pieno, Kelly effettivamente usato) dopo compressione e frazionamento."""
    b = edge.price - 1.0
    if b <= 0:
        return 0.0, 0.0
    raw = (edge.p_final * edge.price - 1.0) / b
    if raw <= 0:
        return raw, 0.0
    p_shrunk = (edge.p_final * (1.0 - policy.edge_shrinkage)
                + (1.0 / edge.price) * policy.edge_shrinkage)
    shrunk = (p_shrunk * edge.price - 1.0) / b
    return raw, max(0.0, shrunk * policy.kelly_fraction)


def _reject_reason(edge: Edge, policy: BankrollPolicy) -> str | None:
    if edge.price < policy.min_price:
        return f"quota {edge.price:.2f} sotto il minimo {policy.min_price:.2f}"
    if edge.price > policy.max_price:
        return f"quota {edge.price:.2f} oltre il massimo {policy.max_price:.2f}"
    if policy.min_books and edge.n_books and edge.n_books < policy.min_books:
        return f"solo {edge.n_books} book quotano: consenso troppo debole"
    if edge.ev < policy.min_ev:
        return f"valore atteso {edge.ev * 100:.1f}% sotto la soglia {policy.min_ev * 100:.0f}%"
    return None


def plan_stakes(edges: list[Edge], policy: BankrollPolicy | None = None,
                available_budget: float | None = None) -> StakePlan:
    """Trasforma una lista di vantaggi in puntate concrete entro il budget.

    Le scommesse sono considerate in ordine di valore atteso decrescente. Se la
    somma richiesta supera il budget, le puntate vengono ridotte in proporzione
    invece di tagliare le ultime della lista: cosi' il profilo di rischio resta
    quello voluto.
    """
    policy = policy or BankrollPolicy()
    budget = policy.weekly_budget if available_budget is None else available_budget
    rejected: list[tuple[Edge, str]] = []
    candidates: list[tuple[Edge, float, float]] = []

    for edge in sorted(edges, key=lambda e: e.ev, reverse=True):
        reason = _reject_reason(edge, policy)
        if reason:
            rejected.append((edge, reason))
            continue
        raw, used = shrunk_kelly(edge, policy)
        if used <= 0:
            rejected.append((edge, "Kelly non positivo dopo la compressione"))
            continue
        candidates.append((edge, raw, used))
        if len(candidates) >= policy.max_bets_per_week:
            break

    if not candidates:
        return StakePlan(bets=[], rejected=rejected, budget=budget)

    # Kelly dimensiona sul capitale complessivo; il budget della settimana e il
    # tetto per giocata intervengono dopo, come vincoli.
    desired = [min(used * policy.bankroll, policy.max_stake) for _, _, used in candidates]
    total = sum(desired)
    scale = min(1.0, budget / total) if total > 0 else 1.0

    bets: list[StakedBet] = []
    spent = 0.0
    for (edge, raw, used), want in zip(candidates, desired):
        stake = _round_stake(want * scale, policy.stake_step)
        if stake < policy.min_stake:
            rejected.append((edge, f"puntata {want * scale:.2f} EUR sotto il minimo "
                                   f"giocabile di {policy.min_stake:.2f} EUR"))
            continue
        if spent + stake > budget + 1e-9:
            stake = _round_stake(budget - spent, policy.stake_step)
            if stake < policy.min_stake:
                rejected.append((edge, "budget settimanale esaurito"))
                continue
        bets.append(StakedBet(edge=edge, stake=stake, kelly_raw=raw, kelly_used=used))
        spent += stake

    return StakePlan(bets=bets, rejected=rejected, budget=budget, scaled_by=scale)
