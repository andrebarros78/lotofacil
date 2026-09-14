# SARE Lotofácil 1.1.8 — Contrato de MISSION_PROVEN

## Autoridade canônica

O SARE Lotofácil permanece **GitHub-only**.

- código, testes, protocolos e workflows: `main`;
- estado operacional persistente: `operations/state`;
- executor canônico: GitHub Actions;
- evidência transitória: GitHub Artifacts;
- proveniência: Git history;
- alias imutável da release: `release/v1.1.8`, criado somente depois dos gates pós-merge.

A release 1.1.8 é incremental sobre a 1.1.7. Todos os contratos T20–T39 e demais guardrails da 1.1.7 permanecem válidos conforme `release/v1.1.7:docs/MISSION_PROVEN.md`, exceto a evolução deliberada de T30: carteira opcional passa de `3–100` para `1–100` cartões.

## Objetivo 1.1.8 — PRIMARY_CARD

A saída principal para um concurso passa a ser um único `PRIMARY_CARD` de 15 dezenas.

O contrato é:

`1 concurso -> 1 PRIMARY_CARD -> 15 dezenas`

Carteira múltipla continua disponível como função opcional de cobertura e não substitui o `PRIMARY_CARD`.

## P-PRIMARY-CARD — seleção canônica

Implementação: `sare_lotofacil.portfolios.primary`.

A regra canônica é `M1_TOP15_M2_TIEBREAK_V1`:

1. M1 `M1_frequency_regularized_lambda_100` fornece o ranking primário das 25 dezenas;
2. M2 `M2_exponential_alpha_0.05` é usado somente para desempate de escores M1;
3. persistindo empate, o menor número é o desempate determinístico final;
4. as 15 primeiras posições formam o `PRIMARY_CARD`;
5. o cartão é armazenado ordenado crescentemente para representação;
6. nenhuma seed aleatória participa da seleção do `PRIMARY_CARD`.

A identidade da decisão inclui SHA-256 sobre alvo, último concurso de treino, cartão, ranking, nomes dos modelos, método e vetores de escores.

## P-TEMPORAL — somente N-1 para prever N

`target_contest` deve ser exatamente:

`training_last_contest + 1`

Qualquer outro alvo é rejeitado com:

`PRIMARY_CARD_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE`

O cartão para o concurso N não pode usar resultado, variável ou transformação disponível somente em N ou depois de N.

## P-FREEZE — congelamento prospectivo

Para novas previsões geradas a partir da 1.1.8, o `primary_card` é armazenado dentro da previsão prospectiva e entra no `prediction_sha256`.

Alterar posteriormente o cartão, ranking, modelos ou metadados cobertos pelo hash invalida a previsão.

A avaliação posterior não altera o objeto congelado. O número de acertos é registrado separadamente em `primary_card_evaluation`.

## P-LEGACY — previsão 3780 e previsões anteriores

Previsões congeladas antes da 1.1.8 não são reescritas para adicionar campos novos.

Quando uma previsão legada já possui vetores M1/M2 congelados, o Operator Console pode derivar o `PRIMARY_CARD` de forma read-only usando exclusivamente esses vetores. Nesse caso a origem é registrada como:

`DERIVED_FROM_FROZEN_LEGACY_MODEL_SCORES`

O hash histórico original continua verificável sob seu contrato original.

## P-PORTFOLIO — modo secundário

`generate_uniform_portfolio` aceita `1 <= card_count <= 100`.

Esse modo permanece separado do `PRIMARY_CARD`:

- `PRIMARY_CARD`: decisão técnica determinística dos modelos;
- `PORTFOLIO`: expansão combinatória opcional, com seed e cartões uniformes.

Aceitar um cartão em `PORTFOLIO` não transforma o algoritmo uniforme em seletor principal.

## P-CONSOLE — operação direta no GitHub

`SARE Operator Console` expõe:

`generate-primary-card`

A ação é read-only, audita `operations/state` antes da execução e produz `primary_card.json` em GitHub Artifact.

A prova operacional exige, entre outros:

- `GITHUB_OPERATOR_PRIMARY_CARD_PASS`;
- `card_count = 1`;
- `selection_method = M1_TOP15_M2_TIEBREAK_V1`;
- alvo igual ao próximo concurso canônico;
- treino terminando no concurso imediatamente anterior;
- `decision_sha256` registrado;
- proveniência do estado `operations/state` registrada.

## P-RELEASE — wheel instalado

`Release Proof` deve instalar o wheel 1.1.8 em ambiente limpo e produzir o Artifact:

`primary-card-release-proof`

O marcador obrigatório é:

`PRIMARY_CARD_RELEASE_PROOF_PASS`

A prova verifica materialmente:

- exatamente 15 dezenas únicas;
- uma única decisão principal;
- determinismo para mesma entrada;
- M1 como ranking primário;
- M2 apenas como desempate;
- identidade SHA-256;
- bloqueio de alvo diferente de N+1;
- seleção a partir de histórico;
- carteira opcional de um cartão suportada separadamente.

## Gates finais do mesmo SHA

Antes de declarar 1.1.8 `MISSION_PROVEN`, o SHA de `main` precisa ter todos os seguintes gates em `completed/success`:

- `CI` em Python 3.12 e 3.13, incluindo testes, doctor, governance e console smoke;
- `Release Proof` com `RELEASE_VERSION=1.1.8`, todas as provas preservadas da 1.1.7 e `PRIMARY_CARD_RELEASE_PROOF_PASS`;
- `Real History Check` com integridade e roundtrip aprovados;
- `GitHub Operational Cycle`, incluindo `cycle`, `committed-state-audit` e `economic-state-proof`;
- `SARE Operator Console Proof`, incluindo a ação `primary-card` sobre o estado canônico;
- governance gate em PASS;
- `main` e `release/v1.1.8` apontando para o mesmo SHA após criação do alias.

O manifesto permanente da release precisa registrar IDs dos runs, IDs/digests dos Artifacts, SHA do estado operacional e a decisão real de `PRIMARY_CARD` observada no Operator Console Proof.

## Sincronização final dos gates

O fechamento da 1.1.8 usa este próprio contrato como ponto de sincronização dos cinco workflows obrigatórios. A alteração de fechamento em `docs/MISSION_PROVEN.md` deve passar por PR/CI e, após merge em `main`, disparar no mesmo SHA final `CI`, `Release Proof`, `Real History Check`, `GitHub Operational Cycle` e `SARE Operator Console Proof`. O alias `release/v1.1.8` só pode ser criado depois de todos concluírem com `success` no mesmo SHA.

## Resultado científico

`MISSION_PROVEN` continua sendo exclusivamente status de engenharia.

O estado científico pode permanecer:

`predictive_evidence = NOT_ESTABLISHED`

A qualidade do `PRIMARY_CARD` é medida prospectivamente pelo número de acertos após cada resultado oficial, sem reescrever o cartão congelado.

## Hardening administrativo

Rulesets nativos do GitHub são hardening administrativo adicional. Sua ausência não bloqueia operação nem MISSION_PROVEN de engenharia sob o contrato atual, mas permanece registrada como pendência externa:

`P0_LOGICAL_HARDENING_COMPLETE_NATIVE_RULESET_PENDING`
