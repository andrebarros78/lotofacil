from __future__ import annotations

import argparse
import json
from pathlib import Path

from sare_lotofacil.reconciliation.official import (
    OFFICIAL_HISTORY_RECONCILIATION_PASS,
    merge_reconciliation_outputs,
    reconcile_history_range,
)


def _run(args: argparse.Namespace) -> int:
    result = reconcile_history_range(
        Path(args.canonical),
        start=args.start,
        end=args.end,
        out_path=Path(args.out),
        raw_dir=Path(args.raw_dir),
        checkpoint_every=args.checkpoint_every,
        delay_seconds=args.delay_seconds,
        timeout=args.timeout,
        retries=args.retries,
        backoff_seconds=args.backoff_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.strict and result["status"] not in {
        "OFFICIAL_HISTORY_RECONCILIATION_PASS",
        "OFFICIAL_HISTORY_RECONCILIATION_SHARD_PASS",
    }:
        return 2
    return 0


def _merge(args: argparse.Namespace) -> int:
    result = merge_reconciliation_outputs(
        Path(args.canonical),
        [Path(value) for value in args.input],
        out_path=Path(args.out),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == OFFICIAL_HISTORY_RECONCILIATION_PASS else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcilia o histórico canônico da Lotofácil concurso a concurso com a API oficial da CAIXA."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Reconcilia uma faixa de concursos.")
    run.add_argument("--canonical", required=True)
    run.add_argument("--start", type=int, required=True)
    run.add_argument("--end", type=int, required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--raw-dir", required=True)
    run.add_argument("--checkpoint-every", type=int, default=25)
    run.add_argument("--delay-seconds", type=float, default=0.20)
    run.add_argument("--timeout", type=float, default=20.0)
    run.add_argument("--retries", type=int, default=3)
    run.add_argument("--backoff-seconds", type=float, default=0.5)
    run.add_argument("--strict", action="store_true")
    run.set_defaults(func=_run)

    merge = subparsers.add_parser("merge", help="Une shards e exige cobertura integral 1..N.")
    merge.add_argument("--canonical", required=True)
    merge.add_argument("--input", action="append", required=True)
    merge.add_argument("--out", required=True)
    merge.set_defaults(func=_merge)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
