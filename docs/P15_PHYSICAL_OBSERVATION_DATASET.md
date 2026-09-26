# P15 Physical Observation Dataset V1

## Objective

Build an auditable, pre-specified evidence layer that links each Lotofácil contest to the official CAIXA draw transmission and later extracts physical/operational variables from that transmission.

This dataset is research infrastructure for the one-card P15 program. It does **not** by itself establish predictive advantage and it does not authorize betting.

## Public evidence basis

CAIXA's official draw rules state that:

- Lotofácil uses one globe loaded with balls numbered 01 through 25;
- the draw transmission includes procedures before the draw, including case checking/opening and globe loading, and procedures after the draw;
- draws from 07/10/2019 onward are available on CAIXA's official YouTube channel;
- draw dynamics may change according to equipment availability;
- retained balls can be manually released and interventions on the globe can occur under audit.

The official CAIXA YouTube channel is historically published as `https://www.youtube.com/user/canalcaixa`.

These statements justify building an observational index. They do **not** imply that the physical variables contain exploitable predictive information.

## Phase 1 — Official video index

Canonical join key:

`contest_id -> draw_date -> official video id/url`

For every contest from the first archive-eligible Lotofácil contest onward, store:

- contest id;
- canonical draw date;
- canonical result for later extraction validation only;
- video id and URL;
- video title and title date;
- explicit Lotofácil contest ids parsed from title/description;
- official channel identity when exposed by metadata;
- duration;
- mapping status/confidence;
- evidence basis;
- placeholders for segment timestamps and extracted physical features.

### Mapping policy

Evidence precedence is fail-closed:

1. explicit Lotofácil contest number + canonical date match;
2. explicit Lotofácil contest number without a contradictory date;
3. unique canonical Lotofácil contest on the official transmission title date;
4. otherwise `MISSING`, `AMBIGUOUS` or `CONFLICT`.

No ambiguous video is silently selected.

## Keyless discovery

The live proof uses public YouTube pages through a pinned `yt-dlp` release. No YouTube Data API key, paid account or new external account is required.

Discovery first queries the CAIXA channel search page for `Loterias CAIXA`. If that surface yields no usable entries, it falls back to the channel video listing and filters lottery transmissions by title/date before hydrating metadata.

The live workflow is evidence, not canonical state. It does not write to `operations/state`.

## Phase 2 — Segment localization

After sufficient video coverage is demonstrated, each mapped transmission will receive:

- Lotofácil segment start/end;
- loading start/end;
- mixing start;
- ejection timestamps for all 15 balls;
- intervention flags;
- visible equipment/mallet/case identifiers when defensibly observable.

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
