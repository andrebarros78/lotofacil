# SARE Lotofácil 1.1.3 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A identidade imutável da release é o SHA Git completo de `main`; `release/v1.1.3` só pode ser criado após todos os gates pós-merge do mesmo SHA terminarem com sucesso.

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
| P-FUNCAO | API e jornada operacional | dados → hipótese → experimento → conclusão → carteira → avaliação executável |
| P-PERSISTENCIA | `GitHub Operational Cycle` | estado textual versionado e reconstrução determinística |
| P-RECUPERACAO | backup/restore + reconstrução GitHub | continuidade com integridade comprovada |
| P-SEGURANCA | governance gate | Actions pinados, permissões mínimas e writer operacional único |
| P-EVIDENCIA | hashes + Artifacts | adulteração detectável e vínculo com commit/workflow |
| P-RELEASE | `Release Proof` | wheel 1.1.3 em ambiente limpo + provas matemática, RIS e regime calibrado |
| P-REGRESSAO | `CI` | Python 3.12 e 3.13 integralmente aprovados |
| P-OPERACAO | ciclo + auditoria + prova econômica | operação GitHub-native ponta a ponta |
| P-CONSOLE | `SARE Operator Console Proof` | ações read-only, RIS real e calibração de regime materialmente comprovados |

## Contrato do detector de regime 1.1.3

O detector é um **scan global retrospectivo de mudança marginal**. O protocolo canônico inicial usa:

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

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar simultaneamente:

- `CI` `completed/success` em Python 3.12 e 3.13;
- `Real History Check` `completed/success` com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `Release Proof` `completed/success`, incluindo `RELEASE_VERSION=1.1.3`, `CATEGORICAL_RIS_RELEASE_PROOF_PASS`, `REGIME_CALIBRATION_RELEASE_PROOF_PASS`, `MATHEMATICAL_CHECKS_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS`;
- `GitHub Operational Cycle`: `cycle`, `committed-state-audit` e `economic-state-proof` em `success`;
- `SARE Operator Console Proof` `completed/success` para `status`, `audit`, `analyze`, `ris`, `portfolio` e `export`;
- console RIS comprovando `calibrated_global_marginal_change_scan`, `RETROSPECTIVE_DISCOVERY`, `compatible_with_target=true`, candidatos datados, `numeric_ris_enabled=false` e `score=null`;
- governance gate em PASS;
- `main` e `release/v1.1.3` resolvendo para o mesmo SHA.

O alias `release/v1.1.3` só é criado **depois** desses gates.

## Contrato RIS da linha 1.x

Permanece proibida qualquer nota RIS numérica:

- `numeric_ris_enabled = false`;
- `score = null`;
- `COMPATIBLE` não prova aleatoriedade;
- `ALERT` não constitui vantagem preditiva;
- alerta retrospectivo de regime não é alerta em tempo real;
- nenhum estado categórico promove modelo automaticamente.

## Resultado científico

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. O detector de regime é uma ferramenta de diagnóstico estatístico e não altera o protocolo prospectivo.

Carteiras permanecem rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

`MISSION_PROVEN` nesta documentação é exclusivamente um **status de engenharia da release**, não uma declaração de vantagem preditiva.

## Hardening soberano

A governança lógica GitHub-only é gate obrigatório. Os Rulesets nativos do GitHub continuam uma camada administrativa adicional e, enquanto não forem observados como ativos, o estado permanece:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

## Limitações 1.1.3

- o detector de regime cobre inicialmente mudanças **marginais**; não afirma cobrir toda forma possível de changepoint;
- o detector é retrospectivo; não existe ainda um protocolo separado de alerta online/tempo real;
- nenhum alerta recebe interpretação causal sem metadados de equipamento, bolas, processo ou coleta;
- o SQLite continua transitório/reconstruível, não memória permanente;
- o histórico principal é corroborado por checkpoints e patches oficiais, não uma reconciliação linha a linha de uma exportação oficial única;
- Rulesets nativos continuam pendentes de ação administrativa externa;
- não existe vantagem preditiva comprovada.

Somente após observação material de todos os gates finais no mesmo SHA e alinhamento de `release/v1.1.3` o estado técnico desta release pode ser registrado como `MISSION_PROVEN`.
