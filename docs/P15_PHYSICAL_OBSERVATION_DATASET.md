# P15 Physical Observation Dataset V1

## Objective

Build an auditable, pre-specified evidence layer that links each Lotofácil contest to a defensible public draw transmission and later extracts physical/operational variables from that transmission.

This dataset is research infrastructure for the one-card P15 program. It does **not** by itself establish predictive advantage and it does not authorize betting.

## Public evidence basis

CAIXA's official draw rules state that:

- Lotofácil uses one globe loaded with balls numbered 01 through 25;
- the draw transmission includes procedures before the draw, including case checking/opening and globe loading, and procedures after the draw;
- draws from 07/10/2019 onward are described as available on CAIXA's official YouTube channel;
- draw dynamics may change according to equipment availability;
- retained balls can be manually released and interventions on the globe can occur under audit.

The official CAIXA YouTube channel is historically published as `https://www.youtube.com/user/canalcaixa`.

CAIXA's official 2020–2021 annual lottery report additionally states that lottery draws were transmitted by RedeTV and via streaming on official Loterias CAIXA social networks. Official CAIXA draw schedules from that era likewise record internet transmission through CAIXA and RedeTV channels. This establishes RedeTV as a documented historical broadcast source for recovery of archive gaps; it does not make third-party copies equivalent to the primary CAIXA archive.

These facts justify building an observational index. They do **not** imply that physical variables contain exploitable predictive information.

## Evidence tiers

### Tier A — Primary archive

Videos discovered inside CAIXA's own public YouTube channel surfaces (`search`, `videos`, `streams`, and month-scoped channel searches).

Allowed joins:

1. explicit Lotofácil contest id + compatible canonical date;
2. unique canonical Lotofácil contest on the exact video-title date when no contradictory contest evidence exists.

### Tier B — Documented historical broadcaster

Verified historical RedeTV broadcast material discovered through bounded public YouTube search shards.

A Tier B video is admitted only when the uploader/channel identity matches the allowlist and one of the following strong joins is present:

1. explicit Lotofácil contest id + exact canonical date; or
2. video title explicitly names Lotofácil + exact date + exactly one canonical Lotofácil contest on that date.

A generic date-only third-party video is insufficient. Unknown/re-upload channels are discarded.

## Phase 1 — Public video index

Canonical join key:

`contest_id -> draw_date -> evidence tier -> video id/url`

For every contest from the first archive-eligible Lotofácil contest onward, store:

- contest id;
- canonical draw date;
- canonical result for later extraction validation only;
- video id and URL when uniquely mapped;
- candidate video ids/URLs when more than one equal-rank source survives;
- video title and title date;
- explicit Lotofácil contest ids parsed from title/description when available;
- channel/uploader identity;
- duration when available;
- mapping status/confidence;
- evidence basis;
- placeholders for segment timestamps and extracted physical features.

### Mapping policy

The policy is fail-closed:

- `MAPPED`: one best candidate survives the evidence hierarchy;
- `AMBIGUOUS`: multiple equal-rank candidates exist and are retained for Phase 2 content disambiguation;
- `CONFLICT`: explicit evidence contradicts the canonical contest date;
- `MISSING`: no admissible candidate was discovered.

`coverage_ratio` counts only uniquely mapped contests.

`accessible_ratio` counts `MAPPED + AMBIGUOUS`, because an ambiguous contest already has public candidate video material available for content inspection but is not treated as uniquely resolved.

No ambiguous video is silently selected.

## Keyless discovery and the cloud bot gate

The live proof uses public YouTube surfaces through pinned `yt-dlp==2026.8.19`. No YouTube Data API key, paid account or new external account is required.

Bulk per-video hydration from GitHub-hosted runners was empirically challenged by YouTube's anti-bot gate. Therefore the architecture deliberately separates:

1. **archive discovery** — public flat indexes/searches, which do not require opening every video;
2. **content acquisition** — later bounded retrieval of individual mapped/candidate videos for frame/segment extraction.

Discovery unions:

- CAIXA channel search;
- CAIXA `videos` tab;
- CAIXA `streams` tab;
- month-scoped searches inside the CAIXA channel;
- month-scoped global YouTube searches for the documented historical broadcast era, filtered by the strict Tier B allowlist and join policy.

Per-video hydration is optional enrichment and its failure cannot erase already discovered index evidence.

The live workflow is evidence, not canonical operational state. It does not write to `operations/state`.

## Phase 2 — Segment localization

After sufficient video coverage is demonstrated, each mapped transmission will receive:

- Lotofácil segment start/end;
- loading start/end;
- mixing start;
- ejection timestamps for all 15 balls;
- intervention flags;
- visible equipment/mallet/case identifiers when defensibly observable.

`AMBIGUOUS` candidate sets are resolved only by source/content evidence (for example modality shown, contest slate, timestamps or visible draw identifiers). The known lottery result cannot be used to choose between candidate videos.

Automatic extraction must retain confidence and provenance for every field. Human review may validate uncertain observations but cannot use future contest results to relabel pre-draw features.

## Phase 3 — Physical feature research

Candidate variables include only observable or documented pre-result information, such as:

- draw venue/session;
- visible globe/equipment identity or stable visual fingerprint;
- visible ball-set/case identity or stable visual fingerprint;
- loading order if observable;
- mixing duration;
- time to first ejection;
- inter-ejection intervals;
- retained-ball/manual-release events;
- interventions, pauses and procedural anomalies;
- equipment changes across sessions.

Mass, diameter, material, maintenance and ball-set serial data must be treated as `UNAVAILABLE` until supported by official documentation or measurements. They must never be inferred as facts from result history.

## Scientific gate

A physical feature receives predictive weight only after leakage-safe evaluation shows information about the **future full 15-number outcome** beyond the mandatory uniform null.

Required progression:

1. discovery on past-only data;
2. frozen feature definition;
3. walk-forward evaluation;
4. placebo/surrogate tests;
5. stability across equipment/time partitions;
6. multiple-testing control;
7. prospective freeze and replication.

Until then:

`predictive_evidence = NOT_ESTABLISHED`

The P15 ranker may score all 3,268,760 cards using an experimental physical model, but an experimental rank is not a claim that the top card has proven advantage.
