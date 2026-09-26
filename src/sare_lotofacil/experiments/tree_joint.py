from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers

UNIVERSE_SIZE = 25
CARD_SIZE = 15


def _logaddexp(a: float, b: float) -> float:
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    high = max(a, b)
    low = min(a, b)
    return high + math.log1p(math.exp(low - high))


def _mutual_information(joint: tuple[tuple[float, float], tuple[float, float]]) -> float:
    row = [sum(joint[x][y] for y in (0, 1)) for x in (0, 1)]
    col = [sum(joint[x][y] for x in (0, 1)) for y in (0, 1)]
    value = 0.0
    for x in (0, 1):
        for y in (0, 1):
            p = joint[x][y]
            if p > 0.0:
                value += p * math.log(p / (row[x] * col[y]))
    return value


@dataclass(frozen=True, slots=True)
class TreeJointScore:
    card: tuple[int, ...]
    log_probability: float
    log_loss: float
    probability: float


@dataclass(frozen=True, slots=True)
class TreeConditionalSubsetModel:
    """Tree-structured binary graphical model conditioned on exactly 15 ones.

    The unconditioned distribution is a Chow-Liu-style directed tree:

        P(x) = P(x_root) * product P(x_child | x_parent).

    Conditioning on sum(x)=15 yields a proper joint distribution on the exact
    Lotofacil state space.  Both the fixed-cardinality normalizer and MAP card
    are solved exactly by tree dynamic programming.
    """

    root: int
    parent: tuple[int, ...]
    children: tuple[tuple[int, ...], ...]
    root_log_prob: tuple[float, float]
    conditional_log_prob: tuple[tuple[tuple[float, float], tuple[float, float]], ...]
    source: str = "P15_H103_TREE_PAIRWISE"

    def _subtree_log_partition(self) -> list[list[list[float]]]:
        tables: list[list[list[float]] | None] = [None] * UNIVERSE_SIZE

        def visit(node: int) -> list[list[float]]:
            # table[state][count] = log mass inside subtree excluding edge from parent.
            table = [[-math.inf] * (CARD_SIZE + 1) for _ in (0, 1)]
            table[0][0] = 0.0
            table[1][1] = 0.0
            for child in self.children[node]:
                child_table = visit(child)
                merged = [[-math.inf] * (CARD_SIZE + 1) for _ in (0, 1)]
                for state in (0, 1):
                    for own_count in range(CARD_SIZE + 1):
                        base = table[state][own_count]
                        if base == -math.inf:
                            continue
                        for child_state in (0, 1):
                            edge = self.conditional_log_prob[child][state][child_state]
                            for child_count in range(CARD_SIZE - own_count + 1):
                                child_mass = child_table[child_state][child_count]
                                if child_mass == -math.inf:
                                    continue
                                total = own_count + child_count
                                merged[state][total] = _logaddexp(
                                    merged[state][total],
                                    base + edge + child_mass,
                                )
                table = merged
            tables[node] = table
            return table

        visit(self.root)
        return [table for table in tables if table is not None]

    @property
    def log_cardinality_mass(self) -> float:
        tables = self._subtree_log_partition()
        root_table = tables[self.root]
        value = -math.inf
        for root_state in (0, 1):
            value = _logaddexp(
                value,
                self.root_log_prob[root_state] + root_table[root_state][CARD_SIZE],
            )
        return value

    def unconditioned_log_probability(self, card: Iterable[int]) -> float:
        normalized = normalize_numbers(card)
        selected = set(normalized)
        state = [1 if index + 1 in selected else 0 for index in range(UNIVERSE_SIZE)]
        value = self.root_log_prob[state[self.root]]
        for node in range(UNIVERSE_SIZE):
            if node == self.root:
                continue
            parent = self.parent[node]
            value += self.conditional_log_prob[node][state[parent]][state[node]]
        return value

    def card_log_probability(self, card: Iterable[int]) -> float:
        return self.unconditioned_log_probability(card) - self.log_cardinality_mass

    def score_card(self, card: Iterable[int]) -> TreeJointScore:
        normalized = normalize_numbers(card)
        log_probability = self.card_log_probability(normalized)
        return TreeJointScore(
            card=normalized,
            log_probability=log_probability,
            log_loss=-log_probability,
            probability=math.exp(log_probability),
        )

    def map_card(self) -> tuple[int, ...]:
        memo: dict[int, tuple[list[list[float]], list[list[list[tuple[int, int, int] | None]]]]] = {}

        def solve(node: int):
            # scores[state][count]
            scores = [[-math.inf] * (CARD_SIZE + 1) for _ in (0, 1)]
            scores[0][0] = 0.0
            scores[1][1] = 0.0
            decisions: list[list[list[tuple[int, int, int] | None]]] = []

            for child in self.children[node]:
                child_scores, _ = solve(child)
                merged = [[-math.inf] * (CARD_SIZE + 1) for _ in (0, 1)]
                decision_for_child = [[None] * (CARD_SIZE + 1) for _ in (0, 1)]
                for state in (0, 1):
                    for own_count in range(CARD_SIZE + 1):
                        base = scores[state][own_count]
                        if base == -math.inf:
                            continue
                        for child_state in (0, 1):
                            edge = self.conditional_log_prob[child][state][child_state]
                            for child_count in range(CARD_SIZE - own_count + 1):
                                child_value = child_scores[child_state][child_count]
                                if child_value == -math.inf:
                                    continue
                                total = own_count + child_count
                                candidate = base + edge + child_value
                                if candidate > merged[state][total]:
                                    merged[state][total] = candidate
                                    decision_for_child[state][total] = (own_count, child_state, child_count)
                scores = merged
                decisions.append(decision_for_child)
            memo[node] = (scores, decisions)
            return scores, decisions

        root_scores, _ = solve(self.root)
        root_state = max(
            (0, 1),
            key=lambda state: self.root_log_prob[state] + root_scores[state][CARD_SIZE],
        )

        selected: list[int] = []

        def reconstruct(node: int, state: int, count: int) -> None:
            if state == 1:
                selected.append(node + 1)
            _, decisions = memo[node]
            current_count = count
            # reverse through child merges to recover each child's state/count.
            child_assignments: list[tuple[int, int, int]] = []
            for child_index in range(len(self.children[node]) - 1, -1, -1):
                decision = decisions[child_index][state][current_count]
                if decision is None:
                    raise RuntimeError("P15_TREE_MAP_RECONSTRUCTION_FAILED")
                previous_count, child_state, child_count = decision
                child_assignments.append((self.children[node][child_index], child_state, child_count))
                current_count = previous_count
            for child, child_state, child_count in reversed(child_assignments):
                reconstruct(child, child_state, child_count)

        reconstruct(self.root, root_state, CARD_SIZE)
        if len(selected) != CARD_SIZE:
            raise RuntimeError("P15_TREE_MAP_CARDINALITY_FAILED")
        return tuple(sorted(selected))

    def map_score(self) -> TreeJointScore:
        return self.score_card(self.map_card())


