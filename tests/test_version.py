from importlib.metadata import version

from sare_lotofacil import __version__
from sare_lotofacil.api.app import create_app


def test_release_version_is_consistent(tmp_path) -> None:
    expected = "1.1.10"
    assert version("sare-lotofacil") == expected
    assert __version__ == expected
    assert create_app(tmp_path / "version.db").version == expected
