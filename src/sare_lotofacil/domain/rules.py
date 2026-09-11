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


DEFAULT_RULES = LotofacilRules()
