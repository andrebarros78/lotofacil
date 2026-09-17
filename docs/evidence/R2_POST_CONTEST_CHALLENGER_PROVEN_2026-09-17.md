# R2 — Pós-concurso + aprendizagem controlada + Challenger

```text
stage_id: R2
status: PROVEN
canonical_implementation_sha: 6e65011510d737bfe88fbfbad703a274d89a848a
started_at: 2026-09-17T21:06:23Z
completed_at: 2026-09-17T21:10:48Z
reviewed_against_invariants: true
open_blockers: []
```

## Contrato de saída

R2 completa a cadeia:

`RESULTADO OFICIAL -> RECONCILIAÇÃO -> FREEZES -> AVALIAÇÃO -> EPISÓDIO -> HIPÓTESE -> CHALLENGER -> BACKTEST/WALK-FORWARD -> CHAMPION + M0 -> DECISÃO DE PROMOÇÃO/REJEIÇÃO`

A etapa prova integridade e reprodutibilidade da cadeia. Ela não declara vantagem preditiva. O estado científico permanece `NOT_ESTABLISHED`.

## Base pós-concurso já canônica

O pipeline incorporado anteriormente permanece obrigatório e foi coberto pela regressão completa:

- resultado oficial ligado a `contest_id + revision`;
- recuperação determinística de freezes;
- quantidade esperada verificável;
- avaliação idempotente;
- prova de não mutação dos freezes antes/depois;
- episódio estruturado persistido em `audit_events`;
- recuperação pelo RAG read-only;
- política do episódio: `retrospective_only=true`, `rewrite_frozen_cards=false`, `direct_model_tuning_allowed=false`.

## Implementação R2

Arquivo principal: `src/sare_lotofacil/experiments/challenger.py`.

### Hipótese predeclarada

`ChallengerHypothesis` exige:

- identidade da hipótese;
- episódio-fonte e concurso-fonte;
- hipótese e mecanismo esperado;
- `brier_score` como métrica primária;
- M0 `uniform_p_0_6` como baseline;
- janela fixa de validação;
- regra de parada fixa, sem optional stopping;
- regra de promoção predeclarada;
- lista explícita de dados proibidos: resultados futuros, alvos de validação e lockbox prospectivo;
- configuração Challenger congelada antes da validação.

A validação deve iniciar estritamente depois do concurso que originou o episódio. Sobreposição falha fechada.

### Episódio -> hipótese

`build_hypothesis_from_episode()` rejeita episódio que:

- não seja retrospectivo-only;
- permita reescrita de freezes;
- permita tuning direto de modelo.

Logo, RAG/episódio não possui caminho direto para promoção ou mutação do Champion.

### Challenger isolado

`run_isolated_challenger()`:

- valida a hipótese antes de acessar a janela de validação;
- falha se resultados predeclarados ainda não existirem;
- executa Champion e Challenger em walk-forward prefix-only;
- compara ambos ao M0 uniforme pela infraestrutura científica existente;
- mantém hash do Champion idêntico antes/depois;
- não aplica promoção automaticamente.

### Regra de decisão

A única regra de elegibilidade aceita é:

`challenger_ci_low_gt_delta_min_and_brier_lt_champion`

O resultado é somente:

- `ELIGIBLE_FOR_PROMOTION`, quando todos os critérios predeclarados forem satisfeitos; ou
- `REJECTED`.

Mesmo quando elegível, `promotion_applied=false`. Uma decisão científica não altera silenciosamente o Champion.

## Negative tests

`tests/test_challenger_r2.py` prova:

1. episódio retrospectivo gera hipótese com janela futura predeclarada;
2. episódio permitindo tuning direto é rejeitado;
3. validação sobreposta ao concurso-fonte é bloqueada por leakage;
4. ausência de resultados futuros bloqueia execução, sem backfill/reconstrução;
5. Champion mantém configuração/hash antes e depois do Challenger;
6. decisão é derivada somente da regra predeclarada;
7. tentativa de trocar stop rule depois do fato é rejeitada;
8. tentativa de trocar promotion rule depois do fato é rejeitada.

Os testes anteriores de pós-concurso continuam cobrindo recuperação de freezes, imutabilidade, idempotência da avaliação e RAG read-only.

## Workflow runs do SHA candidato `1f0d59581e62d32ed92ebad332a1586d0849a8be`

- CI `35275019748`: **SUCCESS**;
  - Python 3.12: **SUCCESS**;
  - Python 3.13: **SUCCESS**;
  - suíte observada em 3.13: `276 passed, 1 skipped`;
  - Doctor: **SUCCESS**;
  - GitHub-only governance: **SUCCESS**;
  - Agent ecosystem governance: **SUCCESS**;
  - Operator console smoke: **SUCCESS**.
- Repository Sanitization `35275019648`: **SUCCESS**.
- Agent Capability Proof `35275019668`: **SUCCESS**.
- Agent Resilience Proof `35275019743`: **SUCCESS**.
- Max Capacity Audit `35275019647`: **SUCCESS**.

## Limitação factual — concurso 3781

R2 não fabrica evidência histórica. A construção não cria nem reconstrói retroativamente um segundo freeze prospectivo real do concurso 3781 quando tal freeze canônico pré-sorteio não existe no estado auditado.

Essa limitação é uma aplicação da invariante soberana:

> sem freeze canônico pré-sorteio, não existe objeto prospectivo auditável.

Os testes que usam dois cartões para 3781 são fixtures de integração do pipeline e não constituem alegação de que dois freezes reais existiram na operação histórica.

## Ciência

```text
predictive_evidence: NOT_ESTABLISHED
promotion_direct_from_rag: FORBIDDEN
champion_mutation_before_gate: FORBIDDEN
optional_stopping: FORBIDDEN
future_validation_backfill: FORBIDDEN
```

A ausência de vantagem preditiva comprovada ou uma hipótese Challenger rejeitada são estados científicos válidos e não invalidam a prova de construção do pipeline.

## Resultado

```text
R0 = PROVEN
R1 = PROVEN
R2 = PROVEN
R3 = NOT_STARTED
R4 = NOT_STARTED
R5 = NOT_STARTED
R6 = NOT_STARTED
CONSTRUCTION_PROVEN = FALSE
NEXT_REQUIRED_STAGE = R3
```
