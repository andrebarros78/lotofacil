# SARE Lotofácil 1.1.5 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A identidade imutável da release é o SHA Git completo de `main`; `release/v1.1.5` só pode ser criado após todos os gates pós-merge do mesmo SHA terminarem com sucesso.

O estado persistente vive em `operations/state`; GitHub Actions é o executor canônico; GitHub Artifacts guarda evidências transitórias; Git history fornece proveniência.

Cadeia mínima:

`commit -> workflow run -> artifact -> provenance -> operations/state -> auditoria independente`

## Matriz de provas

| Prova | Implementação | Condição |
|---|---|---|
| P-DADOS | `Real History Check` | histórico validado, checkpoints oficiais, `integrity_check=ok`, snapshot reproduzível |
| P-MATEMATICA | `doctor` | `C(25,15)=3.268.760`, M0 p=0,6 e Brier=0,24 |
| P-CIENCIA | protocolo + experimentos | ausência de evidência aceita; promoção sem replicação bloqueada |
| P-RIS | RIS categórico | seis dimensões, `numeric_ris_enabled=false`, `score=null` |
| P-REGIME | T16/T19 | falso alarme calibrado e mudança conhecida detectada |
| P-ALTERNATIVAS | T17/T18 | potência marginal medida e memória temporal separada do viés marginal |
| P-BACKTEST | `experiments.backtest`, M1/M2 e T20–T23 | anti-leakage fail-closed, falhas no denominador, baixa cobertura = `INCONCLUSIVE` |
| P-PERSISTENCIA | `GitHub Operational Cycle` | estado textual versionado e reconstrução determinística |
| P-SEGURANCA | governance gate | Actions pinados, permissões mínimas, writer único e Release Proof obrigatório |
| P-RELEASE | `Release Proof` | wheel 1.1.5 limpo com provas matemática, RIS, regime, alternativas e backtest |
| P-REGRESSAO | `CI` | Python 3.12 e 3.13 aprovados |
| P-OPERACAO | ciclo + auditoria + prova econômica | operação GitHub-native ponta a ponta |
| P-CONSOLE | `SARE Operator Console Proof` | ações read-only sobre estado canônico |

## Contrato T20 — lookahead em variável

Para cada janela existe um `training_last_contest` e um `target_contest`. Toda variável usada na janela declara `available_through_contest`.

Se qualquer variável tiver `available_through_contest > training_last_contest`, o experimento é bloqueado **antes da pontuação** com:

`LOOKAHEAD_LEAKAGE_DETECTED`

Leakage não é tratado como mera janela falha; é erro fatal do experimento.

## Contrato T21 — transformação ajustada fora do treino

Toda transformação ajustável declara `fitted_through_contest`. Se o ajuste usar concurso posterior a `training_last_contest`, o experimento é bloqueado com:

`TRANSFORM_FIT_LEAKAGE_DETECTED`

Isso inclui o caso explícito de ajuste sobre o histórico completo antes de avaliar uma janela passada.

## Contrato T22 — falhas de janela

Janelas planejadas não podem desaparecer silenciosamente. Cada janela gera `WindowOutcome` com:

- ID da janela;
- último concurso de treino;
- concurso-alvo;
- estado `SUCCESS` ou `FAILED`;
- Brier M0 (`0,24`) sempre visível;
- Brier/ΔBrier do modelo quando disponível;
- tipo e mensagem de erro quando falha.

O relatório registra `planned_windows`, `successful_windows`, `failed_windows`, `success_rate`, `failed_window_ids` e SHA-256 do ledger normalizado.

## Contrato T23 — evidência insuficiente

A cobertura mínima é predefinida por `min_successful_windows` e `min_success_rate`. Se qualquer requisito não for atingido:

- `status = INCONCLUSIVE`;
- `predictive_evidence = NOT_ESTABLISHED`;
- um score favorável nas poucas janelas válidas não autoriza promoção.

No walk-forward canônico M1/M2, a cobertura exigida é de pelo menos 30 janelas válidas e taxa de sucesso 100%. O estado de backtest fica exposto no próprio `WalkForwardResult`.

## Relação com M1/M2

O caminho real M1 frequência regularizada e M2 exponencial usa a mesma camada auditada. Cada janela declara que `history_prefix` e o estado/transformação do modelo estão disponíveis/ajustados apenas até o corte de treino. Não existe uma implementação paralela exclusiva para os testes T20–T23.

A matemática preditiva permanece inalterada: M0 continua obrigatório em toda janela e as métricas agregadas continuam Brier, ΔBrier e IC95%.

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar simultaneamente:

- `CI` `completed/success` em Python 3.12 e 3.13;
- `Real History Check` `completed/success` com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `Release Proof` `completed/success`, incluindo `RELEASE_VERSION=1.1.5`, `MATHEMATICAL_CHECKS_PASS`, `CATEGORICAL_RIS_RELEASE_PROOF_PASS`, `REGIME_CALIBRATION_RELEASE_PROOF_PASS`, `CONTROLLED_ALTERNATIVES_RELEASE_PROOF_PASS`, `BACKTEST_INTEGRITY_RELEASE_PROOF_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS`;
- Artifact `backtest-integrity-release-proof` com T20 bloqueado, T21 bloqueado, T22 contabilizado e T23 `INCONCLUSIVE`;
- `GitHub Operational Cycle`: `cycle`, `committed-state-audit` e `economic-state-proof` em `success`;
- `SARE Operator Console Proof` `completed/success`;
- governance gate em PASS;
- `main` e `release/v1.1.5` resolvendo para o mesmo SHA.

O alias `release/v1.1.5` só é criado **depois** desses gates.

## Resultado científico e guardrails

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. T16–T23 são provas de calibração, sensibilidade ou integridade metodológica; não alteram o protocolo prospectivo nem promovem modelo.

Carteiras permanecem rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

`MISSION_PROVEN` é exclusivamente status de engenharia da release.

## Hardening soberano

A governança lógica GitHub-only é obrigatória. Enquanto Rulesets nativos não forem observados como ativos, o estado permanece:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

## Limitações 1.1.5

- T20–T23 comprovam integridade temporal/contábil para o contrato de backtest implementado; não provam vantagem preditiva;
- T17/T18 permanecem alternativas sintéticas controladas;
- detector de regime permanece retrospectivo e inicialmente marginal;
- SQLite é transitório/reconstruível, não memória permanente;
- histórico principal é corroborado por checkpoints e patches oficiais, não reconciliação linha a linha de uma exportação oficial única;
- Rulesets nativos continuam pendentes de ação administrativa externa;
- não existe vantagem preditiva comprovada.

Somente após observação material de todos os gates finais no mesmo SHA e alinhamento de `release/v1.1.5` o estado técnico desta release pode ser registrado como `MISSION_PROVEN`.
