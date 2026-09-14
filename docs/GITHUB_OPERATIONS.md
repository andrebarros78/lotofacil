# SARE Lotofácil — Operação integral no GitHub

## Regra soberana GitHub-only

O GitHub é o único ambiente operacional canônico do produto.

Não existe requisito de instalação, execução, persistência, recuperação ou aceitação em PC local, VPS ou servidor externo. Nenhum desses ambientes pode ser condição para continuidade do SARE.

Execuções fora do GitHub são estritamente não canônicas: podem servir para desenvolvimento ou diagnóstico, mas não podem alterar `operations/state`, produzir evidência oficial, promover readiness, fechar gaps ou sustentar `MISSION_PROVEN`.

## Separação de responsabilidades

- `main`: código, testes, protocolos e workflows.
- `release/v1.1.0`: baseline comprovada da release 1.1.0.
- `operations/state`: estado operacional persistente e auditável.
- GitHub Actions: executor do ciclo automático e das provas.
- GitHub Artifacts: SQLite reconstruído, relatórios e evidências de cada execução.
- Git history: trilha temporal e de proveniência.

O banco SQLite não é usado como memória permanente do Git. A memória canônica persistida é textual e versionável: `canonical_history.json`, `bootstrap_manifest.json`, `prospective_ledger.json` e `latest.json`. Cada execução reconstrói um SQLite a partir desse estado, exige `integrity_check=ok` e publica o banco como artefato de prova.

## Ciclo automático

`GitHub Operational Cycle` roda diariamente às 03:15 UTC e também aceita execução manual. Antes de alterar qualquer estado, executa a suíte completa e `sare_lotofacil doctor`. Se qualquer gate falhar, o branch `operations/state` não é modificado.

Quando os gates passam, o ciclo:

1. inicializa o histórico canônico a partir da fonte histórica corroborada e completa lacunas somente pela CAIXA;
2. nas execuções seguintes, usa o histórico canônico já commitado e busca diretamente na CAIXA apenas concursos novos;
3. publica um snapshot reproduzível e executa o Core retrospectivo;
4. avalia previsões prospectivas antigas cujo resultado oficial já exista;
5. congela uma única previsão para `último_concurso + 1`;
6. grava SHA-256 do payload da previsão antes de qualquer avaliação;
7. atualiza o ledger e o relatório, valida tudo novamente e faz commit em `operations/state`;
8. um segundo job faz novo checkout do estado já commitado e recalcula scores/hashes independentemente.

## Protocolo prospectivo congelado

O protocolo `prospective-m1-v1` não pode ser alterado depois de o ledger existir.

- baseline: M0 uniforme, Brier 0,24;
- modelo primário: M1 frequência regularizada, lambda 100;
- modelo secundário: M2 exponencial, alpha 0,05;
- métrica primária: `Delta Brier = Brier(M0) - Brier(M1)`;
- efeito mínimo registrado: `0.0005`;
- coorte A: 100 previsões realmente futuras;
- coorte B de replicação: 100 previsões realmente futuras adicionais;
- cada previsão de concurso N só pode usar concursos até N-1;
- as duas coortes precisam, separadamente, ter média acima do efeito mínimo e limite inferior do IC95% acima do efeito mínimo.

Mesmo se as duas coortes passarem, o sistema retorna `PROSPECTIVE_REPLICATION_CRITERIA_MET_REVIEW_REQUIRED`: não há promoção preditiva automática. Isso preserva a regra científica original de revisão antes de declarar vantagem.

## O que o GitHub prova

O histórico de commits do branch `operations/state` fornece marca temporal independente do código da previsão. Uma previsão congelada em um commit anterior ao resultado não pode ser recalculada retrospectivamente sem deixar rastro no Git.

`verify_github_operational_state.py` recalcula hashes, Brier e deltas a partir do histórico canônico e recusa:

- alteração de protocolo;
- vazamento temporal (`training_last_contest >= target_contest`);
- modificação do payload previsto;
- score divergente do resultado canônico;
- previsão pendente para concurso cujo resultado já esteja no histórico;
- divergência entre ledger e relatório operacional.

## Estados de eficácia prospectiva

- `UNDER_TEST_COHORT_A`: menos de 100 previsões avaliadas.
- `PRIMARY_NOT_REPLICATED_COHORT_A`: a primeira coorte terminou sem cumprir o gate.
- `UNDER_TEST_COHORT_B`: primeira coorte passou; segunda ainda incompleta.
- `PRIMARY_NOT_REPLICATED_COHORT_B`: a replicação não confirmou.
- `PROSPECTIVE_REPLICATION_CRITERIA_MET_REVIEW_REQUIRED`: as duas coortes cumpriram o critério matemático; revisão independente ainda é obrigatória.

Até revisão e promoção formal, `predictive_evidence` permanece `NOT_ESTABLISHED` e as carteiras continuam sem alegação de vantagem preditiva comprovada.

## Condição de aceitação

A prova operacional válida deve permanecer integralmente no GitHub e ligar:

`commit -> workflow run -> artifact -> provenance -> operations/state -> auditoria`

Quando houver dependências, recovery ou integração, a evidência correspondente também deve ser produzida em GitHub Actions. Prova obtida somente em máquina externa é informação auxiliar, nunca evidência canônica.
