"""Il punto in cui tutti i pezzi si incontrano.

Il percorso di una giocata, dall'inizio alla fine:

    storico  ->  modello  ->  probabilita' del modello
    quote    ->  devig    ->  probabilita' di mercato
                     \\        /
                      fusione (il modello prevale)
                          |
                    confronto con la quota piu' alta disponibile
                          |
                    vantaggio -> Kelly compresso -> puntata

Il passaggio piu' importante e' l'ultimo confronto: la probabilita' si stima sul
*consenso* di tutti i book, ma si gioca sulla *quota migliore* fra quelli dove
hai un conto. Il vantaggio nasce in buona parte proprio da questa asimmetria, e
non richiede che il modello sia piu' bravo del mercato: basta che il mercato non
sia unanime.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from bookmaking.domain import Match, MatchOdds
from bookmaking.model.dixon_coles import DixonColesFit
from bookmaking.model.markets import all_markets, outcome_1x2
from bookmaking.pricing.blend import DEFAULT_MODEL_WEIGHT, Edge, blend_probabilities
from bookmaking.pricing.consensus import (BookWeights, ITALIAN_BOOKS,
                                          consensus_probabilities)
from bookmaking.pricing.devig import DevigMethod
from bookmaking.staking.kelly import BankrollPolicy, StakePlan, plan_stakes
from bookmaking.staking.schedina import BonusSchedule, TicketPlan, optimise
from bookmaking.staking.ticket import Leg, Ticket, build_ticket


@dataclass
class MatchAnalysis:
    """Tutto cio' che il sistema sa di una partita, pronto per essere mostrato."""

    match: Match
    score_matrix: np.ndarray
    model_probs: dict[str, dict[str, float]]
    market_probs: dict[str, dict[str, float]]
    edges: list[Edge]
    n_books: int

    @property
    def probabilities_1x2(self) -> dict[str, float]:
        return self.model_probs.get("1X2", {})

    @property
    def expected_goals(self) -> tuple[float, float]:
        n = self.score_matrix.shape[0]
        gx = np.arange(n)
        return (float((self.score_matrix.sum(axis=1) * gx).sum()),
                float((self.score_matrix.sum(axis=0) * gx).sum()))

    @property
    def best_edge(self) -> Edge | None:
        return self.edges[0] if self.edges else None


@dataclass(frozen=True)
class Candidate:
    """Una selezione da andare a controllare sul proprio bookmaker.

    ``required_price`` e' il punto di tutto: la quota minima oltre la quale la
    selezione diventa conveniente. Trasforma la domanda "quanto vale questa
    partita?", che richiede il sistema davanti, nella domanda "la quota
    sull'app supera 2.45?", a cui si risponde in un secondo.
    """

    match: Match
    market: str
    selection: str
    p_final: float
    required_price: float
    best_feed_price: float | None
    best_feed_book: str | None
    n_books: int

    @property
    def fair_price(self) -> float:
        return 1.0 / self.p_final if self.p_final > 0 else float("inf")

    @property
    def already_playable(self) -> bool:
        return (self.best_feed_price or 0.0) >= self.required_price

    @property
    def label(self) -> str:
        return f"{self.match.home} - {self.match.away}"


