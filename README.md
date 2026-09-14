# SARE Lotofácil

Sistema de Análise de Randomicidade e Eventos para a Lotofácil.

## Release

**SARE Core 1.0 + SARE Operational 1.1 — versão 1.1.1.**

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
- carteiras uniformes com etiqueta obrigatória de ausência de vantagem comprovada;
- verificação SHA-256 de evidências persistidas;
- reconstrução determinística do SQLite operacional em GitHub Actions com `integrity_check`;
- CI Python 3.12/3.13, Real History Check, GitHub Operational Cycle e Release Proof.

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
- geração de carteira combinatória uniforme;
- exportação de relatório operacional.

A console é read-only. A atualização do histórico e do ledger prospectivo continua exclusiva do `GitHub Operational Cycle`.

## Persistência e recuperação

O Git não usa SQLite como memória permanente. O estado canônico é textual, versionável e auditável no branch `operations/state`, incluindo os manifests e ledgers definidos pelo contrato operacional.

Cada execução reconstrói os artefatos transitórios a partir desse estado. Recuperação significa reproduzir o estado a partir do histórico Git e comprovar novamente integridade e proveniência dentro do GitHub Actions.

## Hardening GitHub-only

A política executável está em `governance/github-only-policy.json`. O gate `scripts/verify_github_governance.py` impede runners self-hosted, Actions não fixados por SHA e workflows não autorizados com `contents: write`.

A release 1.1.1 migra os Actions oficiais canônicos para variantes com runtime Node 24, preservando o pin por SHA.

A configuração-alvo dos Rulesets nativos está em `docs/GITHUB_NATIVE_RULESET.md`. A ativação administrativa desses Rulesets é a única etapa de P0 que o conector GitHub atual não consegue realizar diretamente.

## Provas e documentação

- autoridade operacional: `docs/GITHUB_OPERATIONS.md`;
- console operacional: `docs/OPERATOR_CONSOLE.md`;
- rulesets nativos: `docs/GITHUB_NATIVE_RULESET.md`;
- operação e política GitHub-only: `docs/OPERACAO.md`;
- matriz de comprovação: `docs/MISSION_PROVEN.md`;
- identidade da especificação-fonte: `docs/SOURCE_SPEC.md`;
- testes automatizados: `tests/`;
- workflows: `.github/workflows/`.

`MISSION_PROVEN` só pode ser declarado por uma cadeia material de evidência no GitHub ligando commit, workflow run, artifact, provenance, estado e gates aplicáveis.
