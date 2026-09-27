from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Iterable, Sequence


_TIME_RE = re.compile(
    r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})(?:[.,](?P<ms>\d{1,3}))?"
)
_TAG_RE = re.compile(r"<[^>]+>")
_INT_RE = re.compile(r"(?<!\d)(?P<n>\d{1,2})(?!\d)")

_NUMBER_WORDS = {
    "um": 1,
    "uma": 1,
    "dois": 2,
    "duas": 2,
    "tres": 3,
    "quatro": 4,
    "cinco": 5,
    "seis": 6,
    "sete": 7,
    "oito": 8,
    "nove": 9,
    "dez": 10,
    "onze": 11,
    "doze": 12,
    "treze": 13,
    "quatorze": 14,
    "catorze": 14,
    "quinze": 15,
    "dezesseis": 16,
    "dezasseis": 16,
    "dezessete": 17,
    "dezassete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "vinte e um": 21,
    "vinte e dois": 22,
    "vinte e tres": 23,
    "vinte e quatro": 24,
    "vinte e cinco": 25,
}

_PROCEDURE_PATTERNS = {
    "LOTTERY_LOTOFACIL": ("lotofacil",),
    "CASE": ("maleta", "estojo"),
    "BALL_CHECK": ("conferencia das bolas", "conferir as bolas", "conferencia de bolas"),
    "GLOBE": ("globo",),
    "LOAD": ("carregamento", "carregar", "carregando"),
    "AUDIT": ("auditor", "auditoria", "fiscal"),
    "DRAW": ("sorteio", "sortear", "sorteando"),
    "BALL": ("bola", "bolinha", "dezena"),
    "EMPTY": ("esvaziamento", "esvaziar o globo", "retirada das bolas"),
}

_EVENT_PATTERNS = {
    "case_open": ("abrir a maleta", "abertura da maleta", "maleta aberta"),
    "ball_check": ("conferencia das bolas", "conferir as bolas", "conferencia de bolas"),
    "globe_load": ("carregamento do globo", "carregar o globo", "carregando o globo"),
    "mixing_start": ("acionar o globo", "globo acionado", "misturar as bolas", "mistura das bolas"),
    "draw_start": ("inicio do sorteio", "iniciar o sorteio", "vamos ao sorteio", "primeira bola"),
    "draw_end": ("ultima bola", "fim do sorteio", "encerrado o sorteio", "resultado da lotofacil"),
    "globe_empty": ("esvaziamento do globo", "esvaziar o globo", "retirada das bolas"),
    "case_close": ("fechar a maleta", "fechamento da maleta", "maleta fechada"),
}

_INTERVENTION_PATTERNS = {
    "MANUAL_RELEASE": ("liberacao manual", "liberar manualmente", "manualmente"),
    "RETAINED_BALL": ("bola retida", "bolinha retida", "bola presa"),
    "INTERRUPTION": ("interromper", "interrupcao", "pausa tecnica", "aguarde"),
    "MALFUNCTION": ("falha", "problema no globo", "problema tecnico", "defeito"),
    "RESTART": ("reiniciar", "recomecar", "novo sorteio"),
}

_SEQUENCE_CONTEXT = (
    "bola",
    "bolinha",
    "dezena",
    "numero",
    "saiu",
    "sorteada",
    "sorteado",
)


@dataclass(frozen=True, slots=True)
class TimedCue:
    start_seconds: float
    end_seconds: float
    text: str


