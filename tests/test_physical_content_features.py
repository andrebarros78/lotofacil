from __future__ import annotations

from sare_lotofacil.physical.content_features import (
    assess_procedure,
    observation_from_assessment,
    parse_webvtt,
)
from sare_lotofacil.physical.frame_features import average_hash_gray, hamming_distance_hex


def _vtt() -> str:
    return """WEBVTT

00:00:10.000 --> 00:00:15.000
Agora a Lotofácil concurso 3790.

00:00:20.000 --> 00:00:27.000
Abertura da maleta e conferência das bolas.

00:00:35.000 --> 00:00:42.000
Carregamento do globo pelos auditores.

00:01:00.000 --> 00:01:05.000
Vamos ao sorteio. Primeira bola número 1.

00:01:08.000 --> 00:01:11.000
Bola número 2.

00:01:14.000 --> 00:01:17.000
Bola número 3.

00:01:20.000 --> 00:01:23.000
Bola número 4.

00:01:26.000 --> 00:01:29.000
Bola número 5.

00:01:32.000 --> 00:01:35.000
Bola número 6.

00:01:38.000 --> 00:01:41.000
Bola número 7.

00:01:44.000 --> 00:01:47.000
Bola número 8.

00:01:50.000 --> 00:01:53.000
Bola número 9.

00:01:56.000 --> 00:01:59.000
Bola número 10.

00:02:02.000 --> 00:02:05.000
Bola número 11.

00:02:08.000 --> 00:02:11.000
Bola número 12.

00:02:14.000 --> 00:02:17.000
Bola número 13.

00:02:20.000 --> 00:02:23.000
Bola número 14.

00:02:26.000 --> 00:02:30.000
Última bola número 15. Fim do sorteio.

00:02:40.000 --> 00:02:45.000
Esvaziamento do globo e fechamento da maleta.
"""


def test_timed_content_extracts_complete_procedure_and_sequence() -> None:
    cues = parse_webvtt(_vtt())
    assessment = assess_procedure(cues, contest_id=3790, expected_numbers=tuple(range(1, 16)))

    assert assessment.complete_procedure is True
    assert assessment.status == "COMPLETE_PROCEDURE_EVIDENCE"
    assert assessment.contest_mentions >= 1
    assert {"CASE", "BALL_CHECK", "GLOBE", "LOAD", "DRAW", "BALL"}.issubset(assessment.procedure_markers)
    assert assessment.draw_sequence == tuple(range(1, 16))
    assert assessment.draw_sequence_status == "EXTRACTED_AND_SET_VALIDATED"

    observation = observation_from_assessment(contest_id=3790, video_id="video", assessment=assessment)
    assert observation.segment_duration_seconds is not None
    assert observation.draw_sequence == tuple(range(1, 16))
    assert observation.predictive_evidence == "NOT_ESTABLISHED"


def test_partial_content_does_not_claim_complete_procedure() -> None:
    cues = parse_webvtt("""WEBVTT

00:00:01.000 --> 00:00:03.000
Lotofácil concurso 3790.
""")
    assessment = assess_procedure(cues, contest_id=3790)
    assert assessment.complete_procedure is False
    assert assessment.status == "PARTIAL_LOTOFACIL_CONTENT"


def test_average_hash_is_deterministic_and_hamming_distance_zero_for_same_frame() -> None:
    raw = bytes(range(256))
    left = average_hash_gray(raw)
    right = average_hash_gray(raw)
    assert left.average_hash_hex == right.average_hash_hex
    assert len(left.average_hash_hex) == 64
    assert hamming_distance_hex(left.average_hash_hex, right.average_hash_hex) == 0
