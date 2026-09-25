# SARE Lotofácil — Operação integral no GitHub

## Regra soberana GitHub-only

O GitHub é o único ambiente operacional canônico do produto.

Não existe requisito de instalação, execução, persistência, recuperação ou aceitação em PC local, VPS ou servidor externo. Execuções fora do GitHub podem servir a desenvolvimento ou diagnóstico, mas não podem alterar `operations/state`, produzir evidência oficial, promover readiness, fechar gaps ou sustentar `MISSION_PROVEN`.

## Separação de responsabilidades

- `main`: código, testes, protocolos, documentação e workflows.
- `release/v1.1.10`: alias imutável da baseline formal da release 1.1.10 quando aplicável ao fechamento de release.
- `operations/state`: estado operacional persistente e auditável.
- GitHub Actions: executor do ciclo automático, auditorias e provas.
- GitHub Artifacts: bancos reconstruídos, relatórios, SBOM e evidências de execução.
- Git history: trilha temporal e de proveniência.

O SQLite é reconstruído a partir do estado canônico e não é usado como memória permanente do Git. O estado persistente atual inclui, conforme aplicável ao ciclo:

- `canonical_history.json` e `canonical_prizes.json`;
- `bootstrap_manifest.json`;
- `prospective_ledger.json`;
- `operator_card_ledger.json`;
- `post_contest_reports.json`, `latest_post_contest_report.json` e `latest_post_contest_report.md`;
- `learning_ledger.json`;
- `adaptive_challenger.json`;
- `latest.json` e `state_commit.json`.

O estado derivado pós-ciclo permanece separado do recibo transacional do estado base quando necessário para preservar integridade e recuperação.

## Ciclo operacional canônico

`GitHub Operational Cycle` roda por agendamento, aceita execução manual e também pode ser disparado por alterações canônicas previstas no workflow. Antes de persistir estado, instala o ambiente, executa a suíte completa, `doctor` e gates de governança. Falha de gate impede mutação canônica.

O ciclo:

1. reconstrói o banco a partir do estado GitHub e exige integridade do SQLite;
2. consulta a CAIXA para reconciliar somente concursos oficiais novos;
3. atualiza histórico e snapshot reproduzível;
4. avalia previsões prospectivas já congeladas cujo resultado oficial passou a existir;
5. congela a previsão do próximo concurso usando somente dados até N-1;
6. mantém hashes e identidades de decisão verificáveis;
7. produz o relatório pós-concurso para toda avaliação disponível;
8. persiste o estado transacional e realiza auditoria independente do estado já commitado.

## Contrato obrigatório pós-concurso

Resultado oficial ingerido não encerra o ciclo por si só. O contrato operacional é:

`resultado oficial -> validação -> auditoria da previsão congelada -> relatório pós-concurso -> aprendizado estruturado -> challenger isolado -> próximo ciclo prospectivo`

O `Post Contest Flow Contract` verifica de forma fail-closed que o resultado oficial mais recente possui auditoria e relatório compatíveis com o ledger prospectivo, sem reconstrução retroativa de cartão.

O relatório pós-concurso registra, quando existe cartão prospectivamente congelado:

- cartão avaliado e resultado oficial;
- número de acertos;
- dezenas acertadas;
- selecionadas que não saíram;
- sorteadas omitidas;
- delta Brier contra o baseline uniforme;
- achados, correções e sugestões de melhoria.

Relatórios de lacuna de processo, como ausência histórica de cartão congelado, permanecem auditáveis, mas não são transformados artificialmente em aprendizado baseado em acertos.

## Learning Ledger — alvo operacional 15/15

`Post Contest Learning Ledger` converte somente relatórios realmente avaliáveis em `learning_ledger.json`.

Para cada concurso avaliável são persistidos:

- `hits`;
- `target_hits = 15`;
- `gap_to_15 = 15 - hits`;
- inclusões que falharam;
- vencedoras omitidas;
- delta Brier e achados do relatório.

O ledger também acumula frequências de erros de seleção e omissão. O relatório é entrada formal de aprendizado do sistema, mas não autoriza overfitting.

Guardrails obrigatórios:

- nenhum retuning baseado em um único concurso;
- nenhuma reescrita retroativa de previsão ou cartão congelado;
- nenhuma autopromoção do champion;
- challenger exige regra predeclarada e validação prospectiva.

## Challenger adaptativo isolado

`Adaptive Primary Challenger` é uma trilha experimental separada do champion. Ele pode aprender com o histórico canônico e com a sequência prospectiva já observada, mas não pode alterar retroativamente o champion nem converter ganho retrospectivo em evidência preditiva.

O fluxo adaptativo preserva a ordem temporal:

`freeze challenger N -> observar resultado oficial N -> avaliar challenger N -> freeze challenger N+1`

Replays para o mesmo alvo são idempotentes. Mudanças de challenger permanecem isoladas até satisfazerem critérios prospectivos predeclarados e revisão exigida pelo protocolo.

## Protocolo prospectivo e evidência científica

O SARE preserva separação entre engenharia e eficácia científica. Previsões do concurso N só podem usar concursos até N-1. Hashes e proveniência são verificados antes da avaliação.

A qualidade operacional pode ser otimizada em direção a 15 acertos, mas o estado científico continua sendo determinado por evidência prospectiva suficiente, e não pelo objetivo desejado.

Enquanto os critérios científicos não forem estabelecidos e formalmente promovidos:

`predictive_evidence = NOT_ESTABLISHED`

Nenhum workflow, relatório, Learning Ledger ou challenger pode transformar `MISSION_PROVEN` de engenharia em alegação de vantagem preditiva comprovada.

## Integridade, segurança e recuperação

A operação canônica exige:

- permissões de workflow mínimas e writers explicitamente autorizados pela governança;
- actions externas pinadas por SHA;
- branch `main` protegida por PR e required checks;
- `operations/state` protegido contra deleção e non-fast-forward;
- sanitização de repositório e bloqueio de material de credencial/secret;
- verificação de dependências e SBOM nos gates terminais;
- transação de estado recuperável, idempotência e replay controlado;
- backup/restore, restart/endurance e rollback comprovados pelo Scope Seal quando o escopo é selado.

## Condição de aceitação

A evidência operacional válida deve ligar:

`commit -> workflow run -> artifact -> provenance -> operations/state -> auditoria`

Um fechamento terminal somente é válido quando o SHA final de `main` passa pelos gates aplicáveis, o ciclo operacional e os contratos pós-concurso são bem-sucedidos, o estado persistente é auditável, o Scope Seal independente passa e o Evidence Manifest corresponde exatamente à fonte e aos artefatos observados.
