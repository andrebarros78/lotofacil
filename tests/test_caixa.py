from datetime import datetime, timezone

from sare_lotofacil.ingestion.caixa import parse_caixa_payload


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
