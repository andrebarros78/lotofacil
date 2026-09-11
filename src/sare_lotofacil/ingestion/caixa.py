from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable
from urllib.request import Request, urlopen

from sare_lotofacil.ingestion.validation import ContestRecord, validate_contest

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil"


@dataclass(frozen=True, slots=True)
class PrizeTier:
    hits: int
    winners: int
    prize_cents: int


@dataclass(frozen=True, slots=True)
class CaixaContest:
    record: ContestRecord
    prize_tiers: tuple[PrizeTier, ...]
    source_url: str
    captured_at: datetime
    raw_payload: dict[str, Any]


def _money_to_cents(value: Any) -> int:
    amount = Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(amount * 100)


def _hits_from_description(description: str) -> int:
    token = description.strip().split()[0]
    hits = int(token)
    if hits not in {11, 12, 13, 14, 15}:
        raise ValueError(f"faixa de prêmio inválida: {description!r}")
    return hits


def parse_caixa_payload(payload: dict[str, Any], *, source_url: str = BASE_URL, captured_at: datetime | None = None) -> CaixaContest:
    if payload.get("tipoJogo") != "LOTOFACIL":
        raise ValueError("payload não identificado como LOTOFACIL")
    contest_id = int(payload["numero"])
    draw_date = datetime.strptime(payload["dataApuracao"], "%d/%m/%Y").date()
    numbers = tuple(int(value) for value in payload["listaDezenas"])
    record = validate_contest(contest_id, draw_date, numbers)

    tiers = []
    for item in payload.get("listaRateioPremio") or []:
        hits = _hits_from_description(str(item["descricaoFaixa"]))
        winners = int(item["numeroDeGanhadores"])
        if winners < 0:
            raise ValueError("número de ganhadores não pode ser negativo")
        tiers.append(PrizeTier(hits=hits, winners=winners, prize_cents=_money_to_cents(item.get("valorPremio"))))
    tiers.sort(key=lambda tier: tier.hits, reverse=True)

    capture = captured_at or datetime.now(timezone.utc)
    if capture.tzinfo is None:
        raise ValueError("captured_at precisa conter timezone")
    return CaixaContest(
        record=record,
        prize_tiers=tuple(tiers),
        source_url=source_url,
        captured_at=capture,
        raw_payload=dict(payload),
    )


def fetch_caixa_contest(
    contest_id: int | None = None,
    *,
    timeout: float = 15.0,
    opener: Callable[..., Any] = urlopen,
) -> CaixaContest:
    if contest_id is not None and (not isinstance(contest_id, int) or isinstance(contest_id, bool) or contest_id <= 0):
        raise ValueError("contest_id deve ser inteiro positivo")
    url = BASE_URL if contest_id is None else f"{BASE_URL}/{contest_id}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "SARE-Lotofacil/0.1"})
    with opener(request, timeout=timeout) as response:
        raw = response.read()
    payload = json.loads(raw.decode("utf-8"))
    return parse_caixa_payload(payload, source_url=url)
