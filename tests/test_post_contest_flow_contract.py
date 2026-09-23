from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_post_contest_flow_contract.py"
spec = importlib.util.spec_from_file_location("post_contest_contract", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)
verify_contract = module.verify_contract


def _write_state(root: Path, *, contest: int = 3786, emitted: bool = True) -> None:
    report = {
        "contest_number": contest,
        "self_analysis": {
            "process_findings": ["auditado"],
            "corrections_required": ["nenhuma correção obrigatória"],
            "adjustments_suggested": ["acompanhar coorte prospectiva"],
            "implementations_suggested": ["persistir relatório"],
        },
    }
    latest = {
        "official_latest_contest": contest,
        "inserted_official_contests": [contest],
        "post_contest_report": {"emitted_for_contests": [contest] if emitted else []},
    }
    reports = {"latest_contest": contest, "latest_report": report}
    ledger = {"predictions": [{"target_contest": contest, "evaluation": {"observed_contest": contest}}]}
    files = {
        "latest.json": latest,
        "post_contest_reports.json": reports,
        "latest_post_contest_report.json": report,
        "prospective_ledger.json": ledger,
    }
    for name, payload in files.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    (root / "latest_post_contest_report.md").write_text(
        f"# Análise Pós-Concurso\n\n- Concurso Número: {contest}\n", encoding="utf-8"
    )


def test_contract_requires_complete_audit_report_and_delivery(tmp_path: Path) -> None:
    _write_state(tmp_path)
    result = verify_contract(tmp_path)
    assert result["status"] == "POST_CONTEST_FLOW_CONTRACT_PASS"
    assert result["official_latest_contest"] == 3786
    assert result["audited"] is True
    assert result["report_persisted"] is True
    assert result["report_deliverable"] is True
    assert result["improvement_suggestions_present"] is True


def test_contract_fails_if_ingested_contest_has_no_emitted_report(tmp_path: Path) -> None:
    _write_state(tmp_path, emitted=False)
    with pytest.raises(RuntimeError, match="INSERTED_WITHOUT_REPORT"):
        verify_contract(tmp_path)
