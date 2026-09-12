from __future__ import annotations

import json
import sare_lotofacil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from sare_lotofacil.api.app import create_app
from sare_lotofacil.experiments.protocol import ExperimentProtocol
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.backup import backup_database, database_integrity, restore_database
from sare_lotofacil.persistence.evidence import verify_source_artifacts
from sare_lotofacil.persistence.jobs import enqueue_job, run_worker_once
from sare_lotofacil.persistence.operations import evaluate_portfolio, get_portfolio, persist_uniform_portfolio
from sare_lotofacil.persistence.repository import create_latest_snapshot, persist_history_records
from sare_lotofacil.persistence.workflows import execute_experiment, get_experiment, get_hypothesis, promote_model, register_hypothesis
from sare_lotofacil.simulation.null import simulate_uniform_draws


def main() -> int:
    module_path = Path(sare_lotofacil.__file__).resolve()
    if "/tmp/sare-clean" in str(Path.cwd()) or Path("/tmp/sare-clean").exists():
        assert "site-packages" in str(module_path), module_path

    with TemporaryDirectory(prefix="sare-release-proof-") as temp_dir:
        root = Path(temp_dir)
        db = root / "sare.db"
        backup = root / "sare.backup.db"
        restored = root / "sare.restored.db"

        draws = simulate_uniform_draws(105, seed=20260911).draws
        first_date = date(2026, 1, 1)
        records = tuple(
            validate_contest(index, first_date + timedelta(days=index - 1), numbers)
            for index, numbers in enumerate(draws, start=1)
        )
        raw_bytes = ("\n".join(f"{record.contest_id}:{','.join(map(str, record.numbers))}" for record in records)).encode("utf-8")
        bulk = persist_history_records(
            db,
            records,
            source_url="proof://synthetic-history",
            raw_bytes=raw_bytes,
            captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            source_class="SINTETICO_PROVA_RELEASE",
            media_type="text/plain",
        )
        assert bulk.inserted == 105
        assert database_integrity(db) == "ok"
        assert all(check.valid for check in verify_source_artifacts(db))

        snapshot = create_latest_snapshot(db)
        assert snapshot.contest_count == 105

        protocol = ExperimentProtocol(
            hypothesis_id="H-RELEASE-001",
            question="M1 ou M2 melhora Brier contra M0 no snapshot congelado?",
            h0="Delta Brier <= 0",
            h1="Delta Brier > 0",
            snapshot_id=snapshot.snapshot_id,
            variables="presenca marginal de cada dezena usando apenas passado",
            model="M1 frequencia regularizada e M2 media exponencial",
            comparators=("uniform_p_0_6", "frequency_regularized", "exponential"),
            multiplicity_family="familia primaria registrada com Holm",
            sample_plan="walk-forward no snapshot congelado",
            stopping_rule="snapshot fixo sem parada oportunista",
            code_environment="wheel instalado em ambiente limpo GitHub Actions Python 3.13",
            delta_min=0.0001,
            min_train=100,
        )
        hypothesis = register_hypothesis(db, protocol)
        assert hypothesis.status == "REGISTERED"
        experiment = execute_experiment(db, hypothesis.hypothesis_id)
        assert experiment.conclusion == "EVIDENCIA_PREDITIVA_INSUFICIENTE"
        assert experiment.predictive_evidence == "NOT_ESTABLISHED"

        promotion_blocked = False
        try:
            promote_model(db, experiment.experiment_id, "M1")
        except PermissionError as exc:
            assert str(exc) == "PREDICTIVE_EVIDENCE_NOT_REPLICATED"
            promotion_blocked = True
        assert promotion_blocked

        portfolio = persist_uniform_portfolio(db, card_count=3, seed=17, snapshot_id=snapshot.snapshot_id, target_contest=106)
        assert portfolio.predictive_evidence == "NOT_ESTABLISHED"
        assert "SEM VANTAGEM PREDITIVA COMPROVADA" in portfolio.evidence_label
        evaluation = evaluate_portfolio(db, portfolio.portfolio_id, draws[-1])
        assert len(evaluation.hits) == 3

        queued = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 99, "snapshot_id": snapshot.snapshot_id, "target_contest": 106})
        assert queued.state == "QUEUED"
        worked = run_worker_once(db, "release-worker", lease_seconds=30)
        assert worked and worked.job_id == queued.job_id and worked.state == "COMPLETED"

        backup_info = backup_database(db, backup)
        assert backup_info.integrity == "ok"
        restore_info = restore_database(backup, restored)
        assert restore_info.integrity == "ok"
        assert database_integrity(restored) == "ok"

        assert get_hypothesis(restored, hypothesis.hypothesis_id).protocol_hash == hypothesis.protocol_hash
        assert get_experiment(restored, experiment.experiment_id) == experiment
        restored_portfolio = get_portfolio(restored, portfolio.portfolio_id)
        assert restored_portfolio == portfolio

        app = create_app(restored, write_token="release-proof")
        paths = {route.path for route in app.routes}
        required_paths = {
            "/health/live", "/health/ready", "/v1/contests", "/v1/ingestions/caixa", "/v1/snapshots",
            "/v1/hypotheses", "/v1/experiments", "/v1/promotions", "/v1/analyses", "/v1/portfolios",
            "/v1/evaluations", "/v1/ris", "/v1/jobs", "/v1/jobs/{job_id}/cancel", "/v1/evidence/integrity",
        }
        assert required_paths <= paths

        result = {
            "status": "OPERATIONAL_RELEASE_PROOF_PASS",
            "installed_module": str(module_path),
            "database_integrity": database_integrity(restored),
            "snapshot_contests": snapshot.contest_count,
            "hypothesis_status": get_hypothesis(restored, hypothesis.hypothesis_id).status,
            "experiment_conclusion": experiment.conclusion,
            "predictive_evidence": experiment.predictive_evidence,
            "promotion_without_replication_blocked": promotion_blocked,
            "portfolio_label": restored_portfolio.evidence_label,
            "backup_restore_verified": True,
            "required_api_paths_verified": len(required_paths),
            "persistent_worker_job_completed": True,
            "evidence_hashes_verified": True,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
