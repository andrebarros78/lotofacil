# R4 — Formal Release Engineering — PROVEN

stage_id: R4
status: PROVEN
canonical_release_sha: 07fdcf624c275f554caeac31e70dc1a34b8e99d9
release_version: 1.1.10
release_tag: v1.1.10
release_alias: release/v1.1.10
release_url: https://github.com/andrebarros78/lotofacil/releases/tag/v1.1.10
published_at_utc: 2026-09-17T22:03:16Z
reviewed_against_invariants: true
open_blockers: []

## Same-SHA gate proof

The formal release target is `07fdcf624c275f554caeac31e70dc1a34b8e99d9`.

The same SHA completed the stable merge-gate push run `35278261372` with:
- `CI`: success
- `Scientific Gate`: success
- `Operational Integrity Gate`: success
- `Security/Sanitization Gate`: success
- `Release Candidate Gate`: success

The same SHA completed Release Proof push run `35278261414` with `success`.

## Immutable refs

Both refs resolve to the release SHA:
- `v1.1.10` -> `07fdcf624c275f554caeac31e70dc1a34b8e99d9`
- `release/v1.1.10` -> `07fdcf624c275f554caeac31e70dc1a34b8e99d9`

## Compatible operational state

Observed compatible operational authority:
- `operations/state@15be04a957a81aae8e92b6ae97e7ad26bc626a05`

## Release assets and hashes

The formal GitHub Release contains 10 uploaded assets.

- `release-manifest-v1.1.10.json`: `56e153b122c28946f0be0becc459d77bb3bafa54f108bb4635ee299f207e87f9`
- `SHA256SUMS.txt`: `0db9f8a1bcbe20aab49fd8deb44a9d57257a997602f3c1831480ee7cdf2170eb`
- `sare_lotofacil-1.1.10-py3-none-any.whl`: `f266b6d52a416bac5afb1f392f1f7b2d819fc9ab649ae1c85283b5a9cef19791`
- `backtest_integrity_release_proof.json`: `468258bf4d7828998c19c70925c6be6085ce59a5f58f3ee4a5db0b6158e86acb`
- `controlled_alternatives_release_proof.json`: `eba8badff4b37c89e4e607c7ca2842a0f9c2b2ae333db6de3c80e4db07737184`
- `operational_release_proof.json`: `1ef5799b9464558afe730dec29bb295a2629ad02a8b4c9a9bde4331ebc423fbe`
- `portfolio_economic_integrity_release_proof.json`: `e9b60e4b1605226cb2a1ba84e4413a8ea8170bf5061c4432954873b2e134cf78`
- `primary_card_release_proof.json`: `d6567582de5b149270eb47d36bc48277afa0ea9c67d5991a72a4c645b5483f53`
- `regime_calibration_release_proof.json`: `deb8f281852c6809f3ff81a55cc32455bfcb5ebd6888299cc00d7a6c644078a0`
- `risk_repro_joint_coverage_release_proof.json`: `5fc1a6ee3d98251d04fd28edb552e8a8e953c6759daef80778ad223abf494a76`

The release manifest also records source-file hashes, dependencies, gate results, protocol references, reconstruction commands and the compatible operational-state SHA.

## Reconstruction

The release documents:
1. `git checkout v1.1.10`
2. `python -m pip install -c requirements.lock.txt -e '.[dev]'`
3. `python -m pytest -q`
4. `python -m sare_lotofacil doctor`
5. `python scripts/verify_github_governance.py`

## Scientific limitation

The release preserves:
- `predictive_evidence=NOT_ESTABLISHED`
- no claim of predictive advantage;
- no retuning using observed lockbox;
- no automatic Champion promotion.

## Conclusion

R4 exit gate is satisfied: a formal GitHub Release exists, contains version/dependency/proof identity and SHA-256 evidence, and is linked to the exact SHA that passed both the stable required gates and Release Proof.

NEXT_REQUIRED_STAGE: R5 — Disaster Recovery GitHub-only.
CONSTRUCTION_PROVEN: FALSE
