from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
LEDGER_REL = Path("governance/agents/post_merge_proof_confirmations.json")
GAPS_REL = Path("governance/agents/capability_gaps.json")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(root: Path = DEFAULT_ROOT) -> dict:
    root = Path(root)
    agents_dir = root / "governance" / "agents"
    ledger_path = root / LEDGER_REL
    gaps_path = root / GAPS_REL

    require(ledger_path.is_file(), "post-merge confirmation ledger missing")
    require(gaps_path.is_file(), "capability gap registry missing")

    ledger = load_json(ledger_path)
    gaps_doc = load_json(gaps_path)

    require(ledger.get("schema_version") == 1, "unsupported post-merge confirmation schema")
    require(ledger.get("authority") == "GITHUB_ONLY", "post-merge confirmation authority drift")

    policy = ledger.get("policy", {})
    require(policy.get("mode") == "APPEND_ONLY_POST_MERGE_CONFIRMATION", "post-merge confirmation mode drift")
    require(policy.get("historical_proof_mutation_forbidden") is True, "historical proof mutation guard disabled")
    require(policy.get("claim_expansion_forbidden") is True, "claim expansion guard disabled")
    require(policy.get("authority_expansion_forbidden") is True, "authority expansion guard disabled")

    gaps = gaps_doc.get("gaps", [])
    gap_ids = [gap.get("id") for gap in gaps]
    require(None not in gap_ids, "capability gap without id")
    require(len(gap_ids) == len(set(gap_ids)), "duplicate capability gap id")
    gap_by_id = {gap["id"]: gap for gap in gaps}

    confirmations = ledger.get("confirmations", [])
    require(confirmations, "post-merge confirmation ledger is empty")
    confirmation_ids = [item.get("confirmation_id") for item in confirmations]
    require(None not in confirmation_ids, "post-merge confirmation without id")
    require(len(confirmation_ids) == len(set(confirmation_ids)), "duplicate post-merge confirmation id")

    for item in confirmations:
        confirmation_id = item["confirmation_id"]
        gap_id = item.get("gap_id")
        require(gap_id in gap_by_id, f"unknown gap in post-merge confirmation: {confirmation_id}")

        registry_status = gap_by_id[gap_id].get("status")
        require(
            item.get("registry_status") == registry_status,
            f"registry status mismatch for {confirmation_id}",
        )

        history_name = item.get("proof_history_file")
        require(
            isinstance(history_name, str) and history_name.endswith("_proof_history.json"),
            f"invalid proof history reference for {confirmation_id}",
        )
        history_path = agents_dir / history_name
        require(history_path.is_file(), f"proof history missing for {confirmation_id}")

        history_doc = load_json(history_path)
        proofs = history_doc.get("proofs", [])
        proof_id = item.get("proof_id")
        proof = next((candidate for candidate in proofs if candidate.get("proof_id") == proof_id), None)
        require(proof is not None, f"proof id not found for {confirmation_id}")
        require(proof.get("gap_id") == gap_id, f"proof gap mismatch for {confirmation_id}")
        require(proof.get("decision") == registry_status, f"proof decision mismatch for {confirmation_id}")
        proof_authority = history_doc.get("authority") or proof.get("authority")
        require(proof_authority == "GITHUB_ONLY", f"proof authority drift for {confirmation_id}")

        original = item.get("original_confirmatory_evidence", {})
        proof_evidence = proof.get("confirmatory_evidence") or proof.get("evidence") or {}
        for key in ("workflow_run_id", "artifact_id", "artifact_digest"):
            require(
                original.get(key) == proof_evidence.get(key),
                f"original evidence mismatch ({key}) for {confirmation_id}",
            )
        if "github_sha" in original:
            require(
                original.get("github_sha") == proof_evidence.get("github_sha"),
                f"original evidence mismatch (github_sha) for {confirmation_id}",
            )
        require(SHA40.fullmatch(str(original.get("github_sha", ""))) is not None, f"invalid original github sha for {confirmation_id}")
        require(SHA256.fullmatch(str(original.get("artifact_digest", ""))) is not None, f"invalid original artifact digest for {confirmation_id}")

        post = item.get("post_merge_confirmation", {})
        require(int(post.get("governance_pr_number", 0)) > 0, f"invalid governance PR for {confirmation_id}")
        require(SHA40.fullmatch(str(post.get("canonical_main_sha", ""))) is not None, f"invalid post-merge main sha for {confirmation_id}")
        require(post.get("canonical_main_sha") != original.get("github_sha"), f"post-merge sha must differ from original proof sha for {confirmation_id}")
        require(bool(post.get("workflow_name")), f"post-merge workflow name missing for {confirmation_id}")
        require(int(post.get("workflow_run_id", 0)) > 0, f"invalid post-merge workflow run for {confirmation_id}")
        require(post.get("workflow_conclusion") == "success", f"post-merge workflow is not successful for {confirmation_id}")
        require(int(post.get("artifact_id", 0)) > 0, f"invalid post-merge artifact id for {confirmation_id}")
        require(bool(post.get("artifact_name")), f"post-merge artifact name missing for {confirmation_id}")
        require(SHA256.fullmatch(str(post.get("artifact_digest", ""))) is not None, f"invalid post-merge artifact digest for {confirmation_id}")

        effect = item.get("governance_effect", {})
        require(effect.get("status_changed") is False, f"status mutation forbidden for {confirmation_id}")
        require(effect.get("claim_expanded") is False, f"claim expansion forbidden for {confirmation_id}")
        require(effect.get("runtime_framework_changed") is False, f"runtime framework mutation forbidden for {confirmation_id}")
        require(effect.get("new_authority_granted") is False, f"authority expansion forbidden for {confirmation_id}")

    return {
        "status": "POST_MERGE_PROOF_CONFIRMATIONS_PASS",
        "authority": ledger["authority"],
        "confirmations": len(confirmations),
        "gaps_linked": len({item["gap_id"] for item in confirmations}),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate append-only post-merge proof confirmations")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    print(json.dumps(validate(args.root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
