# SARE Lotofácil — Rulesets nativos obrigatórios

O repositório é GitHub-only. O código, a operação, a evidência e o estado canônico não dependem de PC, VPS ou servidor externo.

## Estado de automação

A política declarativa está em `governance/github-only-policy.json` e é validada por `scripts/verify_github_governance.py` em CI e nos workflows canônicos.

A criação/alteração de Rulesets nativos do GitHub exige uma operação administrativa que não está exposta pelo conector GitHub usado pelo operador automatizado. Portanto esta é a única etapa de hardening que permanece como ação administrativa externa.

## Ruleset `main`

Configuração-alvo:

- alvo: branch `main`;
- bloquear exclusão;
- bloquear force-push;
- exigir Pull Request antes de merge;
- exigir branch atualizada antes do merge quando suportado;
- exigir os checks do workflow `CI` em Python 3.12 e 3.13;
- impedir bypass rotineiro;
- permitir merge somente após os checks obrigatórios concluírem com sucesso.

## Ruleset `operations/state`

Configuração-alvo:

- alvo: branch `operations/state`;
- bloquear exclusão;
- bloquear force-push;
- preservar histórico linear quando suportado;
- não aceitar alterações humanas como caminho operacional normal;
- o escritor lógico autorizado é `.github/workflows/github-operations.yml`;
- toda alteração deve ser precedida por `GITHUB_OPERATIONAL_AUDIT_PASS` e seguida pelo job `committed-state-audit`.

## Proteções já automatizadas no repositório

Mesmo antes do ruleset nativo ser ativado, o repositório aplica:

- GitHub-hosted runner apenas;
- Actions fixados por SHA de 40 caracteres;
- `contents: write` permitido somente no workflow operacional canônico;
- job de auditoria pós-commit com `contents: read`;
- console do operador estritamente read-only;
- verificador de governança em CI e Release Proof;
- estado canônico separado em `operations/state`;
- nenhuma dependência operacional de PC/VPS.

## Critério de fechamento P0

P0 só pode ser marcado como `CLOSED` quando a API de Rulesets retornar regras ativas equivalentes para `main` e `operations/state`. Até lá, o estado correto é:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`
