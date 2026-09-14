# SARE Lotofácil 1.1.7 — Evidências de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil é **GitHub-only**. A identidade imutável da release é o SHA Git completo de `main`; `release/v1.1.7` só pode ser criado após todos os gates pós-merge do mesmo SHA terminarem com sucesso.

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
| P-CARTEIRA-ECONOMIA | T30–T39 | quantidade/unicidade, busca limitada, cobertura jackpot, custo real, rateio, horizonte e auditoria por revisão íntegros |
| P-PERSISTENCIA | `GitHub Operational Cycle` | estado textual versionado e reconstrução determinística |
| P-SEGURANCA | governance gate | Actions pinados, permissões mínimas, writer único e provas de release obrigatórias |
| P-RELEASE | `Release Proof` | wheel 1.1.7 limpo com provas matemática, RIS, regime, T17–T39 e jornada operacional |
| P-REGRESSAO | `CI` | Python 3.12 e 3.13 aprovados |
| P-OPERACAO | ciclo + auditoria + prova econômica | operação GitHub-native ponta a ponta |
| P-CONSOLE | `SARE Operator Console Proof` | ações read-only sobre estado canônico |

## T20–T29 — contratos preservados

A release 1.1.7 preserva integralmente os contratos já comprovados:

- T20/T21: lookahead de variável ou transformação é bloqueado por proveniência temporal;
- T22: falhas de janela permanecem no denominador e ledger;
- T23: cobertura insuficiente continua `INCONCLUSIVE` e `NOT_ESTABLISHED`;
- T24/T25: zero evento observado não vira risco zero e zero replicações é erro;
- T26: diferença treino/teste não diagnostica leakage por si só;
- T27: optional stopping confirmatório guiado por resultado é bloqueado;
- T28: conteúdo científico normalizado é reprodutível sob seed/dados/código/ambiente/protocolo fixos;
- T29: cobertura de carteira é conjunta no mesmo sorteio, sem independência automática entre cartões.

Essas provas continuam sem promover evidência preditiva.

## Contrato T30 — quantidade operacional

A carteira operacional aceita apenas `3 <= card_count <= 100`. Quantidades fora do intervalo são rejeitadas antes de qualquer geração ou persistência válida.

## Contrato T31 — unicidade sem redução silenciosa

Todo cartão contém 15 dezenas válidas e a carteira entregue precisa manter a quantidade solicitada. Duplicatas são rejeitadas explicitamente com:

`DUPLICATE_CARD`

Quando existe `expected_count`, diferença entre solicitado e entregue gera:

`DELIVERED_CARD_COUNT_MISMATCH`

Deduplicação silenciosa que reduz a quantidade da carteira não é aceita.

## Contrato T32 — busca limitada

Uma busca heurística/limitada recebe política identificada e `max_attempts` finito. Se o orçamento de busca termina sem encontrar a carteira completa:

`status = SEARCH_LIMIT_REACHED`

Esse resultado significa apenas que o algoritmo não encontrou solução dentro do limite. Não pode ser convertido em `INFEASIBLE_PROVEN` sem prova independente de inviabilidade.

Carteira parcial não é publicada como sucesso quando a quantidade pedida não foi atingida.

## Contrato T33 — relaxamento de restrições

Restrições de busca fazem parte da configuração científica/operacional. Pelo menos `max_overlap`, `max_exposure`, `max_attempts`, `seed` e `policy_name` entram na serialização canônica e no hash da política.

Alterar uma restrição cria outro `config_hash` e `config_id`. O sistema não relaxa restrições silenciosamente sob a mesma identidade.

## Contrato T34 — cobertura exata de jackpot

Para `m` cartões válidos e distintos de 15 dezenas, cada cartão corresponde a exatamente um resultado do espaço `C(25,15)` capaz de produzir 15 acertos naquele cartão. Logo:

`P(max_hits = 15) = m / 3.268.760`

O método canônico é:

`EXACT_DISTINCT_CARD_JACKPOT_IDENTITY`

Duplicatas não podem inflar `m`.

## Contrato T35 — geração não é compra

A existência de uma carteira gerada/congelada não implica despesa monetária real. Sem registro material de compra:

- `purchase_recorded = false`;
- `actual_cost_cents = null`;
- `actual_net_cents = null`.

`theoretical_cost_cents` permanece custo hipotético/teórico e não pode ser lançado automaticamente como gasto real.

## Contrato T36 — rateio por faixa e proveniência

As faixas 11, 12, 13, 14 e 15 mantêm seus próprios valores de prêmio. Quando proveniência é fornecida, cada faixa registra sua própria fonte.

É inválido substituir o valor de uma faixa pelo valor de outra ou usar uma única origem sem identificar a faixa quando a auditoria exige proveniência de rateio.

## Contrato T37 — mesmo rateio por unidade na mesma faixa/rodada

Dentro da mesma rodada/revisão, cartões que alcançam a mesma faixa recebem o mesmo valor unitário de rateio daquela faixa. O número de cartões internos premiados não divide novamente o valor unitário oficial.

