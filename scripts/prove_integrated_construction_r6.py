from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from sare_lotofacil.experiments.challenger import ChampionConfig, build_hypothesis_from_episode, run_isolated_challenger
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.operations import persist_uniform_portfolio
from sare_lotofacil.persistence.post_contest import audit_post_contest, list_frozen_cards_for_target, list_post_contest_episodes
from sare_lotofacil.persistence.repository import persist_caixa_contest
from sare_lotofacil.portfolios.frozen import empty_operator_card_ledger, freeze_operator_cards, recover_operator_freezes, validate_operator_card_ledger
from sare_lotofacil.rag.learning import build_learning_rag


def _sha(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _draws(total: int = 160) -> tuple[tuple[int, ...], ...]:
    rows = []
    for contest in range(1, total + 1):
        start = (contest * 7) % 25
        rows.append(tuple(sorted(((start + offset) % 25) + 1 for offset in range(15))))
    return tuple(rows)


def run(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    source_commit = os.environ.get("GITHUB_SHA", "local-controlled-proof")
    workflow_run_id = os.environ.get("GITHUB_RUN_ID", "local-controlled-proof")

    ledger = empty_operator_card_ledger()
    ledger, first = freeze_operator_cards(
        ledger, target_contest=100, requested_card_count=1,
        state_snapshot_hash="controlled-r6-snapshot-99",
        created_at_utc="2026-09-17T22:00:00+00:00",
        idempotency_key="r6-controlled-request-1",
        source_commit=source_commit, workflow_run_id=workflow_run_id,
    )
    ledger, second = freeze_operator_cards(
        ledger, target_contest=100, requested_card_count=1,
        state_snapshot_hash="controlled-r6-snapshot-99",
        created_at_utc="2026-09-17T22:00:01+00:00",
        idempotency_key="r6-controlled-request-2",
        source_commit=source_commit, workflow_run_id=workflow_run_id,
    )
    frozen_registry = recover_operator_freezes(ledger, target_contest=100, expected_card_count=2)
    ledger_before_replay = json.dumps(ledger, sort_keys=True)
    ledger, replay = freeze_operator_cards(
        ledger, target_contest=100, requested_card_count=1,
        state_snapshot_hash="controlled-r6-snapshot-99",
        created_at_utc="2026-09-17T22:00:00+00:00",
        idempotency_key="r6-controlled-request-1",
        source_commit=source_commit, workflow_run_id=workflow_run_id,
    )
    assert replay["status"] == "GITHUB_OPERATOR_CARD_FREEZE_IDEMPOTENT_REPLAY"
    assert json.dumps(ledger, sort_keys=True) == ledger_before_replay
    restarted_ledger = json.loads(json.dumps(ledger))
    validate_operator_card_ledger(restarted_ledger)
    assert len(recover_operator_freezes(restarted_ledger, target_contest=100, expected_card_count=2)) == 2

    db = root / "integrated-r6.db"
    portfolio = persist_uniform_portfolio(db, card_count=2, seed=100, target_contest=100)
    before = list_frozen_cards_for_target(db, 100)
    assert len(before) == 2

    result = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)
    contest = CaixaContest(
        record=validate_contest(100, date(2026, 1, 1), result),
        prize_tiers=(),
        source_url="controlled://r6/official-revision/100",
        captured_at=datetime(2026, 9, 17, 22, 0, tzinfo=timezone.utc),
        raw_payload={"numero": 100, "listaDezenas": list(result), "r6_fixture": True},
    )
    persisted = persist_caixa_contest(db, contest, source_class="OFICIAL_DIRETA")
    assert persisted.revision == 1

    episode = audit_post_contest(db, 100, 1, expected_card_count=2)
    after = list_frozen_cards_for_target(db, 100)
    assert before == after

    repeated_episode = audit_post_contest(db, 100, 1, expected_card_count=2)
    assert repeated_episode.episode_id == episode.episode_id
    assert len(list_post_contest_episodes(db)) == 1

    rag_root = root / "rag-root"
    rag_root.mkdir(exist_ok=True)
    (rag_root / "README.md").write_text("R6 controlled integration fixture\n", encoding="utf-8")
    rag = build_learning_rag(rag_root, db)
    hits = rag.search("concurso 100 cartoes congelados challenger", top_k=5)
    learning_hits = [hit for hit in hits if hit.path.startswith("learning/post_contest/100/")]
    assert learning_hits
    assert episode.episode_id in learning_hits[0].content

    hypothesis = build_hypothesis_from_episode(
        episode.payload,
        hypothesis_id="r6-controlled-challenger",
        statement="controlled R6 hypothesis",
        expected_mechanism="exercise isolated temporal validation without promotion",
        validation_start_contest=101,
        validation_end_contest=140,
        challenger_lam=50.0,
        delta_min=0.0,
    )
    champion = ChampionConfig()
    champion_before = champion.config_hash
    decision = run_isolated_challenger(_draws(), hypothesis=hypothesis, champion=champion)
    assert champion.config_hash == champion_before == decision.champion_hash_after
    assert decision.promotion_applied is False
    assert decision.predictive_evidence == "NOT_ESTABLISHED"

    provenance = [
        {
            "freeze_id": item["freeze_id"],
            "payload_hash": item["payload_hash"],
            "source_commit": item["source_commit"],
            "workflow_run_id": item["workflow_run_id"],
            "state_ref": item["state_ref"],
            "idempotency_key": item["idempotency_key"],
        }
        for item in frozen_registry
    ]

    return {
        "status": "R6_INTEGRATED_CHAIN_PASS",
        "classification": "CONTROLLED_INTEGRATION_FIXTURE_NOT_HISTORICAL_PROSPECTIVE",
        "source_commit": source_commit,
        "workflow_run_id": workflow_run_id,
        "operator_registry": {
            "generated": first["generated_card_count"] + second["generated_card_count"],
            "replay_generated": replay["generated_card_count"],
            "provenance": provenance,
            "ledger_sha256": _sha(restarted_ledger),
        },
        "operational_fixture": {
            "portfolio_id": portfolio.portfolio_id,
            "target_contest": 100,
            "freeze_hashes_before": [item.freeze_sha256 for item in before],
            "freeze_hashes_after": [item.freeze_sha256 for item in after],
            "immutable": before == after,
            "episode_id": episode.episode_id,
            "episode_replay_id": repeated_episode.episode_id,
            "episode_count": len(list_post_contest_episodes(db)),
            "rag_read_only_recovered": True,
        },
        "challenger": {
            "hypothesis_id": hypothesis.hypothesis_id,
            "hypothesis_hash": hypothesis.hypothesis_hash,
            "champion_hash_before": decision.champion_hash_before,
            "champion_hash_after": decision.champion_hash_after,
            "decision": decision.decision,
            "reason": decision.reason,
            "promotion_applied": decision.promotion_applied,
            "predictive_evidence": decision.predictive_evidence,
            "decision_hash": decision.content_hash,
        },
        "claims": {
            "predictive_advantage": "NOT_ESTABLISHED",
            "historical_prospective_claim_for_fixture": False,
            "automatic_promotion": False,
        },
    }


def main() -> int:
    proof = run(Path("artifacts/r6-controlled"))
    out = Path("artifacts/r6_integrated_chain.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(proof, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
