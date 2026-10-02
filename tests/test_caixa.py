import json
from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest

from sare_lotofacil.ingestion.caixa import fetch_caixa_contest, parse_caixa_payload


PAYLOAD = {
    "tipoJogo": "LOTOFACIL",
    "numero": 3779,
    "dataApuracao": "03/09/2026",
    "listaDezenas": ["03", "04", "05", "07", "08", "10", "11", "13", "14", "16", "17", "19", "23", "24", "25"],
    "listaRateioPremio": [
        {"descricaoFaixa": "15 acertos", "numeroDeGanhadores": 7, "valorPremio": 532221.72},
        {"descricaoFaixa": "14 acertos", "numeroDeGanhadores": 704, "valorPremio": 889.16},
        {"descricaoFaixa": "13 acertos", "numeroDeGanhadores": 17324, "valorPremio": 35.0},
        {"descricaoFaixa": "12 acertos", "numeroDeGanhadores": 179888, "valorPremio": 14.0},
        {"descricaoFaixa": "11 acertos", "numeroDeGanhadores": 847986, "valorPremio": 7.0},
    ],
}


def test_parse_observed_caixa_contract() -> None:
    contest = parse_caixa_payload(PAYLOAD, captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc))
    assert contest.record.contest_id == 3779
    assert contest.record.mask.bit_count() == 15
    assert [tier.hits for tier in contest.prize_tiers] == [15, 14, 13, 12, 11]
    assert contest.prize_tiers[0].prize_cents == 53_222_172


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


def test_fetch_caixa_contest_retries_transient_504_then_succeeds() -> None:
    calls = []
    delays = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        if len(calls) == 1:
            raise HTTPError(request.full_url, 504, "Gateway Time-out", None, None)
        return _Response(json.dumps(PAYLOAD).encode("utf-8"))

    contest = fetch_caixa_contest(3779, attempts=3, backoff_seconds=0.25, opener=opener, sleeper=delays.append)
    assert contest.record.contest_id == 3779
    assert len(calls) == 2
    assert delays == [0.25]


def test_fetch_caixa_contest_exhausts_transient_retries_fail_closed() -> None:
    calls = []
    delays = []

    def opener(request, timeout):
        calls.append((request.full_url, timeout))
        raise HTTPError(request.full_url, 504, "Gateway Time-out", None, None)

    with pytest.raises(HTTPError) as exc_info:
        fetch_caixa_contest(3779, attempts=3, backoff_seconds=0.5, opener=opener, sleeper=delays.append)

    assert exc_info.value.code == 504
    assert len(calls) == 3
    assert delays == [0.5, 1.0]
