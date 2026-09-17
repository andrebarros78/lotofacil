from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sare_lotofacil.domain.masks import mask_to_numbers
from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.operations import canonical_json, evaluate_portfolio_revision


@dataclass(frozen=True, slots=True)
class FrozenCardRecord:
    portfolio_id: str
    position: int
    target_contest: int
    seed: int
    card: tuple[int, ...]
    freeze_sha256: str


@dataclass(frozen=True, slots=True)
class PostContestCardAudit:
    portfolio_id: str
    position: int
    freeze_sha256: str
    card: tuple[int, ...]
    hits: int
    matched_numbers: tuple[int, ...]
    selected_misses: tuple[int, ...]
    omitted_winners: tuple[int, ...]
    evaluation_id: str


@dataclass(frozen=True, slots=True)
class PostContestEpisode:
    episode_id: str
    contest_id: int
    revision: int
    result: tuple[int, ...]
    cards: tuple[PostContestCardAudit, ...]
    max_hits: int
    payload: dict[str, Any]


def _sha256(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def list_frozen_cards_for_target(path: str | Path, target_contest: int) -> tuple[FrozenCardRecord, ...]:
    if target_contest <= 0:
        raise ValueError("target_contest deve ser positivo")
    initialize_database(path)
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT p.portfolio_id, pc.position, p.target_contest, p.seed, pc.result_mask "
            "FROM portfolios p JOIN portfolio_cards pc ON pc.portfolio_id=p.portfolio_id "
            "WHERE p.target_contest=? "
            "ORDER BY p.created_at, p.portfolio_id, pc.position",
            (target_contest,),
        ).fetchall()
    records: list[FrozenCardRecord] = []
    for portfolio_id, position, contest, seed, result_mask in rows:
        card = mask_to_numbers(int(result_mask))
        freeze_payload = {
            "portfolio_id": portfolio_id,
            "position": int(position),
            "target_contest": int(contest),
            "seed": int(seed),
            "card": list(card),
        }
        records.append(
            FrozenCardRecord(
                portfolio_id=str(portfolio_id),
                position=int(position),
                target_contest=int(contest),
                seed=int(seed),
                card=card,
                freeze_sha256=_sha256(freeze_payload),
            )
        )
    return tuple(records)


def _load_result(path: str | Path, contest_id: int, revision: int) -> tuple[int, ...]:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT result_mask FROM contest_revisions WHERE contest_id=? AND revision=?",
            (contest_id, revision),
        ).fetchone()
    if not row:
        raise KeyError((contest_id, revision))
    return mask_to_numbers(int(row[0]))


def _persist_episode(path: str | Path, episode_id: str, payload: dict[str, Any]) -> None:
    detail_json = canonical_json(payload)
    event_id = "audit-" + hashlib.sha256(
        f"POST_CONTEST_EPISODE_RECORDED|post_contest_episode|{episode_id}|{detail_json}".encode("utf-8")
    ).hexdigest()[:24]
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO audit_events(event_id, action, entity_type, entity_id, detail_json) "
            "VALUES (?, 'POST_CONTEST_EPISODE_RECORDED', 'post_contest_episode', ?, ?)",
            (event_id, episode_id, detail_json),
        )


def audit_post_contest(
    path: str | Path,
    contest_id: int,
    revision: int,
    *,
    expected_card_count: int | None = None,
) -> PostContestEpisode:
    if contest_id <= 0 or revision <= 0:
        raise ValueError("contest_id e revision devem ser positivos")
    initialize_database(path)
    before = list_frozen_cards_for_target(path, contest_id)
    if not before:
        raise RuntimeError("NO_FROZEN_CARDS_FOR_TARGET")
    if expected_card_count is not None and len(before) != expected_card_count:
        raise RuntimeError(
            f"FROZEN_CARD_COUNT_MISMATCH expected={expected_card_count} observed={len(before)}"
        )

    result = _load_result(path, contest_id, revision)
    result_set = set(result)
    evaluation_by_portfolio: dict[str, tuple[str, tuple[int, ...]]] = {}
    for portfolio_id in dict.fromkeys(card.portfolio_id for card in before):
        evaluation = evaluate_portfolio_revision(path, portfolio_id, contest_id, revision)
        evaluation_by_portfolio[portfolio_id] = (evaluation.evaluation_id, evaluation.hits)

    after = list_frozen_cards_for_target(path, contest_id)
    if before != after:
        raise RuntimeError("FROZEN_CARD_MUTATION_DETECTED")

    audits: list[PostContestCardAudit] = []
    for card in before:
        evaluation_id, hits_by_position = evaluation_by_portfolio[card.portfolio_id]
        if card.position > len(hits_by_position):
            raise RuntimeError("PORTFOLIO_EVALUATION_POSITION_MISMATCH")
        card_set = set(card.card)
        matched = tuple(sorted(card_set & result_set))
        selected_misses = tuple(sorted(card_set - result_set))
        omitted_winners = tuple(sorted(result_set - card_set))
        hits = int(hits_by_position[card.position - 1])
        if hits != len(matched):
            raise RuntimeError("PORTFOLIO_EVALUATION_HIT_MISMATCH")
        audits.append(
            PostContestCardAudit(
                portfolio_id=card.portfolio_id,
                position=card.position,
                freeze_sha256=card.freeze_sha256,
                card=card.card,
                hits=hits,
                matched_numbers=matched,
                selected_misses=selected_misses,
                omitted_winners=omitted_winners,
                evaluation_id=evaluation_id,
            )
        )

    payload: dict[str, Any] = {
        "schema_version": 1,
        "contest_id": contest_id,
        "revision": revision,
        "result": list(result),
        "card_count": len(audits),
        "max_hits": max(item.hits for item in audits),
        "cards": [
            {
                "portfolio_id": item.portfolio_id,
                "position": item.position,
                "freeze_sha256": item.freeze_sha256,
                "card": list(item.card),
                "hits": item.hits,
                "matched_numbers": list(item.matched_numbers),
                "selected_misses": list(item.selected_misses),
                "omitted_winners": list(item.omitted_winners),
                "evaluation_id": item.evaluation_id,
            }
            for item in audits
        ],
        "learning_policy": {
            "retrospective_only": True,
            "rewrite_frozen_cards": False,
            "direct_model_tuning_allowed": False,
            "challenger_required": True,
            "promotion_requires_predeclared_validation": True,
        },
    }
    episode_id = "post-contest-" + _sha256(payload)[:24]
    payload["episode_id"] = episode_id
    _persist_episode(path, episode_id, payload)
    return PostContestEpisode(
        episode_id=episode_id,
        contest_id=contest_id,
        revision=revision,
        result=result,
        cards=tuple(audits),
        max_hits=max(item.hits for item in audits),
        payload=payload,
    )


def list_post_contest_episodes(path: str | Path, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
    if not 1 <= limit <= 500:
        raise ValueError("limit deve estar entre 1 e 500")
    initialize_database(path)
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT detail_json FROM audit_events "
            "WHERE action='POST_CONTEST_EPISODE_RECORDED' AND entity_type='post_contest_episode' "
            "ORDER BY created_at DESC, event_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return tuple(json.loads(row[0]) for row in rows)
