# R5 — GitHub-only Disaster Recovery — PROVEN

stage_id: R5
status: PROVEN
implementation_final_sha: 6ac8af392530b23ef19ddc6b049b316bdf017591
release_tag: v1.1.10
release_sha: 07fdcf624c275f554caeac31e70dc1a34b8e99d9
operations_state_sha: 15be04a957a81aae8e92b6ae97e7ad26bc626a05
successful_dr_run_id: 35281917468
successful_dr_artifact_id: 10522980038
successful_dr_artifact_digest: sha256:75765137c798969f7cfb565efd5b191149cad3b5daf073d62a0d8e6273dbf66f
completed_at_utc: 2026-09-17T22:25:50Z
reviewed_against_invariants: true
open_blockers: []

## Recovery scenario proved

The canonical GitHub-only recovery ran on a fresh GitHub-hosted Ubuntu runner and recovered the formal release and operational state without relying on a resident PC, VPS, or pre-existing runtime.

The successful run performed:

1. clean checkout of the current control plane;
2. clean checkout of formal release `v1.1.10`;
3. clean checkout of `operations/state`;
4. download of the formal GitHub Release assets;
5. recovery of the exact operational-state SHA recorded in the release manifest;
6. validation of release `SHA256SUMS.txt` and all listed assets;
7. clean virtual environment reconstruction from the released wheel under `requirements.lock.txt`;
8. `sare_lotofacil doctor`;
9. operational-state audit;
10. full release test suite;
11. GitHub governance verification;
12. derivable SQLite initialization, backup and restore;
13. deliberate deletion of the reconstructed runtime and derived database files;
14. creation of a second runtime from zero;
15. second doctor and operational-state audit after simulated loss;
16. final DR report and artifact upload.

## Observed RPO

The report records:

- code RPO: **0 committed canonical Git commits**;
- operational-state RPO: **0 committed canonical Git state transitions**;
- recovery scope: exact canonical Git states addressed by SHA.

This is a commit-boundary RPO. It does not claim recovery of uncommitted local work, which is outside GitHub-only authority.

## Observed RTO

Measured by the recovery workflow from the start of the DR clock through the second reconstructed runtime and final report:

- **36.934 seconds**.

GitHub reported the job running from 22:25:10Z through 22:25:50Z; the internal report provides the finer 36.934-second measurement.

## Release integrity recovered

The recovered formal release preserved:

- release manifest SHA-256: `56e153b122c28946f0be0becc459d77bb3bafa54f108bb4635ee299f207e87f9`;
- wheel SHA-256: `f266b6d52a416bac5afb1f392f1f7b2d819fc9ab649ae1c85283b5a9cef19791`;
- release SHA: `07fdcf624c275f554caeac31e70dc1a34b8e99d9`;
- operational state SHA: `15be04a957a81aae8e92b6ae97e7ad26bc626a05`;
- predictive evidence classification: `NOT_ESTABLISHED`.

## Runtime-loss proof

The first clean virtual environment was explicitly deleted. Derived SQLite files were also deleted. A second virtual environment was then created from scratch from the released wheel and locked dependencies.

The second runtime passed doctor and operational-state audit. Therefore recovery does not depend on the first runner environment or a resident machine.

## External dependencies observed

The DR report explicitly records:

- GitHub repository and Git refs;
- GitHub Releases/Actions artifact hosting;
- GitHub-hosted `ubuntu-latest` runner;
- Python package-index access for locked third-party dependencies.

The dependencies are declared rather than hidden; `requirements.lock.txt` pins versions but does not vendor all third-party packages.

## Items not automatically recoverable

The report explicitly records:

- GitHub service availability itself;
- account/OAuth credentials and organization ownership outside Git history;
- native repository ruleset metadata if GitHub repository metadata is lost.

## Manual steps that remain inevitable

- restore/re-authorize GitHub account access after credential loss;
- recreate native rulesets from documented policy if repository metadata itself is lost.

External backups remain recovery copies only and are not promoted to concurrent authority.

## Fail-closed history preserved

R5 was not declared on the first attempts.

- run `35281371125`: failed at release recovery with `release not found`;
- run `35281563807`: repeated the same symptom while the formal GitHub Release was absent;
- during diagnosis, the formal `v1.1.10` release was confirmed absent even though its tags remained; this temporarily regressed the R4 release-availability invariant;
- the formal release was restored on the same tag/SHA with the same ten registered asset hashes;
- run `35281728785`: release assets recovered successfully, then failed because `OPERATIONS_STATE_SHA` was exported through `GITHUB_ENV` and consumed in the same step before GitHub made it available;
- PR #82 corrected that orchestration error without relaxing proof criteria;
- run `35281917468`: complete success.

The failed runs remain part of the evidence chain and are not reclassified as successful.

## Implementation and protected integration

- PR #80 introduced the DR verifier, fail-closed tests and GitHub Actions recovery workflow;
- PR #81 made release download repository-explicit;
- PR #82 corrected same-step operational-state SHA handling;
- each change passed the five protected R3 merge gates before integration.

## Conclusion

R5 exit criteria are satisfied: clean checkout, locked reinstall, release/state recovery by exact SHA, manifest/hash validation, essential checks, simulated execution-environment loss, measured RPO/RTO, and explicit external/manual limitations were all proven on a GitHub-hosted ephemeral runner.

NEXT_REQUIRED_STAGE: R6 — Integrated construction proof.
CONSTRUCTION_PROVEN: FALSE
