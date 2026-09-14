# SARE Lotofácil — Console Operacional GitHub-only

Toda operação canônica é executada em GitHub Actions. Não é necessário terminal, PC local, VPS ou servidor externo.

## Atualizar histórico e ciclo prospectivo

Workflow: `.github/workflows/github-operations.yml` (`GitHub Operational Cycle`).

Pode ser disparado manualmente por `workflow_dispatch` e também roda diariamente. É o único workflow autorizado a escrever em `operations/state`.

Ele:

1. valida código, testes, `doctor` e governança;
2. lê `operations/state`;
3. consulta a CAIXA para concursos novos;
4. avalia previsões pendentes quando o resultado oficial existe;
5. congela a próxima previsão antes do resultado;
6. verifica o estado antes do commit;
7. persiste somente em `operations/state`;
8. executa auditoria independente após o commit.

## Console do operador

Workflow: `.github/workflows/operator-console.yml` (`SARE Operator Console`).

É estritamente read-only e sempre audita `operations/state` antes de executar a ação solicitada.

Ações disponíveis:

- `status`: resumo do estado canônico;
- `audit-state`: auditoria do estado e hashes;
- `analyze-state`: análise Core do histórico canônico;
- `ris-categorical`: executa o painel RIS categórico nas seis dimensões canônicas; nunca produz nota numérica e preserva `score=null`;
- `generate-portfolio`: gera carteira combinatória uniforme como artefato, preservando a etiqueta `CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`;
- `export-report`: exporta relatório operacional JSON + Markdown.

O contrato científico do RIS está em `docs/RIS_CATEGORICAL.md`. A mesma autoridade de cálculo é usada pela API e pela Console; não existe fórmula matemática duplicada no workflow.

Os resultados são publicados como GitHub Artifacts e não alteram o estado canônico.

## Verificação do histórico real

Workflow: `.github/workflows/real-history-check.yml` (`Real History Check`).

Executa a verificação independente do histórico e publica artefatos de evidência.

## Prova de release

Workflow: `.github/workflows/release-proof.yml` (`Release Proof`).

Constrói o wheel, instala em ambiente limpo GitHub-hosted e executa a prova operacional da release.

## Governança

`governance/github-only-policy.json` define a autoridade, branches canônicos, runners permitidos, workflow escritor e SHAs dos Actions permitidos.

`scripts/verify_github_governance.py` é gate obrigatório em CI e nos principais workflows. O gate também exige que o RIS categórico permaneça exposto e materialmente provado pela Console.

A proteção nativa de branches por Ruleset é descrita em `docs/GITHUB_NATIVE_RULESET.md`; essa configuração administrativa é a única etapa que não pode ser aplicada pelo conector GitHub atual.
