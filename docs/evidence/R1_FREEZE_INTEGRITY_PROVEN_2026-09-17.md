# R1 — Freeze Integrity universal — PROVEN

**Projeto:** SARE Lotofácil  
**Etapa:** R1 — Freeze Integrity universal  
**Data:** 2026-09-17  
**Implementação canônica:** `main@d81c71fdb01234fbc1438487deedda031d508f28`  
**PR de implementação:** #71  
**PR legado substituído:** #67 (`SUPERSEDED_CLOSED`)

## Resultado

`R1 = PROVEN`

A implementação do R1 foi integrada ao ramo canônico após fluxo protegido e prova automatizada em Python 3.12 e 3.13.

## Freeze Registry operacional

O ledger operacional passou a usar schema v2 e registra, por freeze:

- `freeze_id` determinístico;
- `target_contest`;
- `type = OPERATOR_CARD`;
- payload (`card`) e `payload_hash`/`card_sha256`;
- `created_at_utc`;
- `source_commit`;
- `workflow_run_id`;
- `model_identity`;
- `config_identity`;
- `state_ref`;
- `idempotency_key`;
- índice determinístico de geração.

O hash da requisição cobre os freezes associados e o ledger é validado integralmente antes de aceitar continuação ou replay.

## Semântica cumulativa reconciliada

A intenção válida do PR #67 foi reconstruída sobre o `main` pós-PR #69.

- requisições sucessivas para o mesmo concurso são append-only;
- cartões operacionais já congelados não são repetidos;
- `primary_card` prospectivo existente é tratado como combinação reservada;
- colisões são puladas deterministicamente;
- não existe sobrescrita silenciosa de freeze;
- replay com a mesma `idempotency_key` e mesmo fingerprint retorna a evidência existente sem gerar novos freezes;
- reutilização da mesma chave para conteúdo diferente falha com `OPERATOR_CARD_IDEMPOTENCY_CONFLICT`.

## Provas automatizadas

O arquivo `tests/test_operator_card_freeze.py` comprova:

1. `1 + 1` no mesmo concurso produz 2 freezes distintos;
2. `1 + 1 + 10 + 1 + 4` produz 17 cartões distintos;
3. replay idempotente produz zero novos freezes e preserva o ledger logicamente idêntico;
4. chave idempotente reutilizada para outra requisição é rejeitada;
5. serialização/reinício via JSON preserva recuperação e cursor determinístico;
6. quantidade esperada divergente falha explicitamente com `FROZEN_CARD_COUNT_MISMATCH`;
7. todos os campos mínimos de identidade/proveniência são obrigatórios;
8. adulteração é detectada por barreira criptográfica do request ou do payload;
9. requisição de 101 cartões prova ausência do antigo limite de 100;
10. colisão com `primary_card` reservado é impedida pelo caminho de geração e auditada pelo verificador do estado.

A rejeição de reconstrução retroativa sem freeze já permanece coberta pelo pipeline pós-concurso incorporado no PR #69 (`NO_FROZEN_CARDS_FOR_TARGET`), sem alteração regressiva neste estágio.

## Workflow canônico e governança

Foi adicionado `SARE Operator Card Freeze` como writer explicitamente autorizado em `operations/state`, compartilhando a concurrency group `sare-github-operational-state`.

O workflow:

- audita o estado antes da geração;
- exige chave de idempotência estável ou deriva uma chave única por execução;
- registra commit/run de origem;
- gera freezes via o mesmo módulo testado em CI;
- reaudita o estado antes da persistência;
- em replay idempotente, não cria commit vazio;
- publica artefatos de auditoria e ledger.

Não foi disparada uma solicitação real de novos cartões apenas para testar R1, porque isso criaria estado operacional prospectivo sem pedido de negócio. A implementação executada em CI usa o mesmo módulo de freeze e prova seus invariantes sem fabricar uma previsão real.

## Runs de prova do head aprovado

Head aprovado antes do squash: `44485f833c801e9d7b448a402a7843ae58e29321`.

- CI run `35274253727`: **success**;
  - `test (3.12)`: success;
  - `test (3.13)`: success;
  - Test, Doctor, GitHub-only governance gate, Agent ecosystem governance gate e Operator console smoke: success em ambos;
- Repository Sanitization run `35274253656`: **success**;
- Max Capacity Audit run `35274253751`: **success**;
- Agent Capability Proof run `35274253641`: **success**;
- Agent Resilience Proof run `35274253619`: **success**;
- Agent PR Pipeline Proof run `35274253658`: **success**.

Houve uma tentativa anterior de CI (`35274115663`) com 269 testes aprovados e 1 teste falho porque a asserção esperava especificamente `OPERATOR_CARD_HASH_MISMATCH`; o sistema detectou a adulteração antes, por `OPERATOR_CARD_REQUEST_HASH_MISMATCH`. O teste foi corrigido para reconhecer ambas as barreiras válidas e o reteste completo passou.

## Invariantes revisados

- freeze prospectivo não é reconstruído retroativamente;
- conteúdo congelado não é reescrito por avaliação posterior;
- cumulatividade não destrói freezes anteriores;
- replay é idempotente;
- colisões e adulteração falham explicitamente;
- RAG/aprendizagem pós-concurso não promovem modelo nem modificam freezes;
- a implementação não altera `predictive_evidence`.

## Registro de estágio

```text
stage_id: R1
status: PROVEN
canonical_sha: d81c71fdb01234fbc1438487deedda031d508f28
started_at: 2026-09-17
completed_at: 2026-09-17
requirements:
  - freeze registry universal para cartões operacionais
  - cumulatividade append-only
  - identidade/hash/proveniência por freeze
  - idempotência de requisição
  - recuperação determinística
  - colisão com freeze científico impedida
  - auditoria canônica
implemented_changes:
  - src/sare_lotofacil/portfolios/frozen.py
  - scripts/github_operator_freeze_cards.py
  - scripts/verify_github_operational_state.py
  - .github/workflows/operator-freeze-cards.yml
  - governance/github-only-policy.json
  - tests/test_operator_card_freeze.py
tests:
  - CI 35274253727 / Python 3.12 + 3.13: success
workflow_runs:
  - 35274253727
  - 35274253656
  - 35274253751
  - 35274253641
  - 35274253619
  - 35274253658
negative_tests:
  - idempotency conflict
  - expected count mismatch
  - tamper detection
  - reserved-card collision prevention
known_limitations:
  - nenhum novo cartão real foi persistido apenas para teste de construção
open_blockers: []
reviewed_against_invariants: true
```

**Próxima etapa obrigatória:** R2 — Pós-concurso + aprendizagem controlada + Challenger.
