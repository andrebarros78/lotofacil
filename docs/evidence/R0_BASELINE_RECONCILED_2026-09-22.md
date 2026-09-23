# R0 — Baseline reconciliado — 2026-09-22

## Estado

`R0 = PROVEN`

Reexecução do R0 contra o estado canônico observado em 2026-09-22.

## Baseline canônico

- Repositório: `andrebarros78/lotofacil`
- Branch canônica: `main`
- HEAD observado: `35481e53e131bb087029c7917f59528035693c5b`
- Baseline de referência do plano: `9c731cfb6206a42b24198256bd16127cd6e39637`
- Relação: `main` está 48 commits à frente e 0 atrás do baseline de referência.
- `operations/state`: `66445d12e80dba3142050c6ef508e1d17246dbca`

## PRs e issues relevantes

- PRs abertos: 0.
- Issues abertas: 0.
- Issue #5: encerrada em 2026-09-17; a premissa antiga de ausência de rulesets foi reconciliada.
- PR #67: fechado sem merge e explicitamente marcado como `SUPERSEDED BY #71 / R1 CONSTRUCTION_PROVEN`; não deve ser mesclado.

## Rulesets ativos

### main — SARE Main Protection — ID 23459135

- enforcement: `active`
- alvo: `refs/heads/main`
- deletion: bloqueada
- non-fast-forward: bloqueado
- Pull Request: obrigatório
- resolução de threads: obrigatória
- merge permitido pelo ruleset: squash
- bypass actors: nenhum
- required status checks estritos:
  - `CI`
  - `Scientific Gate`
  - `Operational Integrity Gate`
  - `Security/Sanitization Gate`
  - `Release Candidate Gate`

### operations/state — SARE Operations State Protection — ID 23459186

- enforcement: `active`
- alvo: `refs/heads/operations/state`
- deletion: bloqueada
- non-fast-forward: bloqueado
- bypass actors: nenhum

## Checks observados no HEAD de main

No HEAD `35481e53e131bb087029c7917f59528035693c5b`, foram observados 17 check-runs concluídos com sucesso, incluindo os cinco required checks do ruleset de `main`.

## Decisões R0

1. O SHA canônico do baseline passa a ser `35481e53e131bb087029c7917f59528035693c5b`.
2. A Issue #5 permanece corretamente encerrada; não há P0 administrativo obsoleto aberto.
3. O PR #67 permanece corretamente fechado e superseded; sua intenção válida foi absorvida pela linha R1/#71.
4. Os rulesets de `main` e `operations/state` estão ativos e coerentes com o estado administrativo atual.
5. Os cinco checks compostos exigidos em `main` estão configurados como required status checks estritos.
6. Não há PR ou issue aberta no momento desta reconciliação.

## Gate de saída

- SHA canônico identificado: PASS
- inventário de PRs/issues: PASS
- rulesets e required checks verificados: PASS
- decisão explícita sobre #5: PASS
- decisão explícita sobre #67: PASS
- pendência P0 conhecida classificada incorretamente: nenhuma observada

`R0 = PROVEN`

Este registro é evidência administrativa do baseline observado. Não altera nem amplia alegações científicas ou preditivas do SARE.
