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

O detector permanece um **scan global retrospectivo de mudança marginal**. O protocolo canônico usa `alpha=0,05`, segmento mínimo de 100 concursos, candidatos a cada 10 concursos, 199 séries nulas para calibração e 199 independentes para validação, IC95% de Wilson e modo `RETROSPECTIVE_DISCOVERY`.

## Contrato T17 — viés marginal controlado

T17 usa 30 replicações de 400 concursos, dezena-alvo 16, probabilidade-alvo 0,72, alpha 0,05, família de 25 testes marginais com Holm e seed-base 20260914. A release exige potência >=0,80, ao menos 24/30 detecções e efeito médio >=0,08.

## Contrato T18 — memória temporal controlada

T18 usa 600 concursos, probabilidade de memória 0,30, retenção de 12 dezenas, seed 20260914, lags 1,2,3,5,10, 399 permutações e Holm. Exige zero rejeições marginais ajustadas, ao menos um alerta temporal, efeito lag 1 >0,50 e p_holm<0,05. O efeito marginal máximo é apenas diagnóstico descritivo.

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar CI 3.12/3.13, Real History Check com integridade e round-trip, Release Proof com versão 1.1.4 e provas matemática/RIS/regime/T17-T18/operação, GitHub Operational Cycle com auditoria e prova econômica, Operator Console Proof, governance PASS e `main == release/v1.1.4`.

## Resultado científico

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. T16/T17/T18/T19 são testes de calibração/sensibilidade e não promovem modelo. Carteiras permanecem rotuladas `CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`.

## Hardening soberano

Rulesets nativos permanecem camada administrativa externa pendente; estado: `P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`.

## Limitações 1.1.4

T17/T18 são sintéticos; regime é retrospectivo e marginal; não há alerta online nem vantagem preditiva comprovada; SQLite é transitório; histórico é corroborado por checkpoints/patches; Rulesets nativos permanecem pendentes.
