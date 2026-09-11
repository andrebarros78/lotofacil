from sare_lotofacil.cli import build_parser


def test_operational_core_commands_are_exposed() -> None:
    parser = build_parser()
    commands = [
        ["doctor"],
        ["init-db", "--path", "x.db"],
        ["fetch-caixa", "--db", "x.db", "--contest", "1"],
        ["snapshot", "--db", "x.db"],
        ["analyze-snapshot", "--db", "x.db", "--snapshot", "snap-x"],
        ["validate-history", "--path", "history.md"],
        ["analyze-history", "--path", "history.md"],
        ["backup-db", "--db", "x.db", "--out", "backup.db"],
        ["restore-db", "--backup", "backup.db", "--out", "restored.db"],
        ["serve", "--db", "x.db"],
    ]
    assert [parser.parse_args(command).command for command in commands] == [command[0] for command in commands]
