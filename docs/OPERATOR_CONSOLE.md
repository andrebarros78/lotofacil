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
6. a partir da 1.1.8, congela também o `PRIMARY_CARD` das novas previsões dentro do hash prospectivo;
7. verifica o estado antes do commit;
8. persiste somente em `operations/state`;
9. executa auditoria independente após o commit.

## Console do operador

Workflow: `.github/workflows/operator-console.yml` (`SARE Operator Console`).

É estritamente read-only e sempre audita `operations/state` antes de executar a ação solicitada.

Ações disponíveis:

- `status`: resumo do estado canônico;
- `audit-state`: auditoria do estado e hashes;
- `analyze-state`: análise Core do histórico canônico;
- `ris-categorical`: painel RIS categórico;
- `generate-primary-card`: produz o único cartão principal de 15 dezenas para o próximo concurso canônico, usando M1 como ranking primário e M2 somente como desempate;
- `generate-portfolio`: gera carteira combinatória uniforme opcional de 1 a 100 cartões;
- `export-report`: exporta relatório operacional JSON + Markdown.

## PRIMARY_CARD

O `PRIMARY_CARD` é a saída principal da 1.1.8.

Ele não usa seed aleatória. A decisão é determinística a partir dos vetores prospectivos M1/M2 associados ao concurso-alvo e possui `decision_sha256` próprio.

Para previsões novas, o cartão é congelado dentro da previsão. Para uma previsão legada já congelada sem o campo `primary_card`, como o alvo 3780 criado antes da 1.1.8, a Console deriva o cartão somente dos vetores M1/M2 já congelados, sem reescrever o ledger histórico.

O Artifact `primary_card.json` inclui:

- concurso-alvo;
- último concurso usado no treino;
- 15 dezenas;
- ranking completo das 25 dezenas;
- método de seleção;
- modelos utilizados;
- hash da decisão;
- snapshot do estado;
- origem da decisão.

## Carteira opcional

`generate-portfolio` continua existindo para cobertura combinatória. A faixa é `1–100`, mas esse caminho é distinto do `PRIMARY_CARD`: uma carteira uniforme de um cartão não substitui o seletor técnico principal.

Os resultados são publicados como GitHub Artifacts e não alteram o estado canônico.

## Verificação do histórico real

Workflow: `.github/workflows/real-history-check.yml` (`Real History Check`).

Executa a verificação independente do histórico e publica artefatos de evidência.

## Prova de release

Workflow: `.github/workflows/release-proof.yml` (`Release Proof`).

Constrói o wheel, instala em ambiente limpo GitHub-hosted e executa as provas da release. Na 1.1.8, o Artifact `primary-card-release-proof` e o marcador `PRIMARY_CARD_RELEASE_PROOF_PASS` são obrigatórios.

## Governança

`governance/github-only-policy.json` define a autoridade, branches canônicos, runners permitidos, workflow escritor e SHAs dos Actions permitidos.

`scripts/verify_github_governance.py` é gate obrigatório em CI e exige materialmente a presença e a prova operacional do `PRIMARY_CARD`.

A proteção nativa por Ruleset é hardening administrativo adicional e não interfere no funcionamento canônico do SARE.
