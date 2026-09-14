# SARE Lotofácil

Sistema de Análise de Randomicidade e Eventos para a Lotofácil.

## Release

**SARE Core 1.0 + SARE Operational 1.1 — versão 1.1.5.**

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
- ingestão validada, revisões imutáveis e artefatos de fonte;
- fonte oficial CAIXA e histórico corroborado por checkpoints oficiais;
- protocolo científico congelado por hash, hipóteses e experimentos auditáveis;
- promoção de modelo bloqueada enquanto a evidência não for `REPLICATED`;
- RIS categórico auditável com seis dimensões, sem score numérico na linha 1.x;
- temporal RIS por permutação de concursos completos nos lags predefinidos 1, 2, 3, 5 e 10, com correção de Holm;
- regime RIS por scan global retrospectivo, limiar calibrado em nulo e falso alarme validado em amostra nula independente;
- laboratório de alternativas controladas com T17 para potência sob viés marginal e T18 para memória temporal sem confusão marginal;
- guardrails T20/T21 contra uso do alvo/futuro e transformações ajustadas fora do treino;
- auditoria T22/T23 de janelas de backtest com denominador explícito, falhas registradas e amostra insuficiente como inconclusiva;
- simuladores de alternativa controlada para medir sensibilidade sem atribuir causalidade;
- carteiras uniformes com etiqueta obrigatória de ausência de vantagem comprovada;
- verificação SHA-256 de evidências persistidas;
- reconstrução determinística do SQLite operacional em GitHub Actions com `integrity_check`;
- CI Python 3.12/3.13, Real History Check, GitHub Operational Cycle e Release Proof.

## Laboratório de alternativas controladas

Desde a versão 1.1.4, duas provas sintéticas predefinidas da fase científica C3 permanecem obrigatórias:

- **T17 — viés marginal controlado:** uma dezena-alvo recebe probabilidade conhecida maior que 0,6; a família marginal canônica, corrigida por Holm, mede potência empírica em séries independentes.
- **T18 — memória temporal controlada:** um kernel simétrico retém parte das dezenas do concurso anterior com probabilidade predefinida, preservando 15-de-25 e sem privilegiar uma dezena; o teste temporal deve detectar dependência enquanto a família marginal ajustada permanece sem rejeição.

Essas provas medem sensibilidade e separação de mecanismos em dados sintéticos conhecidos. Elas **não constituem evidência de vantagem preditiva no histórico real**.

## Integridade temporal e de backtest

A versão 1.1.5 adiciona provas T20–T23 da fase científica C4:

- **T20 — leakage de alvo/futuro:** `feature_offsets` aceita apenas offsets negativos; usar o alvo (`0`) ou futuro (`>0`) bloqueia o protocolo com `FUTURE_OR_TARGET_FEATURE_OFFSET`.
- **T21 — transformação fora do treino:** `transform_fit_scope` canônico é `TRAIN_ONLY`; ajuste em `FULL_HISTORY` é bloqueado com `TRANSFORM_FIT_OUTSIDE_TRAIN`.
- **T22 — falha de janela:** a política obrigatória é `COUNT_IN_DENOMINATOR`; janelas que falham continuam no denominador e aparecem no relatório, que vira `INCONCLUSIVE_WINDOW_FAILURES`.
- **T23 — poucas janelas:** quando há menos janelas que o mínimo predefinido, o estado é `INCONCLUSIVE_INSUFFICIENT_WINDOWS` e `advantage_eligible=false`, mesmo se os resultados observados parecerem favoráveis.

Esses controles medem **integridade metodológica**. Passá-los não constitui vantagem preditiva e não promove modelo.

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
- testes automatizados: `tests/`;
- workflows: `.github/workflows/`.

`MISSION_PROVEN` só pode ser declarado por uma cadeia material de evidência no GitHub ligando commit, workflow run, artifact, provenance, estado e gates aplicáveis.
