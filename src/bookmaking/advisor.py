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
