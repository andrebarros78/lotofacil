from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.error import HTTPError

import pytest

from sare_lotofacil.reconciliation.official import (
    OFFICIAL_DIVERGENCE,
    OFFICIAL_HISTORY_RECONCILIATION_PASS,
    OFFICIAL_INVALID_RESPONSE,
    OFFICIAL_MATCH,
    OFFICIAL_UNAVAILABLE,
    RawOfficialResponse,
    load_canonical_history,
    merge_reconciliation_outputs,
    reconcile_history_range,
    reconcile_record,
)


class _Response:
    def __init__(self, raw: bytes, status: int = 200):
        self._raw = raw
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self._raw


def _payload(contest_id: int, draw_date: str, numbers=range(1, 16)) -> dict:
    return {
        "tipoJogo": "LOTOFACIL",
        "numero": contest_id,
        "dataApuracao": draw_date,
        "listaDezenas": [f"{number:02d}" for number in numbers],
        "listaRateioPremio": [],
    }


def _canonical(path: Path, count: int = 2) -> Path:
    rows = []
    for contest_id in range(1, count + 1):
        rows.append(
            {
                "contest_id": contest_id,
                "draw_date": f"2026-01-{contest_id:02d}",
                "numbers": list(range(1, 16)),
            }
        )
    path.write_text(json.dumps({"schema_version": 1, "records": rows}), encoding="utf-8")
    return path


def _opener_for_payloads(payloads: dict[int, dict], calls: list[int] | None = None):
    def opener(request, timeout=0):
        contest_id = int(request.full_url.rsplit("/", 1)[-1])
        if calls is not None:
            calls.append(contest_id)
        raw = json.dumps(payloads[contest_id], ensure_ascii=False).encode("utf-8")
        return _Response(raw)

    return opener


