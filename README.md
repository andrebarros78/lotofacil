# SARE Lotofácil

Sistema de Análise de Randomicidade e Eventos para a Lotofácil.

## Release

**SARE Core 1.0 + SARE Operational 1.1 — versão 1.1.9.**

O sistema prioriza integridade dos dados, matemática exata, reprodutibilidade, auditoria e recuperação antes de qualquer alegação preditiva.

**Não há vantagem preditiva comprovada.** O histórico real validado produz `EVIDENCIA_PREDITIVA_INSUFICIENTE`; carteiras permanecem combinatórias e são rotuladas explicitamente dessa forma.

## Regra operacional soberana

O SARE Lotofácil é um produto **GitHub-only**.

- repositório canônico: `andrebarros78/lotofacil`;
- `main`: código, testes, protocolos e workflows aprovados;
- `operations/state`: estado operacional persistente e auditável;
- GitHub Actions: único executor operacional aceito;
- GitHub Artifacts: evidências, relatórios e snapshots reconstruíveis;
- Git history: trilha temporal e de proveniência.

**Nenhum PC local, VPS, servidor externo, banco local ou processo residente é requisito de operação, continuidade ou aceitação do produto.**

Execuções fora do GitHub podem existir somente como desenvolvimento ou diagnóstico não canônico. Elas não podem promover estado, produzir evidência oficial, alterar readiness, fechar gaps nem sustentar `MISSION_PROVEN`.

A autoridade operacional está documentada em `docs/GITHUB_OPERATIONS.md`.

## Capacidades

- invariantes oficiais: 25 dezenas e sorteio de 15;
- `C(25,15) = 3.268.760`, distribuição hipergeométrica exata e máscaras de 25 bits;
- M0 uniforme `p_i = 0,6`, Brier `0,24`;
- M1 frequência regularizada e M2 média exponencial em walk-forward, com `ΔBrier` e IC95%;
- backtest auditado com proveniência temporal de variáveis/transformações, ledger de janelas e falhas no denominador;
- risco binomial com intervalo de Wilson, sem converter zero eventos observados em risco zero;
- regras confirmatórias de parada fixas, com optional stopping guiado por resultado bloqueado;
- identidade científica normalizada por seed, dados, código, ambiente e protocolo;
- cobertura conjunta exata de carteira por enumeração do espaço `C(25,15)`, sem hipótese automática de independência entre cartões;
- busca limitada de carteiras com política identificada e estado `SEARCH_LIMIT_REACHED` separado de inviabilidade provada;
- validação explícita de quantidade e unicidade de cartões, sem redução silenciosa da carteira entregue;
- cobertura exata de jackpot `m / C(25,15)` para `m` cartões distintos;
- economia auditável separando custo teórico de despesa real, com proveniência de rateio por faixa e rodada;
- fluxo econômico com horizonte explícito, distinguindo uma rodada de uma sequência de concursos;
- auditoria de carteira vinculada a `contest_id + revision`, idempotente e sem aceitar resultado injetado pelo cliente;
- ingestão validada, revisões imutáveis e artefatos de fonte;
- fonte oficial CAIXA e histórico corroborado por checkpoints oficiais;
- protocolo científico congelado por hash, hipóteses e experimentos auditáveis;
- promoção de modelo bloqueada enquanto a evidência não for `REPLICATED`;
- RIS categórico auditável com seis dimensões, sem score numérico na linha 1.x;
- temporal RIS por permutação de concursos completos nos lags predefinidos 1, 2, 3, 5 e 10, com correção de Holm;
- regime RIS por scan global retrospectivo, limiar calibrado em nulo e falso alarme validado em amostra nula independente;
- laboratório de alternativas controladas com T17 para potência sob viés marginal e T18 para memória temporal sem confusão marginal;
- simuladores de alternativa controlada para medir sensibilidade sem atribuir causalidade;
- carteiras uniformes com etiqueta obrigatória de ausência de vantagem comprovada;
- verificação SHA-256 de evidências persistidas;
- reconstrução determinística do SQLite operacional em GitHub Actions com `integrity_check`;
- CI Python 3.12/3.13, Real History Check, GitHub Operational Cycle, Release Proof e Max Capacity Audit.

## Capacidade máxima 1.1.9

A release 1.1.9 adiciona uma auditoria permanente de capacidade científica e operacional, sem converter desempenho retrospectivo em alegação de previsão:

- treinamento walk-forward M1/M2 sobre o histórico real reconciliado;
- seleção de hiperparâmetros em protocolo cronológico 60/20/20, com holdout separado da validação;
- qualificação sintética contra nulo, viés marginal, memória temporal e mudança de regime;
- falha induzida em janelas de backtest, mantendo falhas no denominador e retornando `INCONCLUSIVE` quando a cobertura é insuficiente;
- injeção de lookahead para comprovar bloqueio de vazamento temporal;
- prova de reprodutibilidade por semente;
- auditoria específica do valor incremental do desempate M2 na política de cartão primário, usando expectativa neutra no grupo empatado e bootstrap em blocos;
- ruleset explícito e versionado para o concurso 3780, Lotofácil da Independência 2026, sem aplicar essa regra a concursos regulares;
- `requirements.lock.txt` como ambiente validado da linha 1.1.9 e instalação dos gates sob constraints fixadas;
- workflow `Max Capacity Audit` executado em PR e em mudanças aplicáveis de `main`.

