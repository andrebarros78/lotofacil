from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path

from sare_lotofacil.domain.combinatorics import (
    draw_sum_mean,
    draw_sum_variance,
    exact_hit_distribution,
    expected_hits,
    pair_probability,
    triple_probability,
    variance_hits,
)
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.persistence.db import initialize_database
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER


def doctor() -> int:
    distribution = exact_hit_distribution()
    checks = {
        "combination_space": DEFAULT_RULES.combination_space == 3_268_760,
        "distribution_sum": sum(distribution.values()) == 1,
        "expected_hits": expected_hits() == 9,
        "variance_hits": variance_hits() == Fraction(3, 2),
        "pair_probability": pair_probability() == Fraction(7, 20),
        "triple_probability": triple_probability() == Fraction(91, 460),
        "draw_sum_mean": draw_sum_mean() == 195,
        "draw_sum_variance": draw_sum_variance() == 325,
        "uniform_brier": abs(UNIFORM_BRIER - 0.24) < 1e-12,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("MATHEMATICAL_CHECKS_FAIL")
        for name in failed:
            print(f"FAIL: {name}")
        return 1
    print("MATHEMATICAL_CHECKS_PASS")
    print(f"combination_space={DEFAULT_RULES.combination_space}")
    print(f"uniform_brier={UNIFORM_BRIER:.12f}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sare-lotofacil")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor", help="verifica invariantes matemáticos do Core")
    init_db = subparsers.add_parser("init-db", help="inicializa o banco SQLite local")
    init_db.add_argument("--path", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "doctor":
        return doctor()
    if args.command == "init-db":
        path = initialize_database(args.path)
        print(f"DATABASE_INITIALIZED {path}")
        return 0
    raise RuntimeError("comando não tratado")
