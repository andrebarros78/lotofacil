# SARE Lotofácil 1.1.4 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A identidade imutável da release é o SHA Git completo de `main`; `release/v1.1.4` só pode ser criado após todos os gates pós-merge do mesmo SHA terminarem com sucesso.

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
| P-FUNCAO | API e jornada operacional | dados → hipótese → experimento → conclusão → carteira → avaliação executável |
| P-PERSISTENCIA | `GitHub Operational Cycle` | estado textual versionado e reconstrução determinística |
| P-RECUPERACAO | backup/restore + reconstrução GitHub | continuidade com integridade comprovada |
| P-SEGURANCA | governance gate | Actions pinados, permissões mínimas e writer operacional único |
| P-EVIDENCIA | hashes + Artifacts | adulteração detectável e vínculo com commit/workflow |
| P-RELEASE | `Release Proof` | wheel 1.1.4 em ambiente limpo + provas matemática, RIS, regime e alternativas controladas |
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

Estados permitidos:

- `STABLE`: calibração compatível com o alvo e nenhum candidato ultrapassa o limiar global;
- `ALERT`: calibração compatível, limiar excedido e p Monte Carlo no nível predefinido;
- `INCONCLUSIVE`: amostra insuficiente ou falso alarme não validado.

Todos os pontos candidatos avaliados devem ser registrados, incluindo concurso/data quando disponíveis.

**Guardrails:** `STABLE` não prova estabilidade física; `ALERT` não prova causa, não é alerta em tempo real e não constitui vantagem preditiva.

## Contrato T17 — viés marginal controlado

A prova T17 usa uma alternativa sintética predefinida em que uma dezena-alvo tem probabilidade marginal conhecida maior que `0,6`, preservando exatamente 15 dezenas por concurso.

Parâmetros canônicos iniciais:

- 30 replicações independentes;
- 400 concursos por replicação;
- dezena-alvo `16`;
- probabilidade-alvo `0,72`;
- `alpha = 0,05`;
- família de 25 testes marginais com correção de Holm;
- seed-base `20260914`.

A release exige potência empírica `>= 0,80`, pelo menos 24 detecções em 30 e efeito médio da dezena-alvo `>= 0,08`.

T17 mede sensibilidade em alternativa conhecida. Não demonstra que o histórico real contém o mesmo mecanismo.

## Contrato T18 — memória temporal controlada

A prova T18 usa um kernel simétrico por permutação das 25 dezenas. Cada concurso continua contendo exatamente 15 dezenas; em transições de memória, 12 dezenas são retidas do concurso anterior e as demais vêm do complemento.

Parâmetros canônicos iniciais:

- 600 concursos;
- probabilidade de memória `0,30`;
- retenção de 12 dezenas;
- seed `20260914`;
- lags predefinidos `1, 2, 3, 5, 10`;
- 399 permutações de concursos completos;
- `alpha = 0,05` com correção de Holm por família.

Critérios obrigatórios:

- zero rejeições na família marginal corrigida por Holm;
- ao menos um alerta temporal ajustado;
- efeito no lag 1 maior que `0,50` dezena repetida;
- `p_holm < 0,05` no lag 1.

O efeito marginal máximo é preservado como diagnóstico descritivo, mas não recebe limiar inferencial ad hoc. A afirmação "sem confusão marginal" é definida pela família estatística canônica corrigida por Holm.

T18 demonstra separação controlada entre dependência temporal e viés marginal nesta alternativa predefinida; não constitui prova universal de separabilidade nem evidência preditiva no histórico real.

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar simultaneamente:

- `CI` `completed/success` em Python 3.12 e 3.13;
- `Real History Check` `completed/success` com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `Release Proof` `completed/success`, incluindo `RELEASE_VERSION=1.1.4`, `CATEGORICAL_RIS_RELEASE_PROOF_PASS`, `REGIME_CALIBRATION_RELEASE_PROOF_PASS`, `CONTROLLED_ALTERNATIVES_RELEASE_PROOF_PASS`, `MATHEMATICAL_CHECKS_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS`;
- Artifact `controlled-alternatives-release-proof` contendo os resultados quantitativos T17/T18 do wheel instalado;
- `GitHub Operational Cycle`: `cycle`, `committed-state-audit` e `economic-state-proof` em `success`;
- `SARE Operator Console Proof` `completed/success` para `status`, `audit`, `analyze`, `ris`, `portfolio` e `export`;
- console RIS comprovando `calibrated_global_marginal_change_scan`, `RETROSPECTIVE_DISCOVERY`, `compatible_with_target=true`, candidatos datados, `numeric_ris_enabled=false` e `score=null`;
- governance gate em PASS;
- `main` e `release/v1.1.4` resolvendo para o mesmo SHA.

O alias `release/v1.1.4` só é criado **depois** desses gates.

## Contrato RIS da linha 1.x

Permanece proibida qualquer nota RIS numérica:

- `numeric_ris_enabled = false`;
- `score = null`;
- `COMPATIBLE` não prova aleatoriedade;
- `ALERT` não constitui vantagem preditiva;
- alerta retrospectivo de regime não é alerta em tempo real;
- nenhum estado categórico promove modelo automaticamente.

## Resultado científico

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. T16/T17/T18/T19 são testes de calibração/sensibilidade em dados nulos ou alternativas controladas; não alteram o protocolo prospectivo nem promovem modelo.

Carteiras permanecem rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

`MISSION_PROVEN` nesta documentação é exclusivamente um **status de engenharia da release**, não uma declaração de vantagem preditiva.

## Hardening soberano

A governança lógica GitHub-only é gate obrigatório. Os Rulesets nativos do GitHub continuam uma camada administrativa adicional e, enquanto não forem observados como ativos, o estado permanece:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

## Limitações 1.1.4

- T17/T18 medem sensibilidade/separação em alternativas sintéticas predefinidas e não demonstram que tais mecanismos existem na Lotofácil real;
- o detector de regime cobre inicialmente mudanças **marginais**; não afirma cobrir toda forma possível de changepoint;
- o detector de regime é retrospectivo; não existe ainda um protocolo separado de alerta online/tempo real;
- nenhum alerta recebe interpretação causal sem metadados de equipamento, bolas, processo ou coleta;
- o SQLite continua transitório/reconstruível, não memória permanente;
- o histórico principal é corroborado por checkpoints e patches oficiais, não uma reconciliação linha a linha de uma exportação oficial única;
- Rulesets nativos continuam pendentes de ação administrativa externa;
- não existe vantagem preditiva comprovada.

Somente após observação material de todos os gates finais no mesmo SHA e alinhamento de `release/v1.1.4` o estado técnico desta release pode ser registrado como `MISSION_PROVEN`.
