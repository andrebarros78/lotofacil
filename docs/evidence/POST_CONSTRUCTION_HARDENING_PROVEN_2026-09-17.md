# Post-Construction Hardening — Gaps Closed

status: PROVEN
date: 2026-09-17
construction_proven: TRUE
predictive_evidence: NOT_ESTABLISHED
open_p0_blockers: []

## Gaps closed

### 1. Terminal tags were not natively protected

Before hardening, only `main` and `operations/state` had repository rulesets. Terminal release/construction tags could still be deleted or repointed through Git operations.

Resolved with native GitHub ruleset:

- id: `23629930`
- name: `SARE Terminal Tags Protection`
- target: `tag`
- enforcement: `active`
- bypass actors: none
- current user bypass: never
- rules: `deletion`, `update`

Protected tags:

- `v1.1.10`
- `release/v1.1.10`
- `release-seal/v1.1.10`
- `construction-proven/v1.1.10`
- `construction-seal/v1.1.10`
- `hardening-seal/v1.1.10`

### 2. Immutable Releases was disabled

Repository-level immutable releases was verified as disabled and then enabled through the GitHub repository API.

Final state:

`enabled=true`

This setting applies to releases published after enablement.

### 3. Historical release v1.1.10 predates immutable releases

The original `v1.1.10` release was intentionally preserved and not deleted/recreated. Verification with `gh release verify v1.1.10` returned no release attestation, as expected for the historical mutable release.

To close the asset-integrity gap, an immutable mirror was published:

`release-seal/v1.1.10 -> 07fdcf624c275f554caeac31e70dc1a34b8e99d9`

The mirror contains all 10 original assets plus `RELEASE_SEAL_METADATA.json`.

Every one of the 10 original assets was compared by GitHub-reported SHA-256 digest and size against the immutable mirror. Result:

`ORIGINAL_10_ASSETS_EXACT_MATCH=TRUE`

The mirror release was verified with GitHub release attestation:

`gh release verify release-seal/v1.1.10` -> success.

### 4. Construction evidence lacked an immutable GitHub Release envelope

An immutable construction seal was published:

`construction-seal/v1.1.10 -> c5daaa677638328837b6281e877482882601edae`

The release is `immutable=true` and contains:

- `construction-seal-manifest-v1.1.10.json`
- `CONSTRUCTION_MANIFEST_1_1_10.json`
- `CONSTRUCTION_PROVEN.md`
- `CONSTRUCTION_SHA256SUMS.txt`
- `R6_INTEGRATED_CONSTRUCTION_PROVEN_2026-09-17.md`

Construction-seal manifest SHA-256:

`4892b1a3ac97b3f224fcde26bc54c7e86d9adfa8390e31b2a0d54cc592ac2e83`

GitHub release verification and local asset verification both succeeded.

## Roles remain distinct

- construction execution SHA: `77d1b6d92edee8c8ed7a0b146441ab6c0ec47e7c`
- terminal documentary seal SHA: `c5daaa677638328837b6281e877482882601edae`
- formal software release SHA: `07fdcf624c275f554caeac31e70dc1a34b8e99d9`
- release-compatible operations snapshot: `15be04a957a81aae8e92b6ae97e7ad26bc626a05`
- operations/state latest observed during reconciliation: `975b706db49f168a9bee9c1e08b14ebdfde32979`

These differences are intentional and do not create split authority. The immutable tags/releases preserve the historical snapshots, while `operations/state` may continue append-only advancement.

## Terminal result

No construction regression was introduced.

`CONSTRUCTION_PROVEN = TRUE`

`POST_CONSTRUCTION_HARDENING = PROVEN`

`open_p0_blockers = []`
