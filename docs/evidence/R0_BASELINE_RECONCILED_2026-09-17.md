# R0 — Baseline reconciliado

**Projeto:** SARE Lotofácil  
**Etapa:** R0 — Reconciliar e selar o baseline  
**Data:** 2026-09-17  
**Baseline canônico verificado:** `main@9c731cfb6206a42b24198256bd16127cd6e39637`

## Estado verificado

- `main` permanece exatamente no SHA-base registrado: `9c731cfb6206a42b24198256bd16127cd6e39637`.
- `operations/state` observado em `6da0cfe6a7490ed94106506fc223e8ade3a3fae7`.
- PRs abertos observados durante R0:
  - #70 — `docs: add CONSTRUCTION_PROVEN execution registry`;
  - #67 — `fix: allow cumulative operator card freezing per contest`;
  - #38 — `[proof] bounded agent proposal e49f780c8853`.
- Issues abertas relevantes antes da reconciliação:
  - #68 — missão pós-concurso / Challenger;
  - #5 — rulesets nativos, semanticamente obsoleta.

## Rulesets nativos

### `main`

Ruleset ativo: `SARE Main Protection` — ID `23459135`.

Regras observadas:
- bloqueio de deleção;
- bloqueio de non-fast-forward;
- Pull Request obrigatório;
- resolução de review threads obrigatória;
- merge permitido por squash;
- required status checks estritos:
  - `test (3.12)`;
  - `test (3.13)`;
- nenhum bypass actor.

### `operations/state`

Ruleset ativo: `SARE Operations State Protection` — ID `23459186`.

Regras observadas:
- bloqueio de deleção;
- bloqueio de non-fast-forward;
- nenhum bypass actor.

## Reconciliações executadas

### Issue #5

A issue afirmava que a API de Rulesets retornava lista vazia. Isso não corresponde mais ao estado canônico. A issue foi atualizada com os dois rulesets ativos e encerrada como `completed`.

A ampliação futura de required checks para os cinco gates compostos do plano CONSTRUCTION_PROVEN permanece matéria de R3, não de #5.

### PR #67

O PR #67 foi criado sobre merge-base `7acca8acdcf6146510ed1857d70d2b1af7fb3b9c` e diverge do `main` atual, que incorporou o PR #69.

Comparação observada entre `52636d98e8c95d1907de7135c3fe564643187998` (head de #67) e `main@9c731cfb...`:
- estado: `diverged`;
- o `main` possui 1 commit pós-merge-base não incorporado pelo PR #67;
- esse commit adiciona o pipeline pós-concurso em `src/sare_lotofacil/persistence/post_contest.py`, `src/sare_lotofacil/rag/learning.py` e `tests/test_post_contest_learning.py`.

A descrição do PR #67 foi atualizada com bloqueio explícito de reconciliação pós-PR #69 e o PR foi convertido para `draft`.

## Required checks efetivamente exigidos

No ruleset atual de `main`, apenas estes contextos são required checks de merge:

- `test (3.12)`;
- `test (3.13)`.

Outros workflows podem executar e fornecer evidência, mas não devem ser tratados como required checks de merge enquanto não estiverem presentes no ruleset. A consolidação em `CI -> Scientific Gate -> Operational Integrity Gate -> Security/Sanitization Gate -> Release Candidate Gate` pertence a R3.

## Provas observadas no PR #70 antes deste registro

No head `2014876347b02e6ff19771e0f3121e6b53c60f80`:
- `CI` run `35261318041`: `success`;
- `Repository Sanitization` run `35261317975`: `success`.

Este arquivo cria novo head e, portanto, essas runs históricas não substituem os checks exigidos para o novo commit.

## Classificação R0

```text
stage_id: R0
status: PROVEN_CANDIDATE_PENDING_CANONICAL_MERGE
canonical_sha: 9c731cfb6206a42b24198256bd16127cd6e39637
requirements:
  - HEAD de main verificado contra baseline
  - PRs/issues relevantes inventariados
  - rulesets main e operations/state verificados
  - required checks efetivos identificados
  - Issue #5 reconciliada e encerrada
  - PR #67 bloqueado para reconciliação pós-PR #69
  - registro de baseline produzido
open_blockers:
  - este registro ainda precisa ser integrado ao ramo canônico por fluxo protegido
reviewed_against_invariants: true
```

R0 somente passa a `PROVEN` após este registro integrar `main` por PR protegido e o SHA resultante ser reverificado.
