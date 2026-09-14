# SARE Lotofácil 1.1.6 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A identidade imutável da release é o SHA Git completo de `main`; `release/v1.1.6` só pode ser criado após todos os gates pós-merge do mesmo SHA terminarem com sucesso.

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
| P-RISCO | `simulation.risk` + T24/T25 | zero observado não vira risco zero; amostra vazia é erro |
| P-PARADA | `experiments.integrity` + T26/T27 | desempenho não diagnostica leakage; optional stopping confirmatório é bloqueado |
| P-REPRODUTIBILIDADE | `experiments.reproducibility` + T28 | contexto científico fixo gera conteúdo normalizado/hashes idênticos |
| P-COBERTURA-CONJUNTA | `portfolios.coverage` + T29 | carteira calculada conjuntamente sobre `C(25,15)`, sem independência automática |
| P-PERSISTENCIA | `GitHub Operational Cycle` | estado textual versionado e reconstrução determinística |
| P-SEGURANCA | governance gate | Actions pinados, permissões mínimas, writer único e provas de release obrigatórias |
| P-RELEASE | `Release Proof` | wheel 1.1.6 limpo com provas matemática, RIS, regime, T17–T29 e jornada operacional |
| P-REGRESSAO | `CI` | Python 3.12 e 3.13 aprovados |
| P-OPERACAO | ciclo + auditoria + prova econômica | operação GitHub-native ponta a ponta |
| P-CONSOLE | `SARE Operator Console Proof` | ações read-only sobre estado canônico |

## T20–T23 — integridade de backtest preservada

T20/T21 continuam bloqueando lookahead de variável e transformação por proveniência temporal; T22 mantém janelas falhas no denominador/ledger; T23 mantém cobertura insuficiente como `INCONCLUSIVE` com `predictive_evidence=NOT_ESTABLISHED`.

O walk-forward real M1/M2 continua usando a mesma camada auditada e M0 (`Brier=0,24`) em cada janela.

## Contrato T24 — zero eventos de ruína

Um evento binário de risco é resumido com intervalo de Wilson e resolução Monte Carlo explícita. Para amostra não vazia com zero eventos:

- estimativa pontual pode ser `0`;
- limite inferior é `0`;
- limite superior do intervalo deve ser **maior que zero**;
- zero eventos observados não pode ser rotulado como risco zero.

A resolução registrada é `1 / replications`.

## Contrato T25 — zero replicações

`replications` precisa ser inteiro positivo. `replications=0` é erro de entrada e não produz:

- probabilidade `0`;
- intervalo `[0,0]`;
- VaR, ruína ou qualquer outra métrica artificialmente nula.

## Contrato T26 — teste melhor que treino

Diferença de desempenho entre treino e teste não é critério de leakage. O diagnóstico canônico usa **proveniência temporal** da janela.

Se variáveis e transformações respeitam o corte de treino, `test_metric < train_metric` (para métrica em que menor é melhor) permanece uma observação de desempenho e retorna:

`NO_LEAKAGE_EVIDENCE_FROM_PERFORMANCE_GAP`

Isso não prova ausência universal de leakage; apenas impede o falso positivo “teste melhor que treino = vazamento”.

## Contrato T27 — parada oportunista

Protocolos confirmatórios exigem regra de parada fixa/predefinida e auditável. São aceitas regras explicitamente fixas e sem parada oportunista, inclusive texto humano equivalente.

Regras dependentes do resultado — por exemplo “inspecionar repetidamente até p<0,05”, parar ao atingir significância ou conveniência — são bloqueadas antes do hash/protocolo válido com:

`OPTIONAL_STOPPING_FORBIDDEN`

A aprovação de modelo continua exigindo `predictive_evidence=REPLICATED`; inspeções repetidas não promovem evidência.

## Contrato T28 — conteúdo científico normalizado

A identidade científica fixa:

- `seed`;
- `data_hash`;
- `code_commit`;
- `environment_hash`;
- `protocol_hash`;
- payload científico normalizado.

Campos voláteis operacionais como `run_id`, timestamps e IDs de workflow não participam do conteúdo científico normalizado.

