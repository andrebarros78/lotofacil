# SARE Lotofácil 1.1.10 — Contrato canônico de MISSION_PROVEN e SCOPE_SEAL

## Autoridade

O SARE Lotofácil é **GitHub-only**.

- código, testes, documentação, protocolos e workflows: `main`;
- estado operacional persistente: `operations/state`;
- execução canônica: GitHub Actions;
- evidência de execução: GitHub Artifacts;
- proveniência: Git history.

Este documento descreve o estado operacional vigente da linha 1.1.10. Documentos históricos `MISSION_PROVEN_1_1_x.md` permanecem como registros das respectivas etapas e não substituem este contrato atual.

## Objetivo de engenharia

O objetivo do escopo é operar autonomamente o ciclo Lotofácil com integridade temporal e rastreabilidade:

`ingestão oficial -> avaliação da previsão congelada -> relatório pós-concurso -> aprendizado persistente -> challenger isolado -> próxima previsão prospectiva`

O alvo operacional de otimização do cartão primário é **15 acertos em 15 dezenas**. Esse alvo não constitui, por si só, prova de capacidade preditiva.

## PRIMARY_CARD e integridade temporal

A decisão principal continua sendo um `PRIMARY_CARD` de 15 dezenas para o próximo concurso canônico. A previsão para N deve ser congelada usando somente dados disponíveis até N-1.

São proibidos:

- reconstrução retroativa de cartão depois do resultado;
- alteração de payload congelado sem invalidar sua identidade;
- uso do resultado N para fabricar a previsão de N;
- promoção de conclusão científica a partir de um único concurso.

Carteiras múltiplas continuam sendo capacidade secundária e não substituem o `PRIMARY_CARD`.

## Contrato obrigatório de ingestão e auditoria

A ingestão de um resultado oficial só é considerada operacionalmente completa quando o fluxo produz e persiste a auditoria correspondente.

O `Post Contest Flow Contract` deve verificar, de forma fail-closed:

- resultado oficial canônico;
- previsão prospectiva correspondente quando existente;
- avaliação do concurso;
- relatório pós-concurso persistido;
- análise e sugestões de melhoria;
- entrega em JSON e Markdown do relatório mais recente;
- ausência de reconstrução retrospectiva de evidência.

Relatórios de lacuna de processo permanecem registrados como lacunas, sem fabricar `hits` ausentes.

## Learning Ledger

`learning_ledger.json` é a memória estruturada de aprendizado pós-concurso baseada exclusivamente em relatórios avaliáveis.

Cada entrada registra:

- concurso;
- `hits`;
- `target_hits = 15`;
- `gap_to_15`;
- selecionadas que falharam;
- sorteadas omitidas;
- métricas e achados do relatório.

O ledger acumula recorrências para orientar hipóteses e challengers, porém preserva:

- `single_contest_retuning_allowed = false`;
- `retroactive_rewrite_allowed = false`;
- `champion_auto_promotion_allowed = false`;
- validação prospectiva predeclarada para challengers.

## Challenger adaptativo

O challenger adaptativo permanece isolado do champion e segue a sequência temporal:

`freeze N -> observar N -> avaliar N -> freeze N+1`

Replay para o mesmo alvo deve ser idempotente. Um challenger pode produzir hipótese de melhoria, mas não pode substituir automaticamente o champion nem reclassificar evidência retrospectiva como preditiva.

## Estado científico

`MISSION_PROVEN` e `SCOPE_SEALED` são estados de engenharia, operação, segurança e reprodutibilidade.

Eles **não** significam que 15/15 seja atingível de forma consistente nem que exista vantagem preditiva demonstrada.

Até evidência prospectiva suficiente e promoção científica formal:

`predictive_evidence = NOT_ESTABLISHED`

Essa condição é compatível com um escopo de engenharia completamente selado.

## Gates obrigatórios

O SHA final de `main` precisa concluir com sucesso os gates aplicáveis ao fechamento, incluindo:

- CI e suíte de regressão;
- `SARE Stable Merge Gates`;
- CodeQL e Repository Sanitization;
- Release Proof;
- GitHub Operational Cycle e auditoria do estado commitado;
- Post Contest Flow Contract;
- Post Contest Learning Ledger;
- Adaptive Primary Challenger quando disparado pelo ciclo;
- SARE Operator Console Proof;
- Scope Seal Proof.

Required checks nunca podem ser contornados para fechar o escopo.

## Persistência e recuperação

O estado canônico em `operations/state` deve permanecer íntegro e verificável, incluindo histórico, ledgers, relatórios e challenger derivados aplicáveis.

O fechamento terminal exige prova material de:

- integridade de persistência;
- idempotência/replay;
- backup e restore;
- restart e endurance proporcional ao escopo;
- rollback/reconstrução da baseline;
- readiness baseada em dependências reais.

## Segurança e supply chain

O fechamento terminal exige:

- repositório sanitizado sem segredo detectado indevidamente;
- credenciais somente por mecanismos autorizados da plataforma;
- actions externas pinadas;
- permissões mínimas e writers autorizados;
- auditoria de vulnerabilidades de dependências;
- SBOM;
- build e instalação limpa do wheel correspondente à fonte selada.

## MISSION_PROVEN

`MISSION_PROVEN` pode ser declarado somente quando o objetivo funcional do escopo estiver comprovado no SHA final, com integrações, persistência e gates aplicáveis em `success` e sem falha crítica conhecida.

Depois de `MISSION_PROVEN`, o fechamento não termina: inicia-se imediatamente `SCOPE_SEAL`.

## SCOPE_SEAL

O Scope Seal é auditoria terminal independente e deve assumir que as provas anteriores podem estar erradas.

Ele revalida, no SHA final:

- identidade e limpeza da baseline;
- instalação bloqueada e compilação;
- suíte completa;
- sanitização/secret policy;
- vulnerabilidades e SBOM;
- build e hash do wheel;
- instalação limpa e identidade de release;
- persistência, backup e restore;
- health, readiness, restart e endurance;
- rollback/reconstrução;
- Evidence Manifest.

Falha no Scope Seal revoga `MISSION_PROVEN` até correção e nova execução completa.

## Critério terminal

Somente pode ser declarado `SCOPE_SEALED` quando:

1. o SHA final de `main` é identificado e protegido pelos gates;
2. o objetivo operacional foi comprovado;
3. contratos pós-concurso e aprendizado estão operacionais;
4. `operations/state` contém o estado persistente esperado;
5. testes, segurança, dependências e supply chain estão aprovados;
6. backup, restore, restart, recovery e rollback estão comprovados quando aplicáveis;
7. documentação corresponde ao runtime;
8. o Scope Seal independente termina em `success`;
9. o Evidence Manifest referencia exatamente o SHA, árvore, artefato e execução selados;
10. não existe falha crítica conhecida aberta.

O estado científico continua reportado separadamente e sem inflação de claims.
