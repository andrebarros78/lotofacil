from sare_lotofacil.cli import doctor


def test_doctor_passes(capsys) -> None:
    assert doctor() == 0
    captured = capsys.readouterr()
    assert "MATHEMATICAL_CHECKS_PASS" in captured.out
