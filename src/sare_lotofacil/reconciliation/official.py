from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sare_lotofacil.ingestion.caixa import BASE_URL, parse_caixa_payload
from sare_lotofacil.ingestion.validation import ContestRecord, validate_contest

OFFICIAL_MATCH = "OFFICIAL_MATCH"
OFFICIAL_DIVERGENCE = "OFFICIAL_DIVERGENCE"
OFFICIAL_UNAVAILABLE = "OFFICIAL_UNAVAILABLE"
OFFICIAL_INVALID_RESPONSE = "OFFICIAL_INVALID_RESPONSE"
OFFICIAL_HISTORY_RECONCILIATION_PASS = "OFFICIAL_HISTORY_RECONCILIATION_PASS"
OFFICIAL_HISTORY_RECONCILIATION_FAIL = "OFFICIAL_HISTORY_RECONCILIATION_FAIL"
OFFICIAL_HISTORY_RECONCILIATION_SHARD_PASS = "OFFICIAL_HISTORY_RECONCILIATION_SHARD_PASS"

_RETRYABLE_HTTP = {429, 500, 502, 503, 504}


@dataclass(frozen=True, slots=True)
class RawOfficialResponse:
    source_url: str
    captured_at_utc: str
    http_status: int | None
    raw_bytes: bytes
    error: str | None = None


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _record_payload(record: ContestRecord) -> dict[str, object]:
    return {
        "contest_id": record.contest_id,
        "draw_date": record.draw_date.isoformat(),
        "numbers": list(record.numbers),
    }


