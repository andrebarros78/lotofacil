# R3 — Merge Gates Governance — PROVEN

stage_id: R3
status: PROVEN
implementation_sha: a74fbb1cd211b0aa5d328a31bfb38c286d6b11c6
positive_probe_merge_sha: 6e584ab90a053c6e0ec4aa9f9974b8d6a46a09ff
started_at_utc: 2026-09-17T21:33:00Z
completed_at_utc: 2026-09-17T21:41:00Z
reviewed_against_invariants: true
open_blockers: []

## Requirements proved

The canonical merge authority for `main` is consolidated into exactly five stable required contexts:

1. `CI`
2. `Scientific Gate`
3. `Operational Integrity Gate`
4. `Security/Sanitization Gate`
5. `Release Candidate Gate`

`Release Candidate Gate` depends on the CI, scientific, operational and security jobs. The versioned contract is `governance/merge-gates.json`; `scripts/verify_merge_gates.py` fails closed if a stable gate is removed/renamed or if the release-candidate dependency chain is relaxed.

## Implementation

- PR #75 integrated `.github/workflows/merge-gates.yml`, governance contract, verifier and negative unit tests.
- Initial verifier test exposed a substring-matching defect; the verifier was corrected to require exact stable job names and the entire workflow was rerun.
- Successful stable-gate proof run: GitHub Actions run `35277658178`.
- Existing CI, Repository Sanitization and Agent PR Pipeline Proof also succeeded on the corrected PR head.
- PR #75 merged to `main` as `a74fbb1cd211b0aa5d328a31bfb38c286d6b11c6`.

## Effective repository protection

Ruleset `SARE Main Protection`, id `23459135`, is active on `refs/heads/main`, has no bypass actor and uses strict required-status-check enforcement. Its required contexts are exactly the five stable names listed above.

## Negative behavioral proof

PR #76 (`test(r3): controlled negative required-gate probe`) intentionally introduced `R3_NEGATIVE_REQUIRED_GATE_PROBE` in the Challenger test suite.

Observed behavior:

- `Scientific Gate` concluded `failure`.
- A direct squash-merge attempt was rejected by GitHub with HTTP 405 and `Repository rule violations found` because required status checks had not succeeded.
- PR #76 was then closed unmerged.

Result: a failing required scientific gate demonstrably blocks merge.

## Positive behavioral proof

PR #77 (`test(r3): controlled positive required-gates probe`) was documentation-only.

Observed stable contexts in run `35278009110`:

- `CI`: success
- `Scientific Gate`: success
- `Operational Integrity Gate`: success
- `Security/Sanitization Gate`: success
- `Release Candidate Gate`: success

Only after all five succeeded, GitHub accepted the protected squash merge. PR #77 merged as `6e584ab90a053c6e0ec4aa9f9974b8d6a46a09ff`.

Result: compliant changes can merge after all required stable gates succeed.

## Negative contract tests

- removing/renaming `Scientific Gate` => contract verifier fails closed;
- removing a Release Candidate dependency => contract verifier fails closed.

## Known limitations

Specialized workflows remain in the repository for deeper evidence and operational missions. They no longer define the stable merge-authority interface; the five required contexts above do. Future governance changes must preserve the contract or intentionally version/reprove it.

## Conclusion

R3 exit gate is satisfied: the five stable checks are real, required by the active main ruleset, a controlled failing PR was blocked, and a controlled passing PR was allowed only after all required checks succeeded.

NEXT_REQUIRED_STAGE: R4 — Release engineering and formal Release.
CONSTRUCTION_PROVEN: FALSE