@dataclass
class Advisor:
    """Consulente: dal modello stimato alle giocate consigliate."""

    fit: DixonColesFit
    policy: BankrollPolicy = field(default_factory=BankrollPolicy)
    weights: BookWeights = field(default_factory=BookWeights)
    model_weight: float = DEFAULT_MODEL_WEIGHT
    devig_method: DevigMethod = DevigMethod.SHIN
    playable_books: frozenset[str] = ITALIAN_BOOKS

    def analyse(self, match: Match, odds: MatchOdds | None = None,
                markets: tuple[str, ...] = ("1X2",)) -> MatchAnalysis:
        """Analizza una partita: probabilita' del modello, del mercato, e vantaggi."""
        matrix = self.fit.score_matrix(match.home, match.away, match.division)
        model_probs = all_markets(matrix)
        market_probs: dict[str, dict[str, float]] = {}
        edges: list[Edge] = []
        n_books = 0

        if odds is not None:
            for market in markets:
                quotes = odds.for_market(market)
                if not quotes or market not in model_probs:
                    continue
                n_books = max(n_books, len(quotes))
                try:
                    consensus = consensus_probabilities(
                        quotes, self.weights, self.devig_method)
                except ValueError:
                    continue
                market_probs[market] = consensus
                edges.extend(self._edges_for(market, model_probs[market],
                                             consensus, odds, len(quotes), match))

        edges.sort(key=lambda e: e.ev, reverse=True)
        return MatchAnalysis(match=match, score_matrix=matrix, model_probs=model_probs,
                             market_probs=market_probs, edges=edges, n_books=n_books)

    def _edges_for(self, market: str, model: dict[str, float],
                   consensus: dict[str, float], odds: MatchOdds,
                   n_books: int, match: Match | None = None) -> list[Edge]:
        final = blend_probabilities(model, consensus, self.model_weight)
        out: list[Edge] = []
        for selection, p_final in final.items():
            best = self._best_playable(odds, market, selection)
            if best is None:
                continue
            book, price = best
            out.append(Edge(market=market, selection=selection, bookmaker=book,
                            price=price, p_model=model.get(selection, 0.0),
                            p_market=consensus.get(selection, 0.0),
                            p_final=p_final, n_books=n_books,
                            match_id=(match.match_id or "") if match else "",
                            label=f"{match.home} - {match.away}" if match else ""))
        return out

    def _best_playable(self, odds: MatchOdds, market: str,
                       selection: str) -> tuple[str, float] | None:
        best: tuple[str, float] | None = None
        for q in odds.for_market(market):
            if q.bookmaker.lower() not in self.playable_books:
                continue
            price = q.prices.get(selection)
            if price is None:
                continue
            if best is None or price > best[1]:
                best = (q.bookmaker, price)
        return best

    def weekly_plan(self, fixtures: list[Match], odds: dict[str, MatchOdds],
                    markets: tuple[str, ...] = ("1X2",),
                    available_budget: float | None = None
                    ) -> tuple[StakePlan, list[MatchAnalysis]]:
        """Il piano della settimana: quali partite, quale mercato, quanto puntare."""
        analyses: list[MatchAnalysis] = []
        all_edges: list[Edge] = []
        for fixture in fixtures:
            key = fixture.match_id or ""
            analysis = self.analyse(fixture, odds.get(key), markets)
            analyses.append(analysis)
            all_edges.extend(analysis.edges)
        plan = plan_stakes(all_edges, self.policy, available_budget)
        return plan, analyses

    def shortlist(self, fixtures: list[Match], odds: dict[str, MatchOdds],
                  markets: tuple[str, ...] = ("1X2",),
                  top_n: int = 12) -> list[Candidate]:
        """Le selezioni da controllare sul proprio bookmaker, con la soglia di convenienza.

        E' il passaggio che rende praticabile un book senza feed: invece di
        battere a mano l'intero palinsesto, si controllano solo le poche
        selezioni che il modello ritiene sottovalutate dal mercato, sapendo gia'
        a quale quota vale la pena giocarle.
        """
        out: list[Candidate] = []
        soglia = 1.0 + self.policy.min_ev
        for fixture in fixtures:
            analysis = self.analyse(fixture, odds.get(fixture.match_id or ""), markets)
            for market in markets:
                final = analysis.model_probs.get(market)
                if final is None:
                    continue
                if market in analysis.market_probs:
                    final = blend_probabilities(final, analysis.market_probs[market],
                                                self.model_weight)
                for selection, p in final.items():
                    if p <= 0:
                        continue
                    best = None
                    mo = odds.get(fixture.match_id or "")
                    if mo is not None:
                        best = mo.best_price(market, selection)
                    out.append(Candidate(
                        match=fixture, market=market, selection=selection, p_final=p,
                        required_price=soglia / p,
                        best_feed_price=best[1] if best else None,
                        best_feed_book=best[0] if best else None,
                        n_books=analysis.n_books))

        # in cima quelle dove il mercato e' gia' vicino alla soglia: sono le piu'
        # probabili da trovare giocabili anche altrove
        def vicinanza(c: Candidate) -> float:
            if c.best_feed_price is None:
                return 0.0
            return c.best_feed_price / c.required_price

        out.sort(key=vicinanza, reverse=True)
        return out[:top_n]

    def candidate_legs(self, fixtures: list[Match], odds: dict[str, MatchOdds],
                       markets: tuple[str, ...] = ("1X2",),
                       min_price: float = 1.10,
                       max_price: float = 8.0) -> list[Leg]:
        """Tutte le selezioni giocabili delle partite date, con la probabilita' fusa.

        E' il materiale grezzo da cui si costruisce una schedina a quota
        obiettivo: una gamba per ogni selezione che un book giocabile quota.
        """
        legs: list[Leg] = []
        for fixture in fixtures:
            mo = odds.get(fixture.match_id or "")
            analysis = self.analyse(fixture, mo, markets)
            for market in markets:
                probs = analysis.model_probs.get(market)
                if probs is None:
                    continue
                if market in analysis.market_probs:
                    probs = blend_probabilities(probs, analysis.market_probs[market],
                                                self.model_weight)
                for selection, p in probs.items():
                    if mo is None or p <= 0:
                        continue
                    best = self._best_playable(mo, market, selection)
                    if best is None:
                        continue
                    book, price = best
                    if not (min_price <= price <= max_price):
                        continue
                    legs.append(Leg(
                        match_id=fixture.match_id or f"{fixture.home}-{fixture.away}",
                        label=f"{fixture.home} - {fixture.away}", market=market,
                        selection=selection, bookmaker=book, price=price,
                        p_final=p, score_matrix=analysis.score_matrix))
        return legs

    def target_tickets(self, fixtures: list[Match], odds: dict[str, MatchOdds],
                       target: float = 5.0, max_legs: int = 10,
                       bonus: BonusSchedule | None = None,
                       markets: tuple[str, ...] = ("1X2",)) -> list[TicketPlan]:
        """Schedine che raggiungono la quota obiettivo, una per numero di gambe.

        Restituisce la frontiera intera e non la sola migliore: e' vedendo come
        cala la probabilita' aggiungendo gambe che si capisce quanto costa
        allungare la schedina, e se il bonus lo ripaga.
        """
        legs = self.candidate_legs(fixtures, odds, markets)
        return optimise(legs, target=target, max_legs=max_legs, bonus=bonus)

    def build_ticket_from(self, picks: list[tuple[Match, str, str]],
                          odds: dict[str, MatchOdds], stake: float) -> Ticket:
        """Costruisce la schedina dalle partite che l'utente ha selezionato.

        ``picks`` e' una lista di (partita, mercato, selezione): e' esattamente
        quello che arriva dai pochi tocchi sull'app.
        """
        legs: list[Leg] = []
        for match, market, selection in picks:
            analysis = self.analyse(match, odds.get(match.match_id or ""), (market,))
            blended = analysis.model_probs.get(market, {})
            if market in analysis.market_probs:
                blended = blend_probabilities(blended, analysis.market_probs[market],
                                              self.model_weight)
            p = blended.get(selection)
            if p is None:
                raise ValueError(f"selezione sconosciuta: {market} / {selection}")
            best = self._best_playable(odds.get(match.match_id or "",
                                                MatchOdds(match.match_id or "")),
                                       market, selection)
            if best is None:
                raise ValueError(
                    f"nessun bookmaker giocabile quota {selection} su "
                    f"{match.home}-{match.away}")
            book, price = best
            legs.append(Leg(match_id=match.match_id or f"{match.home}-{match.away}",
                            label=f"{match.home} - {match.away}", market=market,
                            selection=selection, bookmaker=book, price=price,
                            p_final=p, score_matrix=analysis.score_matrix))
        return build_ticket(legs, stake, self.policy)