def _record_sha256(record: ContestRecord) -> str:
    return _sha256_bytes(_canonical_bytes(_record_payload(record)))


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _atomic_write_bytes(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(raw)
    temp.replace(path)


def load_canonical_history(path: Path) -> tuple[ContestRecord, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("records")
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("canonical history has no records")

    records: list[ContestRecord] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("canonical history contains a non-object record")
        try:
            draw_date = datetime.strptime(str(row["draw_date"]), "%Y-%m-%d").date()
            record = validate_contest(
                int(row["contest_id"]),
                draw_date,
                tuple(int(value) for value in row["numbers"]),
            )
        except Exception as exc:
            raise RuntimeError(f"invalid canonical record: {row!r}") from exc
        records.append(record)

    ordered = tuple(sorted(records, key=lambda item: item.contest_id))
    if ordered[0].contest_id != 1:
        raise RuntimeError("canonical history must start at contest 1")
    for expected_id, record in enumerate(ordered, start=1):
        if record.contest_id != expected_id:
            raise RuntimeError(
                f"canonical history is not contiguous: expected={expected_id} observed={record.contest_id}"
            )
    return ordered


def fetch_official_raw(
    contest_id: int,
    *,
    timeout: float = 20.0,
    retries: int = 3,
    backoff_seconds: float = 0.5,
    opener: Callable[..., Any] = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> RawOfficialResponse:
    if contest_id <= 0:
        raise ValueError("contest_id must be positive")
    if retries < 0:
        raise ValueError("retries cannot be negative")
    source_url = f"{BASE_URL}/{contest_id}"
    request = Request(
        source_url,
        headers={"Accept": "application/json", "User-Agent": "SARE-Lotofacil/1.1-official-reconciliation"},
    )

    for attempt in range(retries + 1):
        captured_at_utc = datetime.now(timezone.utc).isoformat()
        try:
            with opener(request, timeout=timeout) as response:
                raw = response.read()
                status = int(getattr(response, "status", 200))
            return RawOfficialResponse(
                source_url=source_url,
                captured_at_utc=captured_at_utc,
                http_status=status,
                raw_bytes=raw,
            )
        except HTTPError as exc:
            try:
                raw = exc.read()
            except Exception:
                raw = b""
            if exc.code in _RETRYABLE_HTTP and attempt < retries:
                sleep(backoff_seconds * (2**attempt))
                continue
            return RawOfficialResponse(
                source_url=source_url,
                captured_at_utc=captured_at_utc,
                http_status=int(exc.code),
                raw_bytes=raw,
                error=f"HTTPError:{exc.code}",
            )
        except (URLError, TimeoutError, OSError) as exc:
            if attempt < retries:
                sleep(backoff_seconds * (2**attempt))
                continue
            return RawOfficialResponse(
                source_url=source_url,
                captured_at_utc=captured_at_utc,
                http_status=None,
                raw_bytes=b"",
                error=f"{type(exc).__name__}:{exc}",
            )

    raise AssertionError("unreachable")


def reconcile_record(
    canonical: ContestRecord,
    response: RawOfficialResponse,
) -> dict[str, object]:
    raw_sha256 = _sha256_bytes(response.raw_bytes) if response.raw_bytes else None
    base: dict[str, object] = {
        "contest_id": canonical.contest_id,
        "canonical_draw_date": canonical.draw_date.isoformat(),
        "canonical_numbers": list(canonical.numbers),
        "canonical_record_sha256": _record_sha256(canonical),
        "official_source_url": response.source_url,
        "captured_at_utc": response.captured_at_utc,
        "http_status": response.http_status,
        "raw_payload_sha256": raw_sha256,
        "official_draw_date": None,
        "official_numbers": None,
        "official_record_sha256": None,
        "differences": [],
    }

    if response.error is not None or response.http_status is None or not 200 <= response.http_status < 300:
        base["status"] = OFFICIAL_UNAVAILABLE
        base["error"] = response.error or f"HTTP_STATUS:{response.http_status}"
        return base

    if not response.raw_bytes:
        base["status"] = OFFICIAL_INVALID_RESPONSE
        base["error"] = "EMPTY_RESPONSE"
        return base

    try:
        payload = json.loads(response.raw_bytes.decode("utf-8"))
        official = parse_caixa_payload(
            payload,
            source_url=response.source_url,
            captured_at=datetime.fromisoformat(response.captured_at_utc),
        )
    except Exception as exc:
        base["status"] = OFFICIAL_INVALID_RESPONSE
        base["error"] = f"{type(exc).__name__}:{exc}"
        return base

    if official.record.contest_id != canonical.contest_id:
        base["status"] = OFFICIAL_INVALID_RESPONSE
        base["error"] = (
            "UNEXPECTED_CONTEST_ID:"
            f"requested={canonical.contest_id}:received={official.record.contest_id}"
        )
        return base

    base["official_draw_date"] = official.record.draw_date.isoformat()
    base["official_numbers"] = list(official.record.numbers)
    base["official_record_sha256"] = _record_sha256(official.record)

    differences: list[dict[str, object]] = []
    if official.record.draw_date != canonical.draw_date:
        differences.append(
            {
                "field": "draw_date",
                "canonical": canonical.draw_date.isoformat(),
                "official": official.record.draw_date.isoformat(),
            }
        )
    if official.record.numbers != canonical.numbers:
        differences.append(
            {
                "field": "numbers",
                "canonical": list(canonical.numbers),
                "official": list(official.record.numbers),
            }
        )

    base["differences"] = differences
    base["status"] = OFFICIAL_DIVERGENCE if differences else OFFICIAL_MATCH
    return base


def _status_counts(entries: Iterable[dict[str, object]]) -> dict[str, int]:
    counts = {
        OFFICIAL_MATCH: 0,
        OFFICIAL_DIVERGENCE: 0,
        OFFICIAL_UNAVAILABLE: 0,
        OFFICIAL_INVALID_RESPONSE: 0,
    }
    for entry in entries:
        status = str(entry.get("status"))
        if status in counts:
            counts[status] += 1
    return counts


def _raw_path(raw_dir: Path, contest_id: int) -> Path:
    return raw_dir / f"{contest_id:06d}.json"


def _raw_is_valid(entry: dict[str, object], raw_dir: Path) -> bool:
    expected = entry.get("raw_payload_sha256")
    if not isinstance(expected, str) or not expected:
        return False
    path = _raw_path(raw_dir, int(entry["contest_id"]))
    return path.is_file() and _sha256_bytes(path.read_bytes()) == expected


def _build_output(
    *,
    canonical_path: Path,
    start: int,
    end: int,
    entries: list[dict[str, object]],
    raw_dir: Path,
) -> dict[str, object]:
    counts = _status_counts(entries)
    expected = end - start + 1
    raw_complete = len(entries) == expected and all(_raw_is_valid(entry, raw_dir) for entry in entries)
    all_match = len(entries) == expected and counts[OFFICIAL_MATCH] == expected
    full_history = start == 1 and end == len(load_canonical_history(canonical_path))
    if all_match and raw_complete:
        status = (
            OFFICIAL_HISTORY_RECONCILIATION_PASS
            if full_history
            else OFFICIAL_HISTORY_RECONCILIATION_SHARD_PASS
        )
    else:
        status = OFFICIAL_HISTORY_RECONCILIATION_FAIL

    payload: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_file_sha256": _sha256_bytes(canonical_path.read_bytes()),
        "canonical_contests": len(load_canonical_history(canonical_path)),
        "range": {"start": start, "end": end, "expected": expected},
        "counts": counts,
        "raw_evidence_complete": raw_complete,
        "entries": sorted(entries, key=lambda item: int(item["contest_id"])),
    }
    payload["manifest_sha256"] = _sha256_bytes(_canonical_bytes(payload))
    return payload


def reconcile_history_range(
    canonical_path: Path,
    *,
    start: int,
    end: int,
    out_path: Path,
    raw_dir: Path,
    checkpoint_every: int = 25,
    delay_seconds: float = 0.0,
    timeout: float = 20.0,
    retries: int = 3,
    backoff_seconds: float = 0.5,
    opener: Callable[..., Any] = urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    records = load_canonical_history(canonical_path)
    if start < 1 or end < start or end > len(records):
        raise ValueError(
            f"invalid reconciliation range: start={start} end={end} canonical_contests={len(records)}"
        )
    if checkpoint_every <= 0:
        raise ValueError("checkpoint_every must be positive")
    if delay_seconds < 0:
        raise ValueError("delay_seconds cannot be negative")

    raw_dir.mkdir(parents=True, exist_ok=True)
    existing: dict[int, dict[str, object]] = {}
    if out_path.exists():
        try:
            previous = json.loads(out_path.read_text(encoding="utf-8"))
            if previous.get("canonical_file_sha256") == _sha256_bytes(canonical_path.read_bytes()):
                for entry in previous.get("entries", []):
                    if isinstance(entry, dict) and "contest_id" in entry:
                        existing[int(entry["contest_id"])] = entry
        except Exception:
            existing = {}

    entries: list[dict[str, object]] = []
    fetched_since_checkpoint = 0
    for contest_id in range(start, end + 1):
        canonical = records[contest_id - 1]
        prior = existing.get(contest_id)
        if (
            prior is not None
            and prior.get("status") == OFFICIAL_MATCH
            and prior.get("canonical_record_sha256") == _record_sha256(canonical)
            and _raw_is_valid(prior, raw_dir)
        ):
            entries.append(prior)
            continue

        response = fetch_official_raw(
            contest_id,
            timeout=timeout,
            retries=retries,
            backoff_seconds=backoff_seconds,
            opener=opener,
            sleep=sleep,
        )
        if response.raw_bytes:
            _atomic_write_bytes(_raw_path(raw_dir, contest_id), response.raw_bytes)
        entry = reconcile_record(canonical, response)
        entries.append(entry)
        fetched_since_checkpoint += 1

        if fetched_since_checkpoint >= checkpoint_every:
            _atomic_write_json(
                out_path,
                _build_output(
                    canonical_path=canonical_path,
                    start=start,
                    end=end,
                    entries=entries,
                    raw_dir=raw_dir,
                ),
            )
            fetched_since_checkpoint = 0

        if delay_seconds:
            sleep(delay_seconds)

    result = _build_output(
        canonical_path=canonical_path,
        start=start,
        end=end,
        entries=entries,
        raw_dir=raw_dir,
    )
    _atomic_write_json(out_path, result)
    return result


def _verify_manifest_hash(payload: dict[str, object]) -> None:
    observed = payload.get("manifest_sha256")
    unsigned = dict(payload)
    unsigned.pop("manifest_sha256", None)
    expected = _sha256_bytes(_canonical_bytes(unsigned))
    if observed != expected:
        raise RuntimeError("reconciliation manifest hash mismatch")


def merge_reconciliation_outputs(
    canonical_path: Path,
    input_paths: Iterable[Path],
    *,
    out_path: Path,
) -> dict[str, object]:
    records = load_canonical_history(canonical_path)
    canonical_sha = _sha256_bytes(canonical_path.read_bytes())
    by_id: dict[int, dict[str, object]] = {}
    shard_manifests: list[dict[str, object]] = []

    paths = tuple(input_paths)
    if not paths:
        raise RuntimeError("no reconciliation shard inputs")

    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        _verify_manifest_hash(payload)
        if payload.get("canonical_file_sha256") != canonical_sha:
            raise RuntimeError(f"canonical file hash mismatch in shard: {path}")
        if not payload.get("raw_evidence_complete"):
            raise RuntimeError(f"raw evidence incomplete in shard: {path}")

        raw_dir = path.parent / "raw"
        for entry in payload.get("entries", []):
            contest_id = int(entry["contest_id"])
            if contest_id in by_id:
                raise RuntimeError(f"duplicate contest across reconciliation shards: {contest_id}")
            canonical = records[contest_id - 1]
            if entry.get("canonical_record_sha256") != _record_sha256(canonical):
                raise RuntimeError(f"canonical record hash mismatch for contest {contest_id}")
            if not _raw_is_valid(entry, raw_dir):
                raise RuntimeError(f"raw evidence hash mismatch for contest {contest_id}")
            by_id[contest_id] = entry

        shard_manifests.append(
            {
                "path": str(path),
                "manifest_sha256": payload["manifest_sha256"],
                "range": payload["range"],
                "status": payload["status"],
            }
        )

    expected_ids = set(range(1, len(records) + 1))
    observed_ids = set(by_id)
    missing = sorted(expected_ids - observed_ids)
    extra = sorted(observed_ids - expected_ids)
    if missing or extra:
        raise RuntimeError(
            f"reconciliation coverage mismatch: missing={missing[:20]} extra={extra[:20]}"
        )

    entries = [by_id[contest_id] for contest_id in range(1, len(records) + 1)]
    counts = _status_counts(entries)
    status = (
        OFFICIAL_HISTORY_RECONCILIATION_PASS
        if counts[OFFICIAL_MATCH] == len(records)
        else OFFICIAL_HISTORY_RECONCILIATION_FAIL
    )

    result: dict[str, object] = {
        "schema_version": 1,
        "status": status,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "canonical_file_sha256": canonical_sha,
        "canonical_contests": len(records),
        "coverage": {
            "expected": len(records),
            "observed": len(entries),
            "missing": 0,
            "extra": 0,
        },
        "counts": counts,
        "raw_evidence_complete": True,
        "shards": shard_manifests,
        "entries": entries,
    }
    result["manifest_sha256"] = _sha256_bytes(_canonical_bytes(result))
    _atomic_write_json(out_path, result)
    return result
