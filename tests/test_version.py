from importlib.metadata import version

from sare_lotofacil import __version__
from sare_lotofacil.api.app import create_app


def test_release_version_is_consistent(tmp_path) -> None:
    expected_package = "1.1.1"
    expected_api_contract = "1.1.0"
    assert version("sare-lotofacil") == expected_package
    assert __version__ == expected_package
    assert create_app(tmp_path / "version.db").version == expected_api_contract