@dataclass(frozen=True, slots=True)
class ProcedureAssessment:
    status: str
    complete_procedure: bool
    score: int
    lotofacil_mentions: int
    contest_mentions: int
    procedure_markers: tuple[str, ...]
    start_seconds: float | None
    end_seconds: float | None
    duration_seconds: float | None
    event_times: dict[str, float]
    intervention_flags: tuple[str, ...]
    draw_sequence: tuple[int, ...] | None
    draw_sequence_status: str
    cue_count: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PhysicalObservation:
    contest_id: int
    video_id: str
    content_status: str
    complete_procedure: bool
    segment_start_seconds: float | None
    segment_end_seconds: float | None
    segment_duration_seconds: float | None
    case_open_seconds: float | None
    ball_check_seconds: float | None
    globe_load_seconds: float | None
    mixing_start_seconds: float | None
    draw_start_seconds: float | None
    draw_end_seconds: float | None
    globe_empty_seconds: float | None
    case_close_seconds: float | None
    mixing_duration_seconds: float | None
    draw_duration_seconds: float | None
    draw_sequence: tuple[int, ...] | None
    draw_sequence_status: str
    intervention_flags: tuple[str, ...]
    procedure_markers: tuple[str, ...]
    visual_globe_fingerprint: str | None = None
    visual_ball_set_fingerprint: str | None = None
    visual_case_fingerprint: str | None = None
    visual_feature_status: str = "PENDING_FRAME_EXTRACTION"
    predictive_evidence: str = "NOT_ESTABLISHED"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_text(value: str) -> str:
    value = html.unescape(value or "")
    value = _TAG_RE.sub(" ", value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("\xa0", " ")
    return " ".join(value.split())


def _parse_timestamp(value: str) -> float:
    match = _TIME_RE.search(value.strip())
    if not match:
        raise ValueError(f"P15_VTT_TIMESTAMP_INVALID:{value}")
    h = int(match.group("h"))
    m = int(match.group("m"))
    s = int(match.group("s"))
    ms = (match.group("ms") or "0").ljust(3, "0")[:3]
    return h * 3600 + m * 60 + s + int(ms) / 1000.0


def parse_webvtt(text: str) -> tuple[TimedCue, ...]:
    """Parse the timed text subset needed by the physical observation pipeline."""

    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues: list[TimedCue] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if "-->" not in line:
            index += 1
            continue
        left, right = line.split("-->", 1)
        try:
            start = _parse_timestamp(left)
            end = _parse_timestamp(right.split()[0])
        except ValueError:
            index += 1
            continue
        index += 1
        payload: list[str] = []
        while index < len(lines) and lines[index].strip():
            payload.append(lines[index].strip())
            index += 1
        cue_text = normalize_text(" ".join(payload))
        if cue_text and end >= start:
            if cues and cues[-1].start_seconds == start and cues[-1].text == cue_text:
                index += 1
                continue
            cues.append(TimedCue(start, end, cue_text))
        index += 1
    return tuple(cues)


def _matches_any(text: str, patterns: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    return any(pattern in normalized for pattern in patterns)


def _first_match_time(cues: Sequence[TimedCue], patterns: Iterable[str]) -> float | None:
    for cue in cues:
        if _matches_any(cue.text, patterns):
            return cue.start_seconds
    return None


def _extract_markers(cues: Sequence[TimedCue]) -> tuple[str, ...]:
    joined = " ".join(cue.text for cue in cues)
    return tuple(
        marker
        for marker, patterns in _PROCEDURE_PATTERNS.items()
        if _matches_any(joined, patterns)
    )


def _segment_bounds(cues: Sequence[TimedCue]) -> tuple[float | None, float | None]:
    relevant: list[TimedCue] = []
    for cue in cues:
        text = cue.text
        if "lotofacil" in text or any(
            _matches_any(text, patterns) for patterns in _PROCEDURE_PATTERNS.values()
        ):
            relevant.append(cue)
    if not relevant:
        return None, None
    start = max(0.0, relevant[0].start_seconds - 30.0)
    end = relevant[-1].end_seconds + 30.0
    return start, end


def _extract_numbers_from_text(text: str) -> tuple[int, ...]:
    normalized = normalize_text(text)
    values: list[int] = []
    for match in _INT_RE.finditer(normalized):
        value = int(match.group("n"))
        if 1 <= value <= 25:
            values.append(value)
    for phrase, value in sorted(_NUMBER_WORDS.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            values.append(value)
    return tuple(values)


def extract_draw_sequence(
    cues: Sequence[TimedCue],
    *,
    expected_numbers: Sequence[int] | None = None,
) -> tuple[tuple[int, ...] | None, str]:
    expected = set(int(value) for value in expected_numbers or ())
    observed: list[int] = []
    for cue in cues:
        text = normalize_text(cue.text)
        candidate_context = any(token in text for token in _SEQUENCE_CONTEXT)
        numeric_only = bool(re.fullmatch(r"(?:\d{1,2}|[a-z ]{1,20})", text))
        if not candidate_context and not numeric_only:
            continue
        for value in _extract_numbers_from_text(text):
            if expected and value not in expected:
                continue
            if value not in observed:
                observed.append(value)
            if len(observed) == 15:
                break
        if len(observed) == 15:
            break

    if len(observed) != 15:
        return None, f"INCOMPLETE_{len(observed)}_OF_15"
    if expected and set(observed) != expected:
        return None, "SET_MISMATCH"
    return tuple(observed), "EXTRACTED_AND_SET_VALIDATED" if expected else "EXTRACTED_UNVALIDATED"


def assess_procedure(
    cues: Sequence[TimedCue],
    *,
    contest_id: int,
    expected_numbers: Sequence[int] | None = None,
) -> ProcedureAssessment:
    joined = " ".join(cue.text for cue in cues)
    normalized = normalize_text(joined)
    lotofacil_mentions = normalized.count("lotofacil")
    contest_mentions = len(re.findall(rf"(?<!\d){int(contest_id)}(?!\d)", normalized))
    markers = _extract_markers(cues)
    start, end = _segment_bounds(cues)
    duration = None if start is None or end is None else max(0.0, end - start)

    event_times = {
        name: value
        for name, patterns in _EVENT_PATTERNS.items()
        if (value := _first_match_time(cues, patterns)) is not None
    }
    intervention_flags = tuple(
        name
        for name, patterns in _INTERVENTION_PATTERNS.items()
        if _matches_any(joined, patterns)
    )

    sequence, sequence_status = extract_draw_sequence(cues, expected_numbers=expected_numbers)
    core_markers = {"CASE", "BALL_CHECK", "GLOBE", "LOAD", "DRAW", "BALL"}
    core_count = len(core_markers.intersection(markers))
    score = 0
    if lotofacil_mentions:
        score += 40
    if contest_mentions:
        score += 30
    score += min(40, core_count * 8)
    if duration is not None and duration >= 45:
        score += 10
    if "CASE" in markers and "GLOBE" in markers and "DRAW" in markers:
        score += 15
    if sequence is not None:
        score += 15

    complete = bool(
        lotofacil_mentions
        and core_count >= 3
        and duration is not None
        and duration >= 45
        and ("DRAW" in markers or "BALL" in markers)
    )
    if not cues:
        status = "NO_TIMED_TEXT"
    elif complete:
        status = "COMPLETE_PROCEDURE_EVIDENCE"
    elif lotofacil_mentions:
        status = "PARTIAL_LOTOFACIL_CONTENT"
    else:
        status = "NO_LOTOFACIL_CONTENT_EVIDENCE"

    return ProcedureAssessment(
        status=status,
        complete_procedure=complete,
        score=score,
        lotofacil_mentions=lotofacil_mentions,
        contest_mentions=contest_mentions,
        procedure_markers=markers,
        start_seconds=start,
        end_seconds=end,
        duration_seconds=duration,
        event_times=event_times,
        intervention_flags=intervention_flags,
        draw_sequence=sequence,
        draw_sequence_status=sequence_status,
        cue_count=len(cues),
    )


def observation_from_assessment(
    *,
    contest_id: int,
    video_id: str,
    assessment: ProcedureAssessment,
) -> PhysicalObservation:
    events = assessment.event_times
    mixing_duration = None
    if "mixing_start" in events and "draw_start" in events:
        delta = events["draw_start"] - events["mixing_start"]
        if delta >= 0:
            mixing_duration = delta
    draw_duration = None
    if "draw_start" in events and "draw_end" in events:
        delta = events["draw_end"] - events["draw_start"]
        if delta >= 0:
            draw_duration = delta

    return PhysicalObservation(
        contest_id=contest_id,
        video_id=video_id,
        content_status=assessment.status,
        complete_procedure=assessment.complete_procedure,
        segment_start_seconds=assessment.start_seconds,
        segment_end_seconds=assessment.end_seconds,
        segment_duration_seconds=assessment.duration_seconds,
        case_open_seconds=events.get("case_open"),
        ball_check_seconds=events.get("ball_check"),
        globe_load_seconds=events.get("globe_load"),
        mixing_start_seconds=events.get("mixing_start"),
        draw_start_seconds=events.get("draw_start"),
        draw_end_seconds=events.get("draw_end"),
        globe_empty_seconds=events.get("globe_empty"),
        case_close_seconds=events.get("case_close"),
        mixing_duration_seconds=mixing_duration,
        draw_duration_seconds=draw_duration,
        draw_sequence=assessment.draw_sequence,
        draw_sequence_status=assessment.draw_sequence_status,
        intervention_flags=assessment.intervention_flags,
        procedure_markers=assessment.procedure_markers,
    )