A auditoria real demonstrou que M1 não se distingue do M0 no holdout e que M2 `alpha=0,05` é inferior ao M0 como previsão marginal. Na função restrita de desempate do cartão primário, M2 não demonstrou valor incremental. Esses resultados mantêm `predictive_evidence=NOT_ESTABLISHED` e impedem promoção científica automática.

## Integridade de carteira e auditoria econômica

A versão 1.1.7 fechou T30–T39:

- **T30 — quantidade operacional:** carteiras fora do intervalo 3–100 são rejeitadas.
- **T31 — cartão duplicado:** duplicatas geram `DUPLICATE_CARD`; a quantidade entregue é validada e não pode cair silenciosamente abaixo da quantidade solicitada.
- **T32 — busca limitada:** esgotar `max_attempts` retorna `SEARCH_LIMIT_REACHED`; isso não é convertido em prova de inviabilidade.
- **T33 — relaxamento de restrição:** overlap, exposição, seed, orçamento de tentativas e nome da política participam da identidade da configuração; alterar restrição produz outro `config_id`/hash.
- **T34 — jackpot:** para `m` cartões distintos, a cobertura exata de 15 acertos é `m / 3.268.760`.
- **T35 — compra versus geração:** uma carteira apenas gerada mantém `purchase_recorded=false`, `actual_cost_cents=null` e `actual_net_cents=null`; custo teórico não é lançado como despesa real.
- **T36 — rateio por faixa:** 11, 12, 13, 14 e 15 acertos preservam seus próprios valores e, quando fornecida, sua própria proveniência de rateio.
- **T37 — múltiplos ganhadores internos:** cartões da mesma carteira que atingem a mesma faixa na mesma rodada recebem o mesmo rateio unitário daquela faixa.
- **T38 — horizonte:** uma rodada e uma sequência de concursos carregam `horizon_contests` diferente e produzem interpretações econômicas distintas de perda/capacidade de financiar a próxima participação.
- **T39 — auditoria repetida:** a auditoria canônica usa `portfolio_id + contest_id + revision`; repetir a mesma combinação produz a mesma identidade e não duplica o efeito persistido.

O endpoint `POST /v1/evaluations/revisions` recebe apenas a identidade da carteira e da revisão. O resultado é carregado da revisão persistida, impedindo que o cliente substitua o resultado oficial/auditado por uma máscara arbitrária.

Esses controles validam construção de carteira, contabilidade e auditoria. **Eles não estabelecem vantagem preditiva.**

## Integridade de risco, parada, reprodutibilidade e carteira

A versão 1.1.6 fechou T24–T29:

- **T24 — zero eventos de ruína:** zero eventos observados mantém estimativa pontual `0`, mas o limite superior do intervalo binomial continua maior que zero; ausência observada não vira ausência de risco.
- **T25 — zero replicações:** `replications=0` é erro de entrada e não produz métricas de risco iguais a zero.
- **T26 — teste melhor que treino:** diferença favorável no teste não é classificada como leakage por si só; leakage é decidido pela proveniência temporal das variáveis/transformações.
- **T27 — inspeção repetida de p-valores:** protocolos confirmatórios exigem regra fixa/predefinida; parada orientada por p-valor, significância ou conveniência é bloqueada com `OPTIONAL_STOPPING_FORBIDDEN`.
- **T28 — reprodutibilidade:** com seed, hash dos dados, commit de código, hash de ambiente e protocolo fixos, o conteúdo científico normalizado produz o mesmo SHA-256 mesmo quando IDs/timestamps voláteis mudam.
- **T29 — cartões correlacionados:** a cobertura `Q_h(P)` é calculada conjuntamente sobre os mesmos resultados 15-de-25 por enumeração exata; probabilidades individuais não são multiplicadas como se cartões fossem independentes.

A aproximação de independência pode aparecer apenas como diagnóstico comparativo em T29; o campo canônico `independence_assumption_used` permanece `false`.

Esses testes são controles de risco e integridade metodológica. **Nenhum deles estabelece vantagem preditiva.**

## Integridade de backtest

A versão 1.1.5 fechou T20–T23 da fase C4 e aplica o mesmo contrato ao walk-forward real M1/M2:

- **T20 — futuro entre as variáveis:** qualquer variável com disponibilidade posterior ao último concurso do treino gera `LOOKAHEAD_LEAKAGE_DETECTED` e bloqueia o experimento antes da pontuação;
- **T21 — transformação ajustada no futuro:** transformação cujo `fitted_through_contest` ultrapassa o corte de treino gera `TRANSFORM_FIT_LEAKAGE_DETECTED`;
- **T22 — janela falha:** a janela permanece no denominador e no ledger com estado `FAILED`, tipo e mensagem do erro; não existe omissão silenciosa;
- **T23 — pouca evidência:** quantidade/cobertura insuficiente de janelas retorna `INCONCLUSIVE`, mantendo `predictive_evidence=NOT_ESTABLISHED` mesmo que as janelas válidas tenham score favorável.

