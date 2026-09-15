from __future__ import annotations

from dataclasses import dataclass
from math import comb


@dataclass(frozen=True, slots=True)
class LotofacilRules:
    universe_size: int = 25
    draw_size: int = 15
    simple_card_size: int = 15
    simple_bet_cost_cents: int = 350

    @property
    def combination_space(self) -> int:
        return comb(self.universe_size, self.draw_size)

    @property
    def marginal_probability(self) -> float:
        return self.draw_size / self.universe_size

    def expanded_bet_equivalent_cards(self, selected_numbers: int) -> int:
        if not self.simple_card_size <= selected_numbers <= 20:
            raise ValueError("selected_numbers deve estar entre 15 e 20")
        return comb(selected_numbers, self.simple_card_size)

    def expanded_bet_cost_cents(self, selected_numbers: int) -> int:
        return self.expanded_bet_equivalent_cards(selected_numbers) * self.simple_bet_cost_cents


@dataclass(frozen=True, slots=True)
class SpecialPrizeRuleset:
    ruleset_id: str
    contest_id: int
    commercial_name: str
    fixed_prize_cents_by_hits: tuple[tuple[int, int], ...]
    variable_share_bps_by_hits: tuple[tuple[int, int], ...]
    non_accumulating: bool
    source_url: str

    def __post_init__(self) -> None:
        fixed = dict(self.fixed_prize_cents_by_hits)
        variable = dict(self.variable_share_bps_by_hits)
        if set(fixed) != {11, 12, 13}:
            raise ValueError("SPECIAL_RULESET_REQUIRES_FIXED_TIERS_11_12_13")
        if set(variable) != {14, 15}:
            raise ValueError("SPECIAL_RULESET_REQUIRES_VARIABLE_TIERS_14_15")
        if any(value < 0 for value in fixed.values()):
            raise ValueError("SPECIAL_RULESET_NEGATIVE_FIXED_PRIZE")
        if any(value < 0 for value in variable.values()) or sum(variable.values()) != 10_000:
            raise ValueError("SPECIAL_RULESET_VARIABLE_SHARES_MUST_SUM_10000_BPS")
        if not self.source_url.startswith("https://"):
            raise ValueError("SPECIAL_RULESET_REQUIRES_HTTPS_SOURCE")

    def fixed_prize_cents(self, hits: int) -> int | None:
        return dict(self.fixed_prize_cents_by_hits).get(int(hits))

    def variable_share_bps(self, hits: int) -> int | None:
        return dict(self.variable_share_bps_by_hits).get(int(hits))


DEFAULT_RULES = LotofacilRules()

# Regra explicitamente publicada pela CAIXA para a Lotofácil da Independência 2026.
# Não é usada como regra genérica para outros anos nem para concursos regulares.
INDEPENDENCIA_2026_RULESET = SpecialPrizeRuleset(
    ruleset_id="LOTOFACIL_INDEPENDENCIA_2026_CONTEST_3780",
    contest_id=3780,
    commercial_name="Lotofácil da Independência 2026",
    fixed_prize_cents_by_hits=((11, 350), (12, 700), (13, 1750)),
    variable_share_bps_by_hits=((14, 1300), (15, 8700)),
    non_accumulating=True,
    source_url=(
        "https://www.caixa.gov.br/loterias/comunicados-importantes/"
        "Paginas/default.aspx"
    ),
)


def special_prize_ruleset_for_contest(contest_id: int) -> SpecialPrizeRuleset | None:
    if not isinstance(contest_id, int) or isinstance(contest_id, bool) or contest_id <= 0:
        raise ValueError("contest_id deve ser inteiro positivo")
    if contest_id == INDEPENDENCIA_2026_RULESET.contest_id:
        return INDEPENDENCIA_2026_RULESET
    return None
