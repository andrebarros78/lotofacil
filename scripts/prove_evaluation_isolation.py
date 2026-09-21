from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from sare_lotofacil.evaluation import CANONICAL_EVALUATION, MANUAL_EVALUATION
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect
from sare_lotofacil.persistence.operations import (
    evaluate_portfolio,
    evaluate_portfolio_revision,
    persist_uniform_portfolio,
)
from sare_lotofacil.persistence.repository import persist_caixa_contest


def prove(work_dir: Path) -> dict[str, object]:
    work_dir.mkdir(parents=True, exist_ok=True)
    db = work_dir / "f6-evaluation-isolation.db"
    db.unlink(missing_ok=True)

    contest_id = 3785
    numbers = tuple(range(1, 16))
    contest = CaixaContest(
        record=validate_contest(contest_id, date(2026, 9, 21), numbers),
        prize_tiers=(),
        source_url=f"fixture://f6/{contest_id}",
        captured_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        raw_payload={"numero": contest_id, "listaDezenas": list(numbers)},
    )
    persisted = persist_caixa_contest(db, contest, source_class="CAIXA_F6_PROOF")
    portfolio = persist_uniform_portfolio(
        db,
        card_count=3,
        seed=20260921,
        target_contest=contest_id,
    )

    manual = evaluate_portfolio(db, portfolio.portfolio_id, numbers)
    canonical = evaluate_portfolio_revision(
        db,
        portfolio.portfolio_id,
        contest_id,
        persisted.revision,
    )

    if manual.evaluation_class != MANUAL_EVALUATION or manual.evidence_eligible:
        raise RuntimeError("MANUAL_EVALUATION_WAS_NOT_ISOLATED")
    if canonical.evaluation_class != CANONICAL_EVALUATION or not canonical.evidence_eligible:
        raise RuntimeError("CANONICAL_EVALUATION_WAS_NOT_ELIGIBLE")
    if canonical.source_class != "CAIXA_F6_PROOF":
        raise RuntimeError("CANONICAL_SOURCE_CLASS_NOT_BOUND")
    if canonical.result != manual.result:
        raise RuntimeError("PROOF_REQUIRES_IDENTICAL_DRAW_ACROSS_CHANNELS")

    wrong_target_blocked = False
    try:
        evaluate_portfolio_revision(
            db,
            persist_uniform_portfolio(
                db,
                card_count=1,
                seed=20260922,
                target_contest=contest_id + 1,
            ).portfolio_id,
            contest_id,
            persisted.revision,
        )
    except ValueError as exc:
        wrong_target_blocked = str(exc) == "CANONICAL_EVALUATION_TARGET_MISMATCH"
    if not wrong_target_blocked:
        raise RuntimeError("CANONICAL_TARGET_MISMATCH_NOT_BLOCKED")

    manual_spoof_blocked = False
    canonical_spoof_blocked = False
    result_mask = sum(1 << (number - 1) for number in numbers)
    with connect(db) as connection:
        try:
            connection.execute(
                "INSERT INTO evaluations("
                "evaluation_id,portfolio_id,evaluation_class,evidence_eligible,"
                "source_class,result_mask,hits_json,max_hits"
                ") VALUES ('f6-manual-spoof',?,'CANONICAL_EVALUATION',1,"
                "'CAIXA',?,'[15]',15)",
                (portfolio.portfolio_id, result_mask),
            )
        except sqlite3.IntegrityError:
            manual_spoof_blocked = True

        try:
            connection.execute(
                "INSERT INTO revision_evaluations("
                "evaluation_id,portfolio_id,evaluation_class,evidence_eligible,"
                "source_class,contest_id,revision,result_mask,hits_json,max_hits"
                ") VALUES ('f6-canonical-spoof',?,'MANUAL_EVALUATION',0,"
                "'CAIXA_F6_PROOF',?,?,?,'[15]',15)",
                (
                    portfolio.portfolio_id,
                    contest_id,
                    persisted.revision,
                    result_mask,
                ),
            )
        except sqlite3.IntegrityError:
            canonical_spoof_blocked = True

        counts = {
            "manual_rows": int(
                connection.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
            ),
            "canonical_rows": int(
                connection.execute(
                    "SELECT COUNT(*) FROM revision_evaluations"
                ).fetchone()[0]
            ),
        }

    if not manual_spoof_blocked or not canonical_spoof_blocked:
        raise RuntimeError("DATABASE_CHANNEL_SPOOF_NOT_BLOCKED")

    return {
        "status": "EVALUATION_ISOLATION_PROOF_PASS",
        "schema_version": SCHEMA_VERSION,
        "manual": {
            "evaluation_class": manual.evaluation_class,
            "evidence_eligible": manual.evidence_eligible,
            "source_class": manual.source_class,
        },
        "canonical": {
            "evaluation_class": canonical.evaluation_class,
            "evidence_eligible": canonical.evidence_eligible,
            "source_class": canonical.source_class,
            "contest_id": canonical.contest_id,
            "revision": canonical.revision,
        },
        "proof": {
            "same_draw_does_not_cross_channels": True,
            "canonical_target_mismatch_blocked": wrong_target_blocked,
            "manual_spoof_blocked_at_database": manual_spoof_blocked,
            "canonical_spoof_blocked_at_database": canonical_spoof_blocked,
            "row_counts": counts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = prove(args.work_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