def fit_tree_joint_from_counts(
    *,
    n: int,
    one_counts: Sequence[int],
    pair11_counts: Sequence[Sequence[int]],
    prior_strength: float = 20.0,
    prior_inclusion: float = 0.6,
) -> TreeConditionalSubsetModel:
    if n <= 0:
        raise ValueError("n deve ser positivo")
    if len(one_counts) != UNIVERSE_SIZE or len(pair11_counts) != UNIVERSE_SIZE:
        raise ValueError("contadores devem cobrir 25 dezenas")
    if prior_strength <= 0:
        raise ValueError("prior_strength deve ser positivo")
    if not 0.0 < prior_inclusion < 1.0:
        raise ValueError("prior_inclusion deve estar em (0,1)")

    p0 = prior_inclusion
    prior_cells = {
        (1, 1): prior_strength * p0 * p0,
        (1, 0): prior_strength * p0 * (1.0 - p0),
        (0, 1): prior_strength * (1.0 - p0) * p0,
        (0, 0): prior_strength * (1.0 - p0) * (1.0 - p0),
    }

    smoothed_joint: dict[tuple[int, int], tuple[tuple[float, float], tuple[float, float]]] = {}
    mi = [[0.0] * UNIVERSE_SIZE for _ in range(UNIVERSE_SIZE)]
    denom = n + prior_strength

    for i in range(UNIVERSE_SIZE):
        if len(pair11_counts[i]) != UNIVERSE_SIZE:
            raise ValueError("matriz pair11 inválida")
        for j in range(i + 1, UNIVERSE_SIZE):
            c11 = int(pair11_counts[i][j])
            c10 = int(one_counts[i]) - c11
            c01 = int(one_counts[j]) - c11
            c00 = n - c11 - c10 - c01
            counts = {(1, 1): c11, (1, 0): c10, (0, 1): c01, (0, 0): c00}
            joint = (
                (
                    (counts[(0, 0)] + prior_cells[(0, 0)]) / denom,
                    (counts[(0, 1)] + prior_cells[(0, 1)]) / denom,
                ),
                (
                    (counts[(1, 0)] + prior_cells[(1, 0)]) / denom,
                    (counts[(1, 1)] + prior_cells[(1, 1)]) / denom,
                ),
            )
            smoothed_joint[(i, j)] = joint
            value = _mutual_information(joint)
            mi[i][j] = mi[j][i] = value

    # Deterministic maximum spanning tree (Prim).
    root = 0
    in_tree = {root}
    parent = [-1] * UNIVERSE_SIZE
    while len(in_tree) < UNIVERSE_SIZE:
        best: tuple[float, int, int] | None = None
        for i in sorted(in_tree):
            for j in range(UNIVERSE_SIZE):
                if j in in_tree:
                    continue
                candidate = (mi[i][j], -i, -j)
                if best is None or candidate > best:
                    best = candidate
                    best_edge = (i, j)
        if best is None:
            raise RuntimeError("P15_TREE_BUILD_FAILED")
        i, j = best_edge
        parent[j] = i
        in_tree.add(j)

    children_lists: list[list[int]] = [[] for _ in range(UNIVERSE_SIZE)]
    for node in range(UNIVERSE_SIZE):
        if node != root:
            children_lists[parent[node]].append(node)
    children = tuple(tuple(sorted(items)) for items in children_lists)

    root_p1 = (int(one_counts[root]) + prior_strength * p0) / denom
    root_log_prob = (math.log1p(-root_p1), math.log(root_p1))

    default = (((0.0, 0.0), (0.0, 0.0)))
    conditionals: list[tuple[tuple[float, float], tuple[float, float]]] = [default] * UNIVERSE_SIZE
    for child in range(UNIVERSE_SIZE):
        if child == root:
            conditionals[child] = ((0.0, 0.0), (0.0, 0.0))
            continue
        par = parent[child]
        i, j = sorted((par, child))
        joint = smoothed_joint[(i, j)]
        # joint is indexed by state of i then state of j. Orient to parent -> child.
        probs = [[0.0, 0.0], [0.0, 0.0]]
        for par_state in (0, 1):
            row_values = []
            for child_state in (0, 1):
                if par == i:
                    value = joint[par_state][child_state]
                else:
                    value = joint[child_state][par_state]
                row_values.append(value)
            row_sum = sum(row_values)
            probs[par_state][0] = row_values[0] / row_sum
            probs[par_state][1] = row_values[1] / row_sum
        conditionals[child] = (
            (math.log(probs[0][0]), math.log(probs[0][1])),
            (math.log(probs[1][0]), math.log(probs[1][1])),
        )

    return TreeConditionalSubsetModel(
        root=root,
        parent=tuple(parent),
        children=children,
        root_log_prob=root_log_prob,
        conditional_log_prob=tuple(conditionals),
    )


def counts_from_draws(draws: Sequence[Iterable[int]]) -> tuple[list[int], list[list[int]]]:
    one_counts = [0] * UNIVERSE_SIZE
    pair11_counts = [[0] * UNIVERSE_SIZE for _ in range(UNIVERSE_SIZE)]
    for raw_draw in draws:
        draw = normalize_numbers(raw_draw)
        indices = [number - 1 for number in draw]
        for i in indices:
            one_counts[i] += 1
        for a_pos in range(len(indices)):
            i = indices[a_pos]
            for b_pos in range(a_pos + 1, len(indices)):
                j = indices[b_pos]
                pair11_counts[i][j] += 1
                pair11_counts[j][i] += 1
    return one_counts, pair11_counts


def fit_tree_joint(
    draws: Sequence[Iterable[int]],
    *,
    prior_strength: float = 20.0,
    prior_inclusion: float = 0.6,
) -> TreeConditionalSubsetModel:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    one_counts, pair11_counts = counts_from_draws(normalized)
    return fit_tree_joint_from_counts(
        n=len(normalized),
        one_counts=one_counts,
        pair11_counts=pair11_counts,
        prior_strength=prior_strength,
        prior_inclusion=prior_inclusion,
    )