def test_load_canonical_history_rejects_gap(tmp_path: Path) -> None:
    path = tmp_path / "canonical.json"
    path.write_text(
        json.dumps(
            {
                "records": [
                    {"contest_id": 1, "draw_date": "2026-01-01", "numbers": list(range(1, 16))},
                    {"contest_id": 3, "draw_date": "2026-01-03", "numbers": list(range(1, 16))},
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="not contiguous"):
        load_canonical_history(path)


def test_reconcile_record_match_binds_raw_payload_hash(tmp_path: Path) -> None:
    canonical_path = _canonical(tmp_path / "canonical.json", 1)
    canonical = load_canonical_history(canonical_path)[0]
    raw = json.dumps(_payload(1, "01/01/2026")).encode("utf-8")
    response = RawOfficialResponse(
        source_url="https://example/1",
        captured_at_utc="2026-09-21T13:00:00+00:00",
        http_status=200,
        raw_bytes=raw,
    )

    result = reconcile_record(canonical, response)

    assert result["status"] == OFFICIAL_MATCH
    assert result["raw_payload_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["canonical_record_sha256"] == result["official_record_sha256"]
    assert result["differences"] == []


def test_reconcile_record_reports_semantic_divergence(tmp_path: Path) -> None:
    canonical_path = _canonical(tmp_path / "canonical.json", 1)
    canonical = load_canonical_history(canonical_path)[0]
    raw = json.dumps(_payload(1, "02/01/2026", range(2, 17))).encode("utf-8")
    response = RawOfficialResponse(
        source_url="https://example/1",
        captured_at_utc="2026-09-21T13:00:00+00:00",
        http_status=200,
        raw_bytes=raw,
    )

    result = reconcile_record(canonical, response)

    assert result["status"] == OFFICIAL_DIVERGENCE
    assert {item["field"] for item in result["differences"]} == {"draw_date", "numbers"}


def test_reconcile_record_rejects_unexpected_contest_id(tmp_path: Path) -> None:
    canonical_path = _canonical(tmp_path / "canonical.json", 1)
    canonical = load_canonical_history(canonical_path)[0]
    raw = json.dumps(_payload(2, "01/01/2026")).encode("utf-8")
    response = RawOfficialResponse(
        source_url="https://example/1",
        captured_at_utc="2026-09-21T13:00:00+00:00",
        http_status=200,
        raw_bytes=raw,
    )

    result = reconcile_record(canonical, response)

    assert result["status"] == OFFICIAL_INVALID_RESPONSE
    assert "UNEXPECTED_CONTEST_ID" in result["error"]


def test_reconcile_record_marks_http_failure_unavailable(tmp_path: Path) -> None:
    canonical_path = _canonical(tmp_path / "canonical.json", 1)
    canonical = load_canonical_history(canonical_path)[0]
    response = RawOfficialResponse(
        source_url="https://example/1",
        captured_at_utc="2026-09-21T13:00:00+00:00",
        http_status=404,
        raw_bytes=b"",
        error="HTTPError:404",
    )

    result = reconcile_record(canonical, response)

    assert result["status"] == OFFICIAL_UNAVAILABLE
    assert result["official_record_sha256"] is None


def test_reconciliation_is_resumable_without_refetching_verified_match(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path / "canonical.json", 1)
    out = tmp_path / "official_reconciliation.json"
    raw_dir = tmp_path / "raw"
    calls: list[int] = []
    payloads = {1: _payload(1, "01/01/2026")}

    first = reconcile_history_range(
        canonical,
        start=1,
        end=1,
        out_path=out,
        raw_dir=raw_dir,
        checkpoint_every=1,
        delay_seconds=0,
        opener=_opener_for_payloads(payloads, calls),
        sleep=lambda _: None,
    )
    assert first["status"] == OFFICIAL_HISTORY_RECONCILIATION_PASS
    assert calls == [1]

    def fail_if_called(*args, **kwargs):
        raise AssertionError("verified contest should not be fetched again")

    second = reconcile_history_range(
        canonical,
        start=1,
        end=1,
        out_path=out,
        raw_dir=raw_dir,
        checkpoint_every=1,
        delay_seconds=0,
        opener=fail_if_called,
        sleep=lambda _: None,
    )
    assert second["status"] == OFFICIAL_HISTORY_RECONCILIATION_PASS
    assert second["entries"][0]["raw_payload_sha256"] == first["entries"][0]["raw_payload_sha256"]


def test_merge_requires_complete_coverage_and_proves_all_matches(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path / "canonical.json", 2)
    payloads = {
        1: _payload(1, "01/01/2026"),
        2: _payload(2, "02/01/2026"),
    }
    shard1 = tmp_path / "shard1"
    shard2 = tmp_path / "shard2"
    reconcile_history_range(
        canonical,
        start=1,
        end=1,
        out_path=shard1 / "official_reconciliation.json",
        raw_dir=shard1 / "raw",
        checkpoint_every=1,
        delay_seconds=0,
        opener=_opener_for_payloads(payloads),
        sleep=lambda _: None,
    )
    reconcile_history_range(
        canonical,
        start=2,
        end=2,
        out_path=shard2 / "official_reconciliation.json",
        raw_dir=shard2 / "raw",
        checkpoint_every=1,
        delay_seconds=0,
        opener=_opener_for_payloads(payloads),
        sleep=lambda _: None,
    )

    merged = merge_reconciliation_outputs(
        canonical,
        [shard1 / "official_reconciliation.json", shard2 / "official_reconciliation.json"],
        out_path=tmp_path / "merged.json",
    )

    assert merged["status"] == OFFICIAL_HISTORY_RECONCILIATION_PASS
    assert merged["coverage"] == {"expected": 2, "observed": 2, "missing": 0, "extra": 0}
    assert merged["counts"][OFFICIAL_MATCH] == 2
    assert merged["raw_evidence_complete"] is True


def test_merge_rejects_tampered_raw_evidence(tmp_path: Path) -> None:
    canonical = _canonical(tmp_path / "canonical.json", 1)
    payloads = {1: _payload(1, "01/01/2026")}
    shard = tmp_path / "shard"
    reconcile_history_range(
        canonical,
        start=1,
        end=1,
        out_path=shard / "official_reconciliation.json",
        raw_dir=shard / "raw",
        checkpoint_every=1,
        delay_seconds=0,
        opener=_opener_for_payloads(payloads),
        sleep=lambda _: None,
    )
    (shard / "raw" / "000001.json").write_text('{"tampered":true}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="raw evidence hash mismatch"):
        merge_reconciliation_outputs(
            canonical,
            [shard / "official_reconciliation.json"],
            out_path=tmp_path / "merged.json",
        )