M0 (`Brier=0,24`) aparece em toda janela do ledger. O resultado M1/M2 expõe `planned_windows`, `successful_windows`, `failed_windows`, `success_rate`, `backtest_status`, `failed_window_ids` e um hash SHA-256 do ledger normalizado.

## Laboratório de alternativas controladas

A versão 1.1.4 adicionou duas provas sintéticas predefinidas da fase científica C3:

- **T17 — viés marginal controlado:** uma dezena-alvo recebe probabilidade conhecida maior que 0,6; a família marginal canônica, corrigida por Holm, mede potência empírica em séries independentes.
- **T18 — memória temporal controlada:** um kernel simétrico retém parte das dezenas do concurso anterior com probabilidade predefinida, preservando 15-de-25 e sem privilegiar uma dezena; o teste temporal deve detectar dependência enquanto a família marginal ajustada permanece sem rejeição.

Essas provas medem sensibilidade e separação de mecanismos em dados sintéticos conhecidos. Elas **não constituem evidência de vantagem preditiva no histórico real**.

## RIS categórico

A linha 1.x **não produz RIS numérico**. São invariantes:

- `numeric_ris_enabled = false`;
- `score = null`;
- `COMPATIBLE` não significa prova de aleatoriedade;
- `ALERT` não significa vantagem preditiva;
- alerta de regime retrospectivo não é alerta emitido em tempo real;
- estado categórico não promove modelo automaticamente.

As seis dimensões canônicas são: integridade dos dados, uniformidade, coocorrência, temporal, regime e evidência preditiva. O contrato completo está em `docs/RIS_CATEGORICAL.md`.

A API `GET /v1/ris` e a Operator Console usam a mesma autoridade matemática em `sare_lotofacil.analysis.ris`; não existe fórmula paralela por canal.

## Operação

A operação ocorre exclusivamente por workflows do GitHub.

Fluxo canônico:

1. código e protocolos permanecem versionados em `main`;
2. CI e gates científicos validam o commit;
3. `GitHub Operational Cycle` lê `operations/state`;
4. o SQLite transitório é reconstruído no runner do GitHub;
5. resultados, hashes e ledger são verificados;
6. somente estado textual validado é persistido em `operations/state`;
7. artefatos da execução são publicados no GitHub;
8. um segundo job audita o estado já commitado.

Falha em qualquer gate impede alteração do estado operacional canônico.

### Console do operador

`SARE Operator Console` permite executar diretamente pelo GitHub, sem terminal externo:

- status do estado canônico;
- auditoria de `operations/state`;
- análise Core;
- RIS categórico auditável;
- geração de carteira combinatória uniforme;
- exportação de relatório operacional.

A console é read-only. A atualização do histórico e do ledger prospectivo continua exclusiva do `GitHub Operational Cycle`.

## Persistência e recuperação

O Git não usa SQLite como memória permanente. O estado canônico é textual, versionável e auditável no branch `operations/state`, incluindo os manifests e ledgers definidos pelo contrato operacional.

Cada execução reconstrói os artefatos transitórios a partir desse estado. Recuperação significa reproduzir o estado a partir do histórico Git e comprovar novamente integridade e proveniência dentro do GitHub Actions.

## Hardening GitHub-only

A política executável está em `governance/github-only-policy.json`. O gate `scripts/verify_github_governance.py` impede runners self-hosted, Actions não fixados por SHA e workflows não autorizados com `contents: write`.

Desde a release 1.1.1, os Actions oficiais canônicos usam variantes com runtime Node 24, preservando o pin por SHA.

A configuração-alvo dos Rulesets nativos está em `docs/GITHUB_NATIVE_RULESET.md`. A ativação administrativa desses Rulesets é a única etapa de P0 que o conector GitHub atual não consegue realizar diretamente.

## Provas e documentação

- autoridade operacional: `docs/GITHUB_OPERATIONS.md`;
- console operacional: `docs/OPERATOR_CONSOLE.md`;
- contrato RIS: `docs/RIS_CATEGORICAL.md`;
- rulesets nativos: `docs/GITHUB_NATIVE_RULESET.md`;
- operação e política GitHub-only: `docs/OPERACAO.md`;
- matriz de comprovação: `docs/MISSION_PROVEN.md`;
- identidade da especificação-fonte: `docs/SOURCE_SPEC.md`;
- ambiente validado: `requirements.lock.txt`;
- testes automatizados: `tests/`;
- workflows: `.github/workflows/`.

`MISSION_PROVEN` só pode ser declarado por uma cadeia material de evidência no GitHub ligando commit, workflow run, artifact, provenance, estado e gates aplicáveis.
