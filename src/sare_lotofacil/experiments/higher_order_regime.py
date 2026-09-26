from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from itertools import combinations
from math import comb
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers

UNIVERSE_SIZE = 25
CARD_SIZE = 15
BLOCK_SIZE = 5
BLOCK_COUNT = 5
PATTERN_COUNT = 1 << BLOCK_SIZE
TOTAL_SIMPLE_CARDS = comb(UNIVERSE_SIZE, CARD_SIZE)


def _logaddexp(a: float, b: float) -> float:
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    high = max(a, b)
    low = min(a, b)
    return high + math.log1p(math.exp(low - high))


def _mutual_information(joint: tuple[tuple[float, float], tuple[float, float]]) -> float:
    rows = [sum(joint[x][y] for y in (0, 1)) for x in (0, 1)]
    cols = [sum(joint[x][y] for x in (0, 1)) for y in (0, 1)]
    value = 0.0
    for x in (0, 1):
        for y in (0, 1):
            p = joint[x][y]
            if p > 0.0:
                value += p * math.log(p / (rows[x] * cols[y]))
    return value


def _validate_blocks(blocks: Sequence[Sequence[int]]) -> tuple[tuple[int, ...], ...]:
    normalized = tuple(tuple(int(number) for number in block) for block in blocks)
    if len(normalized) != BLOCK_COUNT:
        raise ValueError(f"são necessários {BLOCK_COUNT} blocos")
    if any(len(block) != BLOCK_SIZE for block in normalized):
        raise ValueError(f"cada bloco deve conter {BLOCK_SIZE} dezenas")
    flattened = [number for block in normalized for number in block]
    if sorted(flattened) != list(range(1, UNIVERSE_SIZE + 1)):
        raise ValueError("os blocos devem particionar exatamente as dezenas 1..25")
    return tuple(tuple(sorted(block)) for block in normalized)


def _encode_pattern(selected: set[int], block: Sequence[int]) -> int:
    pattern = 0
    for bit, number in enumerate(block):
        if number in selected:
            pattern |= 1 << bit
    return pattern


def pattern_counts_from_draws(
    draws: Sequence[Iterable[int]],
    blocks: Sequence[Sequence[int]],
) -> list[list[int]]:
    normalized_blocks = _validate_blocks(blocks)
    counts = [[0] * PATTERN_COUNT for _ in range(BLOCK_COUNT)]
    for raw_draw in draws:
        draw = normalize_numbers(raw_draw)
        selected = set(draw)
        for block_index, block in enumerate(normalized_blocks):
            counts[block_index][_encode_pattern(selected, block)] += 1
    return counts


def learn_information_blocks(
    draws: Sequence[Iterable[int]],
    *,
    smoothing: float = 1.0,
) -> tuple[tuple[int, ...], ...]:
    """Learn five disjoint 5-number blocks from past-only pairwise information.

    The blocks define a low-treewidth factorization.  Inside each block the
    model learns the complete 5-bit pattern distribution, which includes all
    pair, triple, quadruple and fifth-order interactions within that block.
    The partition is deterministic and must be frozen before scoring targets.
    """

    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if not normalized:
        raise ValueError("é necessário histórico para aprender os blocos")
    if smoothing <= 0.0:
        raise ValueError("smoothing deve ser positivo")

    n = len(normalized)
    ones = [0] * UNIVERSE_SIZE
    pair11 = [[0] * UNIVERSE_SIZE for _ in range(UNIVERSE_SIZE)]
    for draw in normalized:
        indices = [number - 1 for number in draw]
        for i in indices:
            ones[i] += 1
        for pos, i in enumerate(indices):
            for j in indices[pos + 1 :]:
                pair11[i][j] += 1
                pair11[j][i] += 1

    mi = [[0.0] * UNIVERSE_SIZE for _ in range(UNIVERSE_SIZE)]
    for i in range(UNIVERSE_SIZE):
        for j in range(i + 1, UNIVERSE_SIZE):
            c11 = pair11[i][j]
            c10 = ones[i] - c11
            c01 = ones[j] - c11
            c00 = n - c11 - c10 - c01
            raw = ((c00, c01), (c10, c11))
            denom = n + 4.0 * smoothing
            joint = (
                ((raw[0][0] + smoothing) / denom, (raw[0][1] + smoothing) / denom),
                ((raw[1][0] + smoothing) / denom, (raw[1][1] + smoothing) / denom),
            )
            value = _mutual_information(joint)
            mi[i][j] = mi[j][i] = value

    remaining = set(range(UNIVERSE_SIZE))
    groups: list[tuple[int, ...]] = []
    while remaining:
        ordered = sorted(remaining)
        if len(ordered) <= BLOCK_SIZE:
            groups.append(tuple(index + 1 for index in ordered))
            break

        best_pair: tuple[float, int, int] | None = None
        seed = (ordered[0], ordered[1])
        for a_pos, i in enumerate(ordered):
            for j in ordered[a_pos + 1 :]:
                candidate = (mi[i][j], -i, -j)
                if best_pair is None or candidate > best_pair:
                    best_pair = candidate
                    seed = (i, j)

        group = [seed[0], seed[1]]
        while len(group) < BLOCK_SIZE:
            candidates = [index for index in ordered if index not in group]
            chosen = max(
                candidates,
                key=lambda index: (sum(mi[index][member] for member in group), -index),
            )
            group.append(chosen)

        for index in group:
            remaining.remove(index)
        groups.append(tuple(sorted(index + 1 for index in group)))

    return _validate_blocks(groups)


