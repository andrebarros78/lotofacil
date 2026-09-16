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

O banco SQLite não é usado como memória permanente do Git. A memória canônica persistida é textual e versionável: `canonical_history.json`, `bootstrap_manifest.json`, `prospective_ledger.json`, `operator_card_ledger.json` quando inicializado e `latest.json`. Cada execução reconstrói um SQLite a partir desse estado, exige `integrity_check=ok` e publica o banco como artefato de prova.

## Ciclo automático

`GitHub Operational Cycle` roda diariamente às 03:15 UTC e também aceita execução manual. Antes de alterar qualquer estado, executa a suíte completa e `sare_lotofacil doctor`. Se qualquer gate falhar, o branch `operations/state` não é modificado.

Quando os gates passam, o ciclo:

1. inicializa o histórico canônico a partir da fonte histórica corroborada e completa lacunas somente pela CAIXA;
2. nas execuções seguintes, usa o histórico canônico já commitado e busca diretamente na CAIXA apenas concursos novos;
3. publica um snapshot reproduzível e executa o Core retrospectivo;
4. avalia previsões prospectivas antigas cujo resultado oficial já exista;
5. congela uma única previsão científica para `último_concurso + 1`;
6. grava SHA-256 do payload da previsão antes de qualquer avaliação;
7. atualiza o ledger e o relatório, valida tudo novamente e faz commit em `operations/state`;
8. um segundo job faz novo checkout do estado já commitado e recalcula scores/hashes independentemente.

A unicidade acima pertence à **previsão científica prospectiva**, não limita a quantidade de cartões solicitados pelo operador.

## Cartões operacionais sob demanda

O workflow `SARE Operator Card Freeze` é o caminho canônico para comandos de geração de cartões feitos pelo operador.

- cada solicitação positiva deve ser atendida e adicionada ao estado, sem substituir solicitações anteriores;
- várias solicitações para o mesmo concurso são cumulativas;
- `1` seguido de `1` congela dois novos cartões distintos;
- uma sequência `1 + 1 + 10 + 1 + 4` acrescenta 17 cartões; se seis já estavam congelados, o total passa a 23;
- cartões repetidos para o mesmo concurso são proibidos;
- cartões científicos já congelados em `prospective_ledger.json` são tratados como combinações reservadas e não podem ser duplicados pelo ledger do operador;
- não existe o antigo limite operacional de 100 cartões por solicitação neste caminho; a limitação absoluta é apenas o espaço matemático de `C(25,15) = 3.268.760` combinações distintas por concurso;
- cada request registra cursor de geração, cartões, hashes, snapshot do estado e SHA-256 do request;
- `operator_card_ledger.json` é append-only e auditado antes de qualquer persistência;
- a geração operacional continua rotulada `CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA`.

O console read-only pode continuar produzindo prévias e diagnósticos, mas uma ordem do operador para **gerar cartões** deve usar o workflow de congelamento, para que os resultados sejam persistidos canonicamente em `operations/state`.

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
- divergência entre ledger e relatório operacional;
- adulteração do ledger de cartões do operador;
- duplicação de cartão operacional no mesmo concurso;
- colisão com cartão primário já congelado para o mesmo concurso.

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
