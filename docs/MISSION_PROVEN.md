# SARE Lotofácil 1.1.5 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A identidade imutável da release é o SHA Git completo de `main`; `release/v1.1.5` só pode ser criado após todos os gates pós-merge do mesmo SHA terminarem com sucesso.

O estado persistente vive em `operations/state`; GitHub Actions é o executor canônico; GitHub Artifacts guarda evidências transitórias; Git history fornece proveniência.

Cadeia mínima:

`commit -> workflow run -> artifact -> provenance -> operations/state -> auditoria independente`

## Matriz de provas

| Prova | Implementação | Condição |
|---|---|---|
| P-DADOS | `Real History Check`, ingestão, repositório e evidência | histórico validado, checkpoints oficiais, snapshot reproduzível, `integrity_check=ok` |
| P-MATEMATICA | `doctor`, combinatória e baseline | `C(25,15)=3.268.760`, E=9, Var=1,5, M0 p=0,6, Brier=0,24 |
| P-CIENCIA | protocolo, experimentos, walk-forward | ausência de evidência é aceita; promoção bloqueada sem replicação prospectiva |
| P-RIS | `analysis.ris`, API, console e `tests/test_ris.py` | seis dimensões, sem score numérico, autoridade matemática única |
| P-REGIME | `statistics.regime`, `analysis.regime`, `simulation.alternative`, `tests/test_regime.py` | T16 falso alarme calibrado/validado e T19 mudança conhecida detectada com ponto registrado |
| P-ALTERNATIVAS | `simulation.alternative`, `simulation.validation`, `tests/test_controlled_alternatives.py` | T17 potência marginal medida e T18 memória temporal detectada sem rejeição marginal ajustada |
| P-INTEGRIDADE-TEMPORAL | `experiments.integrity`, `ExperimentProtocol`, `tests/test_leakage_backtest_integrity.py` | T20/T21 bloqueiam leakage; T22 registra falha no denominador; T23 mantém pouca amostra como inconclusiva |
| P-FUNCAO | API e jornada operacional | dados → hipótese → experimento → conclusão → carteira → avaliação executável |
| P-PERSISTENCIA | `GitHub Operational Cycle` | estado textual versionado e reconstrução determinística |
| P-RECUPERACAO | backup/restore + reconstrução GitHub | continuidade com integridade comprovada |
| P-SEGURANCA | governance gate | Actions pinados, permissões mínimas e writer operacional único |
| P-EVIDENCIA | hashes + Artifacts | adulteração detectável e vínculo com commit/workflow |
| P-RELEASE | `Release Proof` | wheel 1.1.5 em ambiente limpo + provas matemática, RIS, regime, alternativas e integridade T20-T23 |
| P-REGRESSAO | `CI` | Python 3.12 e 3.13 integralmente aprovados |
| P-OPERACAO | ciclo + auditoria + prova econômica | operação GitHub-native ponta a ponta |
| P-CONSOLE | `SARE Operator Console Proof` | ações read-only, RIS real e calibração de regime materialmente comprovados |

## Contrato do detector de regime

O detector permanece um **scan global retrospectivo de mudança marginal**. O protocolo canônico usa:

- `alpha = 0,05`;
- segmento mínimo = 100 concursos;
- candidatos a cada 10 concursos;
- estatística máxima conjunta sobre 25 dezenas e todos os candidatos;
- 199 séries nulas para calibração do limiar;
- 199 séries nulas independentes para validação da taxa de falso alarme;
- IC95% de Wilson para o falso alarme observado;
- seed canônica `20260914`;
- modo obrigatório `RETROSPECTIVE_DISCOVERY`.

Estados permitidos são `STABLE`, `ALERT` e `INCONCLUSIVE`. `STABLE` não prova estabilidade física; `ALERT` não prova causa, não é alerta em tempo real e não constitui vantagem preditiva.

## Contrato T17 — viés marginal controlado

T17 usa 30 replicações independentes, 400 concursos por replicação, dezena-alvo `16`, probabilidade-alvo `0,72`, `alpha=0,05`, família de 25 testes marginais com Holm e seed-base `20260914`. A release exige potência `>=0,80`, pelo menos 24 detecções em 30 e efeito médio `>=0,08`.

## Contrato T18 — memória temporal controlada

T18 usa 600 concursos, probabilidade de memória `0,30`, retenção de 12 dezenas, seed `20260914`, lags `1,2,3,5,10`, 399 permutações e Holm. Exige zero rejeições marginais ajustadas, ao menos um alerta temporal, efeito no lag 1 `>0,50` e `p_holm<0,05`.

T17/T18 medem sensibilidade/separação em alternativas sintéticas predefinidas. Não demonstram que tais mecanismos existem no histórico real.

## Contrato T20 — variável do alvo/futuro