@dataclass(frozen=True, slots=True)
class HigherOrderCardScore:
    card: tuple[int, ...]
    log_probability: float
    log_loss: float
    probability: float


@dataclass(frozen=True, slots=True)
class FullSpaceRanking:
    evaluated_cards: int
    top_cards: tuple[HigherOrderCardScore, ...]
    observed_card: tuple[int, ...] | None
    observed_rank: int | None


@dataclass(frozen=True, slots=True)
class BlockPatternConditionalModel:
    """Exact fixed-cardinality joint model with complete within-block factors.

    The 25 numbers are partitioned into five blocks of five.  Each block stores
    a proper probability over all 32 binary patterns.  The product distribution
    is then conditioned on exactly 15 selected numbers.  This yields a proper
    distribution over all 3,268,760 Lotofácil simple cards while preserving
    higher-order interactions up to order five inside every block.
    """

    blocks: tuple[tuple[int, ...], ...]
    local_log_prob: tuple[tuple[float, ...], ...]
    source: str = "P15_H104_HIGHER_ORDER_BLOCK_FACTOR"

    def __post_init__(self) -> None:
        _validate_blocks(self.blocks)
        if len(self.local_log_prob) != BLOCK_COUNT:
            raise ValueError("probabilidades locais incompletas")
        for values in self.local_log_prob:
            if len(values) != PATTERN_COUNT:
                raise ValueError("cada bloco deve possuir 32 padrões")
            if not all(math.isfinite(float(value)) for value in values):
                raise ValueError("log-probabilidades devem ser finitas")

    @property
    def log_cardinality_mass(self) -> float:
        dp = [-math.inf] * (CARD_SIZE + 1)
        dp[0] = 0.0
        for block_index in range(BLOCK_COUNT):
            nxt = [-math.inf] * (CARD_SIZE + 1)
            for previous_count, base in enumerate(dp):
                if base == -math.inf:
                    continue
                for pattern in range(PATTERN_COUNT):
                    total = previous_count + pattern.bit_count()
                    if total <= CARD_SIZE:
                        nxt[total] = _logaddexp(
                            nxt[total],
                            base + self.local_log_prob[block_index][pattern],
                        )
            dp = nxt
        return dp[CARD_SIZE]

    def patterns_for_card(self, card: Iterable[int]) -> tuple[int, ...]:
        normalized = normalize_numbers(card)
        selected = set(normalized)
        return tuple(_encode_pattern(selected, block) for block in self.blocks)

    def raw_log_score(self, card: Iterable[int]) -> float:
        patterns = self.patterns_for_card(card)
        return sum(self.local_log_prob[index][pattern] for index, pattern in enumerate(patterns))

    def card_log_probability(self, card: Iterable[int]) -> float:
        return self.raw_log_score(card) - self.log_cardinality_mass

    def score_card(self, card: Iterable[int]) -> HigherOrderCardScore:
        normalized = normalize_numbers(card)
        value = self.card_log_probability(normalized)
        return HigherOrderCardScore(
            card=normalized,
            log_probability=value,
            log_loss=-value,
            probability=math.exp(value),
        )

    def map_card(self) -> tuple[int, ...]:
        dp = [-math.inf] * (CARD_SIZE + 1)
        dp[0] = 0.0
        decisions: list[list[tuple[int, int] | None]] = []

        for block_index in range(BLOCK_COUNT):
            nxt = [-math.inf] * (CARD_SIZE + 1)
            choice: list[tuple[int, int] | None] = [None] * (CARD_SIZE + 1)
            for previous_count, base in enumerate(dp):
                if base == -math.inf:
                    continue
                for pattern in range(PATTERN_COUNT):
                    total = previous_count + pattern.bit_count()
                    if total > CARD_SIZE:
                        continue
                    candidate = base + self.local_log_prob[block_index][pattern]
                    current = nxt[total]
                    if candidate > current:
                        nxt[total] = candidate
                        choice[total] = (previous_count, pattern)
            dp = nxt
            decisions.append(choice)

        if dp[CARD_SIZE] == -math.inf:
            raise RuntimeError("P15_HIGHER_ORDER_MAP_UNREACHABLE")

        patterns = [0] * BLOCK_COUNT
        count = CARD_SIZE
        for block_index in range(BLOCK_COUNT - 1, -1, -1):
            decision = decisions[block_index][count]
            if decision is None:
                raise RuntimeError("P15_HIGHER_ORDER_MAP_RECONSTRUCTION_FAILED")
            previous_count, pattern = decision
            patterns[block_index] = pattern
            count = previous_count

        selected: list[int] = []
        for block_index, pattern in enumerate(patterns):
            for bit, number in enumerate(self.blocks[block_index]):
                if pattern & (1 << bit):
                    selected.append(number)
        if len(selected) != CARD_SIZE:
            raise RuntimeError("P15_HIGHER_ORDER_MAP_CARDINALITY_FAILED")
        return tuple(sorted(selected))

    def map_score(self) -> HigherOrderCardScore:
        return self.score_card(self.map_card())

    def rank_full_space(
        self,
        *,
        top_k: int = 10,
        observed_card: Iterable[int] | None = None,
    ) -> FullSpaceRanking:
        """Enumerate all 3,268,760 states and prove the global ranking.

        This method is intentionally exhaustive.  It is used for final/current
        model certification, not inside every historical walk-forward window.
        """

        if top_k <= 0:
            raise ValueError("top_k deve ser positivo")
        observed = normalize_numbers(observed_card) if observed_card is not None else None
        observed_raw = self.raw_log_score(observed) if observed is not None else None
        observed_rank = 1 if observed is not None else None
        heap: list[tuple[float, tuple[int, ...], tuple[int, ...]]] = []
        evaluated = 0

        for card in combinations(range(1, UNIVERSE_SIZE + 1), CARD_SIZE):
            raw = self.raw_log_score(card)
            evaluated += 1
            tie_key = tuple(-number for number in card)
            entry = (raw, tie_key, card)
            if len(heap) < top_k:
                heapq.heappush(heap, entry)
            elif entry > heap[0]:
                heapq.heapreplace(heap, entry)

            if observed is not None and card != observed:
                assert observed_raw is not None and observed_rank is not None
                if raw > observed_raw or (raw == observed_raw and card < observed):
                    observed_rank += 1

        if evaluated != TOTAL_SIMPLE_CARDS:
            raise RuntimeError("P15_FULL_SPACE_ENUMERATION_INCOMPLETE")

        ordered = sorted(heap, key=lambda item: (-item[0], item[2]))
        normalizer = self.log_cardinality_mass
        scores = tuple(
            HigherOrderCardScore(
                card=card,
                log_probability=raw - normalizer,
                log_loss=-(raw - normalizer),
                probability=math.exp(raw - normalizer),
            )
            for raw, _tie, card in ordered
        )
        return FullSpaceRanking(
            evaluated_cards=evaluated,
            top_cards=scores,
            observed_card=observed,
            observed_rank=observed_rank,
        )


