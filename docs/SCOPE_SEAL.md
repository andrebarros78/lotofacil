# SARE Lotofácil 1.1.10 — Escopo de Selagem

## Autoridade operacional

O produto canônico é **GitHub-only**.

Autoridades:

- `main`: código, testes, governança e workflows;
- `operations/state`: estado operacional append-only;
- GitHub Actions: executor canônico;
- GitHub Artifacts e Releases imutáveis: evidência e artefatos;
- Git history e rulesets: proveniência e proteção de autoridade.

Execuções em PC, VPS ou processos residentes são somente desenvolvimento/diagnóstico e não podem sustentar `MISSION_PROVEN` ou `SCOPE_SEALED`.

## Objetivo do escopo

Entregar e preservar o SARE Lotofácil 1.1.10 como software científico-operacional reproduzível, auditável e recuperável, mantendo separação explícita entre:

1. análise estatística/científica;
2. operação e persistência;
3. construção de carteiras;
4. auditoria pós-concurso;
5. RAG read-only;
6. agentes de engenharia governados;
7. release e recuperação.

O objetivo não inclui provar vantagem preditiva. O estado científico permanece:

`predictive_evidence = NOT_ESTABLISHED`.

## Capacidades incluídas

- invariantes e combinatória da Lotofácil;
- ingestão validada e fonte CAIXA;
- persistência SQLite transitória e reconstruível;
- snapshots e revisões imutáveis;
- baseline M0 e modelos experimentais governados;
- walk-forward, lockbox e bloqueios de leakage;
- RIS categórico;
- geração/auditoria de carteiras;
- freeze ledger e idempotência;
- post-contest learning controlado;
- Challenger isolado do Champion;
- API FastAPI para execução local/runner, com writes deny-by-default;
- CLI;
- RAG read-only;
- ecossistema de agentes governado;
- operator console GitHub;
- backup/restore;
- release reproduzível;
- disaster recovery GitHub-only;
- sanitização, secret policy, CodeQL, Dependabot e auditoria de dependências;
- rollback para a release formal protegida.

## Modos operacionais

### Canônico

`GITHUB_ONLY`

Toda mutação operacional canônica ocorre por workflows e estado versionado autorizado.

### Diagnóstico/local

`NON_CANONICAL_DIAGNOSTIC`

Pode executar CLI/API/testes localmente, mas não promove autoridade, readiness canônico ou evidência oficial.

### Read-only

RAG, consultas e relatórios podem operar sem autoridade de mutação.

### Write-enabled API

A API só habilita writes quando recebe um `write_token` configurado fora do código. Sem token configurado, writes retornam `WRITE_DISABLED`; sem credencial ou com credencial inválida, retornam erro de autenticação/autorização.

## Integrações obrigatórias

- GitHub repository/actions/artifacts/releases;
- PyPI durante reconstrução de dependências pinadas;
- fonte pública CAIXA quando ingestão oficial é executada.

Integrações experimentais ou agentes externos não adquirem autoridade sobre o estado canônico.

## Persistência

Persistência canônica:

- Git;
- `operations/state`;
- manifests/ledgers textuais;
- GitHub Artifacts/Releases.

SQLite é estado transitório reconstruível em runner e é coberto por backup/restore e `PRAGMA integrity_check`.

## Segurança aplicável

- rulesets de `main`, `operations/state` e tags terminais;
- sem bypass actors;
- required status checks;
- GitHub Actions com SHA pinning obrigatório;
- actions externas pinadas por commit SHA;
- Secret Scanning;
- Dependabot alerts;
- CodeQL;
- scanner de segredos/artefatos/runtime paths no repositório;
- proibição de `curl|wget | sh/bash` em workflows;
- deny-by-default para escrita na API;
- comparação constante de token;
- validação Pydantic `extra=forbid`;
- limite de body;
- idempotency keys e conflito fail-closed;
- proteção temporal/lockbox;
- freeze hashes e tamper detection;
- release/tag imutável;
- backup/restore/recovery;
- rollback para release formal.

## Controles NOT_APPLICABLE

Os controles abaixo não são silenciosamente aprovados; são `NOT_APPLICABLE` ao produto canônico atual:

- **multitenancy isolation**: não existe modelo de tenants no produto;
- **public-service rate limiting/perimeter WAF**: o SARE não é operado como serviço público residente; a API é runner/local e não é autoridade canônica externa;
- **application-managed TLS termination**: não há listener público canônico; transporte GitHub/PyPI/CAIXA é delegado aos provedores HTTPS;
- **application-managed encryption at rest of GitHub storage**: armazenamento canônico é serviço GitHub; o produto não mantém servidor/disco próprio;
- **host reboot recovery**: não existe host residente obrigatório; recuperação canônica é runner/reconstruction GitHub-only;
- **distributed tracing**: não há malha de microsserviços residente no baseline 1.1.10;
- **database migration rollback**: migrations SQLite são forward-preserving e testadas para preservação; rollback de schema não é contrato declarado;
- **tenant-to-tenant negative access**: sem tenants;
- **public DDoS protection**: sem endpoint público canônico.

## Known noncritical items

- a suíte possui um teste opcional de experimento LangGraph que é `SKIPPED` quando o framework não canônico não está instalado; isso é comportamento preexistente e deliberado, não conversão de falha em skip;
- FastAPI/Starlette emitem warnings de depreciação relativos ao TestClient atual; o lock auditado não possui vulnerabilidades conhecidas abertas e esses warnings não alteram o contrato funcional.

## Critério de selagem

O escopo só pode ser declarado `SCOPE_SEALED` quando o workflow `Scope Seal Proof` no SHA final:

- executa testes com contagem JUnit fail-closed;
- compila fonte/testes;
- passa sanitização;
- passa auditoria de dependências;
- gera SBOM;
- constrói wheel;
- instala wheel em ambiente limpo;
- executa doctor;
- prova backup/restore;
- prova health/readiness;
- prova autenticação negativa;
- prova restart e endurance bounded;
- reconstrói a baseline de rollback;
- produz manifesto runtime com hash.

Além disso, a auditoria terminal externa deve observar zero alertas abertos de Secret Scanning, Dependabot e CodeQL, rulesets ativos e nenhuma issue/PR crítica aberta.
