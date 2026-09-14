# SARE Lotofácil — Console Operacional GitHub-only

Toda operação canônica é executada em GitHub Actions. Não é necessário terminal, PC local, VPS ou servidor externo.

## Atualizar histórico, rateios e ciclo prospectivo

Workflow: `.github/workflows/github-operations.yml` (`GitHub Operational Cycle`).

Pode ser disparado manualmente por `workflow_dispatch` e também roda diariamente. É o único workflow autorizado a escrever em `operations/state`.

Na operação `cycle`, ele:

1. valida código, testes, `doctor` e governança;
2. lê `operations/state`;
3. consulta a CAIXA para concursos novos;
4. avalia previsões pendentes quando o resultado oficial existe;
5. congela a próxima previsão antes do resultado;
6. atualiza `canonical_prizes.json` com rateios oficiais e revisões;
7. audita automaticamente carteiras persistidas cujo concurso-alvo já tenha resultado e rateio;
8. verifica todo o estado antes do commit;
9. persiste somente em `operations/state`;
10. executa auditoria independente após o commit.

## Registrar carteira canônica

No mesmo workflow `GitHub Operational Cycle`, execute manualmente com:

- `operation = register_portfolio`;
- `card_count = 3..100`;
- `seed = 0` para usar o concurso-alvo como seed, ou informe uma seed inteira;
- `target_contest = 0` para usar o próximo concurso já congelado no estado prospectivo.

O sistema recusa registro retroativo e também recusa pular para um concurso posterior: a carteira canônica só pode mirar exatamente `next_prediction_target`.

O registro gera `portfolio_id` determinístico, persiste os cartões originais em `operations/portfolio_ledger.json`, grava proveniência do código e do estado anterior e mantém obrigatoriamente:

`CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`

Registrar uma carteira **não significa registrar uma compra**. Por padrão:

- `purchase.recorded = false`;
- `actual_cost_cents = null`;
- resultado financeiro real = não aplicável.

O custo da carteira é apenas custo teórico até existir, em evolução futura explicitamente auditada, um registro real de compra.

Após o commit, um segundo job faz novo checkout de `operations/state` e audita o ledger de carteiras de forma independente.

## Auditoria econômica pós-concurso

Quando o concurso-alvo passa a existir no histórico oficial e seu rateio está em `canonical_prizes.json`, o ciclo automático audita a carteira original persistida.

A avaliação registra:

- dezenas oficiais do concurso;
- revisão do rateio utilizada;
- acertos de cada cartão;
- prêmio de cada cartão segundo sua faixa;
- contagem de cartões por faixa;
- prêmio total;
- custo teórico;
- resultado líquido hipotético;
- estado de compra real, que permanece falso/nulo quando não existe compra registrada.

A avaliação é idempotente. Se resultado ou rateio oficial for revisado, uma nova `evaluation_revision` é anexada e a avaliação anterior é preservada.

## Console do operador

Workflow: `.github/workflows/operator-console.yml` (`SARE Operator Console`).

É estritamente read-only e sempre audita `operations/state` antes de executar a ação solicitada. Quando existe ledger de carteiras, ele também é auditado antes da leitura.

Ações disponíveis:

- `status`: resumo do estado canônico;
- `audit-state`: auditoria do estado e hashes;
- `analyze-state`: análise Core do histórico canônico;
- `generate-portfolio`: gera carteira combinatória uniforme somente como artefato transitório;
- `recover-portfolio`: recupera a carteira original persistida pelo `portfolio_id`, sem regenerá-la;
- `export-report`: exporta relatório operacional JSON + Markdown.

Os resultados da Console são publicados como GitHub Artifacts e não alteram o estado canônico.

## Verificação do histórico real

Workflow: `.github/workflows/real-history-check.yml` (`Real History Check`).

Executa a verificação independente do histórico e publica artefatos de evidência.

## Prova de release

Workflow: `.github/workflows/release-proof.yml` (`Release Proof`).

Constrói o wheel, instala em ambiente limpo GitHub-hosted e executa a prova operacional da release.

## Governança

`governance/github-only-policy.json` define a autoridade, branches canônicos, runners permitidos, workflow escritor e SHAs dos Actions permitidos.

`scripts/verify_github_governance.py` é gate obrigatório em CI e nos principais workflows.

A proteção nativa de branches por Ruleset é descrita em `docs/GITHUB_NATIVE_RULESET.md`; essa configuração administrativa permanece rastreada separadamente e não introduz dependência de máquina externa.