Com seed, dados, código, ambiente, protocolo e valores científicos iguais, a serialização canônica e o SHA-256 precisam ser idênticos independentemente da ordem de chaves ou de IDs/timestamps voláteis.

Alterar um elemento científico fixado, como a seed, deve alterar o hash.

## Contrato T29 — cobertura conjunta de carteira

Para uma carteira `P` e limiar `h`, a autoridade é:

`Q_h(P) = # {d em Ω : max_c |c ∩ d| >= h} / |Ω|`

com `|Ω| = C(25,15) = 3.268.760`.

A versão 1.1.6 calcula essa cobertura por enumeração exata conjunta com máscaras de 25 bits. Em cada resultado possível, todos os cartões enfrentam o **mesmo** sorteio e o resultado é contado uma única vez quando ao menos um cartão atinge o limiar.

Invariantes:

- `method = EXACT_JOINT_ENUMERATION_25_CHOOSE_15`;
- `independence_assumption_used = false`;
- cartões precisam ser válidos e distintos;
- uma aproximação de independência pode ser exibida apenas como diagnóstico comparativo e nunca substitui a cobertura conjunta.

T29 não atribui vantagem preditiva à carteira; mede cobertura combinatória sob H0.

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar simultaneamente:

- `CI` `completed/success` em Python 3.12 e 3.13;
- `Real History Check` `completed/success` com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `Release Proof` `completed/success`, incluindo `RELEASE_VERSION=1.1.6`, `MATHEMATICAL_CHECKS_PASS`, `CATEGORICAL_RIS_RELEASE_PROOF_PASS`, `REGIME_CALIBRATION_RELEASE_PROOF_PASS`, `CONTROLLED_ALTERNATIVES_RELEASE_PROOF_PASS`, `BACKTEST_INTEGRITY_RELEASE_PROOF_PASS`, `RISK_REPRO_JOINT_COVERAGE_RELEASE_PROOF_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS`;
- Artifact `backtest-integrity-release-proof` com T20–T23;
- Artifact `risk-repro-joint-coverage-release-proof` com T24–T29 quantitativos do wheel instalado;
- `GitHub Operational Cycle`: `cycle`, `committed-state-audit` e `economic-state-proof` em `success`;
- `SARE Operator Console Proof` `completed/success`;
- governance gate em PASS;
- `main` e `release/v1.1.6` resolvendo para o mesmo SHA.

O alias `release/v1.1.6` só é criado **depois** desses gates.

## Resultado científico e guardrails

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. T16–T29 são provas de calibração, sensibilidade, integridade metodológica, risco, reprodutibilidade ou cobertura combinatória; nenhuma substitui o protocolo prospectivo nem promove modelo.

Carteiras permanecem rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

`MISSION_PROVEN` é exclusivamente status de engenharia da release.

## Hardening soberano

A governança lógica GitHub-only é obrigatória. Enquanto Rulesets nativos não forem observados como ativos, o estado permanece:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

## Limitações 1.1.6

- o resumo T24 é para evento binário observado em replicações e não substitui um simulador econômico completo de trajetórias, VaR/cauda e regimes de prêmio;
- T27 valida a regra declarada e marcadores de parada oportunista; não torna semanticamente decidível todo texto arbitrário possível;
- T28 normaliza conteúdo científico declarado, mas não substitui captura de ambiente/dependências no workflow;
- T29 faz cobertura exata combinatória, não retorno econômico nem vantagem preditiva;
- T17/T18 permanecem alternativas sintéticas controladas;
- detector de regime permanece retrospectivo e inicialmente marginal;
- SQLite é transitório/reconstruível, não memória permanente;
- histórico principal é corroborado por checkpoints e patches oficiais, não reconciliação linha a linha de uma exportação oficial única;
- Rulesets nativos continuam pendentes de ação administrativa externa;
- não existe vantagem preditiva comprovada.

Somente após observação material de todos os gates finais no mesmo SHA e alinhamento de `release/v1.1.6` o estado técnico desta release pode ser registrado como `MISSION_PROVEN`.