def fit_block_pattern_from_counts(
    *,
    blocks: Sequence[Sequence[int]],
    pattern_counts: Sequence[Sequence[int]],
    n: int,
    prior_strength: float = 32.0,
    prior_inclusion: float = 0.6,
    source: str = "P15_H104_HIGHER_ORDER_BLOCK_FACTOR",
) -> BlockPatternConditionalModel:
    normalized_blocks = _validate_blocks(blocks)
    if n <= 0:
        raise ValueError("n deve ser positivo")
    if len(pattern_counts) != BLOCK_COUNT:
        raise ValueError("contadores de padrões incompletos")
    if prior_strength <= 0.0:
        raise ValueError("prior_strength deve ser positivo")
    if not 0.0 < prior_inclusion < 1.0:
        raise ValueError("prior_inclusion deve estar em (0,1)")

    local: list[tuple[float, ...]] = []
    for block_index in range(BLOCK_COUNT):
        counts = pattern_counts[block_index]
        if len(counts) != PATTERN_COUNT:
            raise ValueError("cada bloco deve possuir 32 contadores")
        if sum(int(value) for value in counts) != n:
            raise ValueError("contagem local incompatível com n")

        probs: list[float] = []
        for pattern in range(PATTERN_COUNT):
            k = pattern.bit_count()
            null_pattern_probability = (prior_inclusion**k) * ((1.0 - prior_inclusion) ** (BLOCK_SIZE - k))
            posterior = (int(counts[pattern]) + prior_strength * null_pattern_probability) / (
                n + prior_strength
            )
            probs.append(posterior)
        local.append(tuple(math.log(probability) for probability in probs))

    return BlockPatternConditionalModel(
        blocks=normalized_blocks,
        local_log_prob=tuple(local),
        source=source,
    )


def fit_higher_order_blocks(
    draws: Sequence[Iterable[int]],
    *,
    blocks: Sequence[Sequence[int]] | None = None,
    prior_strength: float = 32.0,
    prior_inclusion: float = 0.6,
    source: str = "P15_H104_HIGHER_ORDER_BLOCK_FACTOR",
) -> BlockPatternConditionalModel:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if not normalized:
        raise ValueError("é necessário histórico")
    learned_blocks = learn_information_blocks(normalized) if blocks is None else _validate_blocks(blocks)
    counts = pattern_counts_from_draws(normalized, learned_blocks)
    return fit_block_pattern_from_counts(
        blocks=learned_blocks,
        pattern_counts=counts,
        n=len(normalized),
        prior_strength=prior_strength,
        prior_inclusion=prior_inclusion,
        source=source,
    )