O protocolo científico congela `feature_offsets`, relativos ao concurso-alvo. Todo preditor precisa usar exclusivamente offsets `<0`.

Qualquer offset `0` ou positivo gera bloqueio fail-closed com código:

`FUTURE_OR_TARGET_FEATURE_OFFSET`

Um protocolo bloqueado não produz hash científico válido nem pode prosseguir como experimento válido.

## Contrato T21 — transformação ajustada fora do treino

`transform_fit_scope` canônico é obrigatoriamente:

`TRAIN_ONLY`

`FULL_HISTORY` ou qualquer escopo não autorizado é bloqueado antes da execução científica com:

`TRANSFORM_FIT_OUTSIDE_TRAIN`

A verificação não usa heurísticas de desempenho; ela inspeciona o contrato temporal declarado.

## Contrato T22 — falha de janela sem omissão silenciosa

A política canônica é:

`COUNT_IN_DENOMINATOR`

Toda janela agendada pertence ao denominador do backtest. Se uma janela falhar:

- `total_windows` não diminui;
- a janela aparece em `failures` com identificador e motivo;
- `failed_windows` é incrementado;
- o estado é `INCONCLUSIVE_WINDOW_FAILURES`;
- `advantage_eligible=false`.

A política `DROP_FAILED` é proibida pelo protocolo temporal.

## Contrato T23 — poucas janelas

O protocolo congela `min_eval_windows` positivo. Quando o número total de janelas é menor que o mínimo:

- o estado é `INCONCLUSIVE_INSUFFICIENT_WINDOWS`;
- resultados aparentemente favoráveis não alteram esse estado;
- `advantage_eligible=false`.

T23 existe para impedir que amostra pequena seja reinterpretada como evidência de vantagem.

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar simultaneamente:

- `CI` `completed/success` em Python 3.12 e 3.13;
- `Real History Check` `completed/success` com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `Release Proof` `completed/success`, incluindo `RELEASE_VERSION=1.1.5`, `CATEGORICAL_RIS_RELEASE_PROOF_PASS`, `REGIME_CALIBRATION_RELEASE_PROOF_PASS`, `CONTROLLED_ALTERNATIVES_RELEASE_PROOF_PASS`, `LEAKAGE_BACKTEST_INTEGRITY_RELEASE_PROOF_PASS`, `MATHEMATICAL_CHECKS_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS`;
- Artifact `controlled-alternatives-release-proof` com T17/T18 do wheel instalado;
- Artifact `leakage-backtest-integrity-release-proof` com T20/T21/T22/T23 do wheel instalado;
- `GitHub Operational Cycle`: `cycle`, `committed-state-audit` e `economic-state-proof` em `success`;
- `SARE Operator Console Proof` `completed/success` para `status`, `audit`, `analyze`, `ris`, `portfolio` e `export`;
- governance gate em PASS;
- `main` e `release/v1.1.5` resolvendo para o mesmo SHA.

O alias `release/v1.1.5` só é criado **depois** desses gates.

## Contrato RIS da linha 1.x

Permanece proibida qualquer nota RIS numérica:

- `numeric_ris_enabled = false`;
- `score = null`;
- `COMPATIBLE` não prova aleatoriedade;
- `ALERT` não constitui vantagem preditiva;
- alerta retrospectivo de regime não é alerta em tempo real;
- nenhum estado categórico promove modelo automaticamente.

## Resultado científico

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. T16–T23 são provas de calibração, sensibilidade ou integridade metodológica; nenhuma delas substitui o protocolo prospectivo nem promove modelo.

Carteiras permanecem rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

`MISSION_PROVEN` nesta documentação é exclusivamente um **status de engenharia da release**, não uma declaração de vantagem preditiva.

## Hardening soberano

A governança lógica GitHub-only é gate obrigatório. Os Rulesets nativos do GitHub continuam uma camada administrativa adicional e, enquanto não forem observados como ativos, o estado permanece:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

## Limitações 1.1.5

- T20/T21 validam o contrato temporal declarado; não provam que toda transformação futura possível possa ser detectada por introspecção automática;
- o auditor de janelas torna falhas explícitas e fail-closed, mas não transforma poucas janelas em evidência;
- T17/T18 permanecem alternativas sintéticas, não evidência sobre a Lotofácil real;
- o detector de regime cobre inicialmente mudanças marginais e é retrospectivo;
- não existe ainda protocolo separado de alerta online/tempo real;
- o SQLite continua transitório/reconstruível, não memória permanente;
- o histórico principal é corroborado por checkpoints e patches oficiais, não reconciliado linha a linha com uma exportação oficial única;
- Rulesets nativos continuam pendentes de ação administrativa externa;
- não existe vantagem preditiva comprovada.

Somente após observação material de todos os gates finais no mesmo SHA e alinhamento de `release/v1.1.5` o estado técnico desta release pode ser registrado como `MISSION_PROVEN`.