Faixas diferentes continuam com valores diferentes conforme a fonte daquela rodada.

## Contrato T38 — horizonte econômico explícito

Resultados econômicos precisam declarar o horizonte em concursos. Uma rodada e uma sequência longa não são semanticamente equivalentes.

`HorizonCashflow` registra, entre outros:

- `horizon_contests`;
- saldo inicial e final;
- perda líquida;
- quantidade de concursos com resultado líquido negativo;
- incapacidade de financiar a próxima participação.

A interpretação de perda/ruína precisa respeitar esse horizonte explícito.

## Contrato T39 — auditoria por revisão e idempotência de domínio

A auditoria canônica de carteira contra histórico persistido usa a identidade:

`portfolio_id + contest_id + revision`

O resultado sorteado não é recebido do cliente nesse caminho; ele é carregado da revisão persistida em `contest_revisions`.

A tabela `revision_evaluations` possui unicidade sobre essa identidade. Repetir a mesma auditoria:

- retorna a mesma identidade determinística;
- não cria segunda avaliação lógica;
- não duplica o evento `PORTFOLIO_REVISION_EVALUATED`.

A API canônica é:

`POST /v1/evaluations/revisions`

O schema operacional correspondente é a versão 6.

## Gates finais do mesmo SHA

Antes de declarar `MISSION_PROVEN`, o SHA canônico precisa apresentar simultaneamente:

- `CI` `completed/success` em Python 3.12 e 3.13;
- `Real History Check` `completed/success` com `database_integrity=ok` e `snapshot_roundtrip_exact=true`;
- `Release Proof` `completed/success`, incluindo `RELEASE_VERSION=1.1.7`, `MATHEMATICAL_CHECKS_PASS`, `CATEGORICAL_RIS_RELEASE_PROOF_PASS`, `REGIME_CALIBRATION_RELEASE_PROOF_PASS`, `CONTROLLED_ALTERNATIVES_RELEASE_PROOF_PASS`, `BACKTEST_INTEGRITY_RELEASE_PROOF_PASS`, `RISK_REPRO_JOINT_COVERAGE_RELEASE_PROOF_PASS`, `PORTFOLIO_ECONOMIC_INTEGRITY_RELEASE_PROOF_PASS` e `OPERATIONAL_RELEASE_PROOF_PASS`;
- Artifact `backtest-integrity-release-proof` com T20–T23;
- Artifact `risk-repro-joint-coverage-release-proof` com T24–T29;
- Artifact `portfolio-economic-integrity-release-proof` com T30–T39 quantitativos produzidos pelo wheel instalado;
- `GitHub Operational Cycle`: `cycle`, `committed-state-audit` e `economic-state-proof` em `success`;
- `SARE Operator Console Proof` `completed/success`;
- governance gate em PASS;
- `main` e `release/v1.1.7` resolvendo para o mesmo SHA.

O alias `release/v1.1.7` só é criado **depois** desses gates.

## Resultado científico e guardrails

`EVIDENCIA_PREDITIVA_INSUFICIENTE` e `predictive_evidence=NOT_ESTABLISHED` continuam resultados válidos. T16–T39 são provas de calibração, sensibilidade, integridade metodológica, risco, reprodutibilidade, cobertura, construção de carteira ou auditoria econômica; nenhuma substitui o protocolo prospectivo nem promove modelo.

Carteiras permanecem rotuladas:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

`MISSION_PROVEN` é exclusivamente status de engenharia da release.

## Hardening soberano

A governança lógica GitHub-only é obrigatória. Enquanto Rulesets nativos não forem observados como ativos, o estado permanece:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`

## Limitações 1.1.7

- T32 comprova o tratamento correto do limite de busca, não um solver geral de inviabilidade combinatória;
- T34 cobre jackpot exato; limiares menores continuam usando a cobertura conjunta exata T29 quando necessário;
- T35 mantém compra ausente como custo real nulo; registro material de aposta comprada permanece fora desta release;
- T36/T37 validam rateio fornecido/persistido e sua proveniência, mas não fazem inferência de prêmio ausente;
- T38 explicita horizonte de fluxo de caixa, mas não substitui um simulador econômico completo de trajetórias, VaR/cauda e regimes futuros de prêmio;
- T39 torna a auditoria revision-aware/idempotente, mas revisão oficial posterior precisa ser tratada como nova revisão, não mutação da anterior;
- detector de regime permanece retrospectivo e inicialmente marginal;
- SQLite é transitório/reconstruível, não memória permanente;
- histórico principal é corroborado por checkpoints e patches oficiais, não reconciliação linha a linha de uma exportação oficial única;
- Rulesets nativos continuam pendentes de ação administrativa externa;
- não existe vantagem preditiva comprovada.

Somente após observação material de todos os gates finais no mesmo SHA e alinhamento de `release/v1.1.7` o estado técnico desta release pode ser registrado como `MISSION_PROVEN`.
