# CONSTRUCTION_PROVEN — Registro Canônico de Execução

**Projeto:** SARE Lotofácil  
**Repositório canônico:** `andrebarros78/lotofacil`  
**Estado-base de criação:** `main@9c731cfb6206a42b24198256bd16127cd6e39637`  
**Data de registro:** 2026-09-17  
**Classe:** plano executivo soberano, retomável e auditável  
**Objetivo terminal:** `CONSTRUCTION_PROVEN`

---

## 1. Finalidade e regra de retomada

Este documento transforma o plano de execução do SARE Lotofácil em um registro canônico de construção. Ele deve permitir que qualquer IA ou operador autorizado retome o trabalho sem depender de conversas anteriores.

A execução é estritamente sequencial. Uma etapa só pode ser declarada concluída quando seus critérios de prova forem satisfeitos por evidência verificável no GitHub canônico. Código escrito, documentação, intenção, workflow existente ou teste isolado não equivalem a prova de construção.

Ao retomar a missão, a IA deve:

1. ler este arquivo integralmente;
2. verificar o `HEAD` atual de `main` e comparar com o estado-base registrado;
3. listar PRs, issues, rulesets e workflows relevantes ainda abertos/ativos;
4. reconciliar divergências ocorridas após este registro;
5. executar a primeira etapa não comprovada;
6. nunca pular um bloqueio ou fabricar evidência ausente;
7. atualizar este registro ou um registro de evidência vinculado antes de declarar avanço de estado.

---

## 2. Definição de CONSTRUCTION_PROVEN

`CONSTRUCTION_PROVEN` significa que a construção integral definida neste plano foi implementada, integrada ao ramo canônico e comprovada por uma cadeia reproduzível de evidências.

Não significa vantagem preditiva comprovada. O estado científico do SARE continua separado do estado de construção. Resultado de loteria, desempenho de um cartão ou episódio retrospectivo não pode, isoladamente, promover modelo, alterar freeze, reescrever histórico ou produzir alegação preditiva.

O estado `CONSTRUCTION_PROVEN` somente pode ser emitido quando todas as etapas R0–R6 estiverem `PROVEN`, todos os bloqueios P0 estiverem resolvidos e a prova integral final estiver vinculada a um SHA canônico único.

Estados permitidos por etapa:

- `NOT_STARTED`
- `IN_PROGRESS`
- `BLOCKED`
- `PROVEN`
- `REGRESSED`

Estado inicial deste registro: **IN_PROGRESS**.

---

## 3. Estado atual verificado no momento do registro

### 3.1 Base canônica

- `main`: `9c731cfb6206a42b24198256bd16127cd6e39637`.
- O repositório opera sob arquitetura GitHub-only: código, estado canônico, Actions, artifacts e histórico Git formam a autoridade operacional.
- O projeto declara versão `1.1.10`.
- A arquitetura científica mantém M0/M1/M2, walk-forward, lockbox, auditoria e separação entre geração combinatória e evidência preditiva.

### 3.2 Entregas já incorporadas

O `main` já contém pipeline pós-concurso auditável que:

- recupera freezes por concurso-alvo;
- pode validar quantidade esperada;
- avalia sem mutar freezes;
- persiste episódio estruturado em `audit_events`;
- expõe episódios ao RAG somente para leitura;
- impõe `retrospective_only=true`, `rewrite_frozen_cards=false` e `direct_model_tuning_allowed=false`.

### 3.3 Pendências e riscos conhecidos

- PR #67 permanece aberto e contém a intenção de freezes cumulativos por concurso, mas nasceu sobre semântica anterior ao pipeline pós-concurso incorporado no PR #69. **Não deve ser mesclado sem reconciliação e nova prova.**
- Issue #68 ainda representa a missão pós-concurso completa; Challenger, validação científica e promoção/rejeição permanecem parte da cadeia a concluir.
- Issue #5 está semanticamente defasada se continuar afirmando ausência de rulesets nativos; o estado atual deve ser reconciliado e a issue atualizada/encerrada conforme evidência.
- A proteção de `main` observada exige os checks de CI Python 3.12 e 3.13, mas nem todos os gates que o próprio projeto considera críticos estão necessariamente configurados como checks obrigatórios de merge.
- Existem muitos workflows especializados de prova. Isso aumenta risco de fragmentação de governança, nomes instáveis de checks e divergência entre “workflow executou” e “gate bloqueia merge”.
- Não havia GitHub Release formal publicado no momento da auditoria-base, apesar da versão de software declarada.
- A autoridade GitHub-only reduz dependência de máquina local, mas concentra risco em conta/permissões, Actions, `operations/state` e disponibilidade do provedor.

### 3.4 Restrição factual do concurso 3781

No estado operacional auditado, existe apenas um `primary_card` recuperável de forma prospectiva para o concurso 3781, já avaliado com 8 acertos. Um segundo cartão alegado não pode ser reconstruído retroativamente sem evidência pré-sorteio. Portanto:

> **Sem freeze canônico prévio, o objeto não existe como previsão/cartão prospectivo auditável.**

Essa regra deixa de ser exceção do concurso 3781 e passa a ser invariante universal do projeto.

---

## 4. Arquitetura-alvo obrigatória

A construção deve permanecer como monólito modular auditável. Microserviços, Kubernetes, banco distribuído ou framework agentivo adicional não são requisitos e não devem ser introduzidos sem prova comparativa de necessidade e valor.

A arquitetura lógica é dividida em cinco planos:

### DATA PLANE

Responsável por ingestão, revisões, snapshots, proveniência e identidade temporal dos dados.

### SCIENCE PLANE

Responsável por M0/M1/M2, experimentos, walk-forward, lockbox, Challenger, Champion, métricas e decisão científica.

### OPERATION PLANE

Responsável por pedido do operador, geração, freeze, recuperação, auditoria pós-concurso, idempotência e `operations/state`.

### EVIDENCE PLANE

Responsável por hashes, manifests, artifacts, `audit_events`, RAG somente leitura, rastreabilidade e reconstrução.

### GOVERNANCE PLANE

Responsável pela cadeia de gates obrigatórios:

`CI -> Scientific Gate -> Operational Integrity Gate -> Security/Sanitization Gate -> Release Candidate Gate`

Workflows especializados podem continuar existindo internamente, mas a interface de merge deve convergir para gates estáveis e inequívocos.

---

## 5. Invariantes soberanos de segurança e integridade

1. Nenhum resultado posterior pode alterar conteúdo congelado antes do sorteio.
2. Nenhum cartão pode ser reconstruído retroativamente e tratado como prospectivo.
3. Todo freeze citável deve possuir identidade determinística e proveniência suficiente.
4. RAG é memória/auditoria; não é mecanismo de promoção de modelo.
5. Episódio retrospectivo não pode alterar Champion diretamente.
6. Toda hipótese de melhoria deve passar por Challenger e validação predeclarada.
7. Lockbox não pode ser usado para seleção ou tuning.
8. Estado operacional deve ser append-only ou versionado onde a mutabilidade destruiria auditabilidade.
9. Escritas em estado canônico devem ocorrer apenas por caminho explicitamente autorizado e auditável.
10. Falha de evidência deve resultar em `BLOCKED`/`NOT_PROVEN`, nunca em inferência otimista.
11. Backups externos são cópias de recuperação; não são segunda autoridade ativa.
12. Nenhuma IA pode declarar `CONSTRUCTION_PROVEN` com gates faltantes, resultados não verificáveis ou SHA divergente.

---

# 6. PLANO DE EXECUÇÃO REAL

## R0 — Reconciliar e selar o baseline

**Objetivo:** estabelecer um ponto de partida único e eliminar estado administrativo obsoleto.

**Sequência obrigatória:**

1. obter `HEAD` de `main`;
2. comparar com `9c731cfb6206a42b24198256bd16127cd6e39637`;
3. listar PRs e issues abertos relevantes;
4. verificar rulesets ativos de `main` e `operations/state`;
5. verificar checks realmente obrigatórios;
6. atualizar/encerrar Issue #5 conforme o estado real dos rulesets;
7. marcar PR #67 como dependente de reconciliação com a semântica pós-PR #69;
8. produzir registro do baseline reconciliado.

**Artefatos esperados:**

- SHA canônico do baseline;
- inventário de PRs/issues abertos;
- snapshot dos rulesets e required checks;
- decisão explícita sobre #5;
- decisão explícita sobre compatibilidade de #67.

**Prova mínima:** todas as afirmações acima verificáveis no GitHub; nenhuma pendência P0 conhecida classificada incorretamente.

**KPI:** zero issue crítica sabidamente obsoleta; zero PR operacional avançando sobre semântica incompatível conhecida.

**Estado inicial:** `IN_PROGRESS`.

---

## R1 — Freeze Integrity universal

**Objetivo:** tornar todo objeto prospectivo recuperável, imutável e auditável.

### R1.1 Freeze Registry

Implementar ou consolidar registro universal contendo, no mínimo:

- `freeze_id`;
- `target_contest`;
- `type`;
- `payload` ou referência imutável ao payload;
- `payload_hash`;
- `created_at`;
- `source_commit`;
- `workflow_run_id` quando aplicável;
- identidade de modelo/configuração;
- referência do estado Git que materializou o freeze;
- identidade/idempotency key da requisição do operador.

### R1.2 Semântica cumulativa

Reconciliar a intenção válida do PR #67 com o pipeline pós-concurso atual. Requisições explícitas sucessivas para o mesmo concurso devem poder acrescentar cartões sem sobrescrever freezes anteriores, sem duplicação silenciosa e sem destruir o `primary_card` já congelado.

### R1.3 Testes obrigatórios

- 1 + 1 cartões no mesmo concurso => 2 freezes distintos;
- sequência 1 + 1 + 10 + 1 + 4 => 17 cartões distintos quando houver espaço combinatório;
- replay da mesma requisição idempotente => nenhuma duplicação indevida;
- colisão de payload => comportamento determinístico;
- restart/reexecução => mesma recuperação;
- auditoria pós-concurso => conteúdo antes/depois byte/hash-idêntico;
- quantidade esperada ausente => falha explícita;
- tentativa de reconstrução retroativa sem freeze => rejeição explícita.

**Artefatos esperados:** código, testes, ledger/registry versionado, workflow autorizado, hashes e evidência de execução.

**Gate de saída:** 100% dos cartões operacionais congelados recuperáveis deterministicamente; zero mutação pós-freeze; zero reconstrução prospectiva silenciosa.

**Estado inicial:** `NOT_STARTED`.

---

## R2 — Pós-concurso + aprendizagem controlada + Challenger

**Objetivo:** completar a cadeia de aprendizagem sem vazamento temporal e sem autoajuste indevido.

**Fluxo obrigatório:**

`RESULTADO OFICIAL -> RECONCILIAÇÃO -> FREEZES -> AVALIAÇÃO -> EPISÓDIO -> HIPÓTESE -> CHALLENGER -> BACKTEST/WALK-FORWARD -> CHAMPION + M0 -> DECISÃO DE PROMOÇÃO/REJEIÇÃO`

### R2.1 Avaliação

- associar resultado oficial a `contest_id + revision`;
- localizar todos os freezes esperados;
- calcular acertos e métricas sem mutação;
- persistir avaliação idempotente.

### R2.2 Episódio de aprendizagem

Registrar fatos, erros observados, contexto e referências de evidência. O episódio deve permanecer retrospectivo e somente leitura para fins de recuperação contextual.

### R2.3 Hipótese

Toda melhoria proposta deve ser formalizada antes do teste, incluindo:

- hipótese;
- mecanismo esperado;
- métrica primária;
- baseline;
- janela de treino/validação;
- regra de parada;
- regra de promoção/rejeição;
- dados proibidos para seleção.

### R2.4 Challenger

Challenger deve executar isoladamente do Champion. Não pode alterar Champion, configuração canônica ou freezes antes da decisão de promoção.

### R2.5 Validação

Executar backtest/walk-forward temporalmente válido, comparação com Champion e M0, controles contra leakage e, quando aplicável, intervalos de incerteza já definidos pelo protocolo científico.

**Gate de saída:** hipótese e Challenger têm evidência reproduzível; nenhuma mutação indevida; decisão de promoção/rejeição derivada de regra predeclarada.

**KPI:** 100% das promoções rastreáveis a hipótese + experimento + gate; zero promoção direta via RAG/episódio.

**Estado inicial:** `NOT_STARTED`.

---

## R3 — Consolidar governança e gates de merge

**Objetivo:** transformar a política de prova em proteção efetiva do repositório.

**Interface obrigatória desejada:**

1. `CI`;
2. `Scientific Gate`;
3. `Operational Integrity Gate`;
4. `Security/Sanitization Gate`;
5. `Release Candidate Gate`.

**Execução:**

- mapear workflows atuais para esses cinco gates;
- evitar criar workflow novo quando um composto existente puder agregar subprovas;
- garantir nomes estáveis dos required checks;
- configurar ruleset para exigir os gates críticos adequados;
- testar PR controlado com falha científica;
- testar PR controlado com falha operacional;
- comprovar que merge é bloqueado;
- testar PR válido e comprovar caminho de merge permitido.

**Artefatos esperados:** workflows compostos, ruleset atualizado, runs de prova positiva/negativa e registro de governança.

**Gate de saída:** mudança que quebra ciência ou integridade operacional não consegue atingir `main` pelo fluxo normal protegido.

**Estado inicial:** `NOT_STARTED`.

---

## R4 — Engenharia formal de release

**Objetivo:** fazer cada release identificar inequivocamente código, dependências, estado e provas.

**Conteúdo mínimo do release candidate:**

- versão SemVer;
- SHA canônico;
- `requirements.lock.txt`/dependências efetivas;
- manifest de arquivos/artefatos relevantes;
- hashes SHA-256;
- resultado dos gates obrigatórios;
- referência ao protocolo científico;
- referência ao estado operacional compatível;
- instrução de reconstrução/recuperação;
- limitações e estado da evidência preditiva.

**Regra:** tag/alias isolado não substitui release formal. Release formal não pode apontar para SHA diferente daquele que passou pelos gates declarados.

**Gate de saída:** GitHub Release formal verificável e ligado ao mesmo SHA aprovado pelos gates.

**Estado inicial:** `NOT_STARTED`.

---

## R5 — Disaster Recovery do modelo GitHub-only

**Objetivo:** provar recuperação sem criar split-brain de autoridade.

**Cenários mínimos:**

- checkout limpo a partir do repositório;
- reinstalação usando dependências travadas;
- reconstrução do estado derivável;
- recuperação de estado operacional versionado;
- validação de hashes/manifests;
- reexecução de testes/gates essenciais;
- simulação de indisponibilidade/perda do ambiente de execução, sem promover backup externo a autoridade concorrente.

**Métricas obrigatórias:**

- RPO observado;
- RTO observado;
- itens não recuperáveis automaticamente;
- dependências externas necessárias;
- passos manuais inevitáveis.

**Gate de saída:** recuperação reproduzível a partir das fontes canônicas declaradas e evidência de que o sistema não depende de máquina residente específica.

**Estado inicial:** `NOT_STARTED`.

---

## R6 — Prova integral de construção

**Objetivo:** executar uma cadeia única, limpa e auditável que atravesse todos os planos arquiteturais.

**Cenário integral obrigatório:**

1. checkout limpo do SHA candidato;
2. instalação locked;
3. CI;
4. ingestão/validação de histórico real;
5. gates científicos;
6. geração operacional;
7. freeze com identidade/hash/proveniência;
8. recuperação do freeze;
9. avaliação pós-concurso por revisão oficial;
10. prova de imutabilidade;
11. persistência do episódio;
12. recuperação pelo RAG read-only;
13. criação de hipótese Challenger;
14. validação temporal isolada;
15. decisão de promoção/rejeição sem alterar evidência histórica;
16. restart/replay e prova de idempotência;
17. recuperação/reconstrução;
18. sanitização/segurança;
19. release candidate;
20. manifest final de evidências.

**Manifest final obrigatório:**

- `construction_id`;
- versão;
- SHA;
- data/hora UTC;
- lista de gates e run IDs;
- hashes dos artefatos;
- inventário de testes;
- resultado de cada etapa R0–R6;
- lista de exceções conhecidas;
- lista de claims permitidos;
- lista de claims proibidos;
- assinatura/hash do próprio manifest.

**Critério terminal:** todas as etapas R0–R6 em `PROVEN`, nenhuma exceção P0 aberta, todos os artefatos referenciados existentes e verificáveis no mesmo baseline.

Somente então emitir:

`CONSTRUCTION_PROVEN = TRUE`

Até lá:

`CONSTRUCTION_PROVEN = FALSE`

---

## 7. Matriz de dependências

| Etapa | Depende de | Pode avançar em paralelo? | Bloqueia |
|---|---|---|---|
| R0 | estado GitHub atual | não | R1–R6 |
| R1 | R0 | parcialmente com desenho de R2 | R2, R6 |
| R2 | R1 | testes internos podem antecipar | R6 |
| R3 | R0 e conhecimento de R1/R2 | sim, após interfaces estabilizadas | R4, R6 |
| R4 | R3 e candidato estável | não | R6 |
| R5 | R1/R3 suficientemente estáveis | sim | R6 |
| R6 | R0–R5 | não | CONSTRUCTION_PROVEN |

---

## 8. Bloqueios formais

### P0 — Bloqueiam CONSTRUCTION_PROVEN

- freeze prospectivo não recuperável;
- mutação de freeze após resultado;
- reconstrução retroativa tratada como prospectiva;
- Challenger capaz de alterar Champion antes do gate;
- leakage de lockbox;
- required gates críticos não efetivamente bloqueando merge;
- release apontando para SHA diferente do aprovado;
- recuperação não reproduzível;
- evidência final sem hash/proveniência;
- divergência entre estado documentado e estado canônico não reconciliada.

### P1 — Não bloqueiam construção se explicitamente registradas

- ausência de vantagem preditiva comprovada;
- resultado estatístico inconclusivo;
- hipótese Challenger rejeitada;
- limitação de um experimento que não comprometa integridade do pipeline.

A construção pode ser provada mesmo quando a ciência conclui `NOT_ESTABLISHED`, desde que essa conclusão seja produzida corretamente e sem manipulação.

---

## 9. Comandos e verificações esperados

Os comandos abaixo são referências operacionais. Uma IA pode usar API GitHub equivalente, desde que produza a mesma evidência.

```bash
git rev-parse HEAD
git status --short
python -m pip install -c requirements.lock.txt -e '.[dev]'
pytest -q
python -m sare_lotofacil doctor
python scripts/verify_github_governance.py
python scripts/validate_agent_ecosystem.py
```

Também devem ser verificadas via GitHub/API:

- PRs/issues abertos;
- rulesets ativos;
- required status checks;
- workflow runs do SHA candidato;
- artifacts e hashes;
- tags/releases;
- estado de `operations/state`;
- commits que materializam cada transição.

Nenhum comando deve ser considerado suficiente isoladamente para provar uma etapa.

---

## 10. Padrão de evidência por etapa

Toda etapa declarada `PROVEN` deve registrar:

```text
stage_id:
status: PROVEN
canonical_sha:
started_at:
completed_at:
requirements:
implemented_changes:
tests:
workflow_runs:
artifacts:
hashes:
negative_tests:
known_limitations:
open_blockers: []
reviewed_against_invariants: true
```

Se `open_blockers` não estiver vazio, o estado não pode ser `PROVEN`.

---

## 11. Checklist operacional das primeiras 24 horas

- [ ] Selar o baseline atual de `main` e registrar divergência em relação ao SHA-base deste documento.
- [ ] Reconciliar Issue #5 com os rulesets realmente ativos.
- [ ] Impedir merge de PR #67 sem reconciliação com o pipeline pós-concurso incorporado no PR #69.
- [ ] Formalizar a invariante universal: sem freeze canônico pré-sorteio, não existe objeto prospectivo auditável.
- [ ] Mapear quais workflows apenas executam e quais checks realmente bloqueiam merge.
- [ ] Definir a implementação dos cinco gates compostos estáveis.
- [ ] Especificar Freeze Registry e testes de idempotência/cumulatividade.
- [ ] Só depois avançar a cadeia Challenger/aprendizagem.

---

## 12. Protocolo para outra IA assumir a execução

Ao receber este documento, a IA deve considerar que nenhuma ação posterior ao `estado-base de criação` está garantida. Deve verificar o GitHub antes de agir.

Prompt operacional mínimo de retomada:

```text
MISSÃO: continuar CONSTRUCTION_PROVEN do SARE Lotofácil.

1. Leia docs/CONSTRUCTION_PROVEN.md integralmente.
2. Verifique o estado GitHub atual contra o baseline registrado.
3. Não confie em status histórico sem reverificação.
4. Encontre a primeira etapa R0-R6 que não esteja comprovada no estado canônico.
5. Execute-a ponta a ponta em branch/PR protegido, incluindo testes e evidências.
6. Não pule bloqueios P0 e não reconstrua evidência inexistente.
7. Preserve freezes, lockbox, Champion e proveniência conforme invariantes.
8. Atualize o registro de execução com SHA, runs, artifacts e hashes.
9. Só declare PROVEN quando a prova for verificável.
10. Só declare CONSTRUCTION_PROVEN=TRUE após R0-R6 PROVEN no mesmo baseline/release.
```

---

## 13. Regra de mudança deste plano

Alterações neste documento exigem PR normal e devem explicar:

- qual requisito mudou;
- por que mudou;
- impacto em etapas anteriores;
- necessidade ou não de regressão de `PROVEN` para `REGRESSED`;
- evidência que sustenta a mudança.

Nenhuma alteração pode apagar silenciosamente uma falha, relaxar critério de prova para acomodar resultado ou reclassificar evidência retrospectiva como prospectiva.

---

## 14. Estado canônico atual da missão

```text
CONSTRUCTION_PROVEN = TRUE
R0 = PROVEN
R1 = PROVEN
R2 = PROVEN
R3 = PROVEN
R4 = PROVEN
R5 = PROVEN
R6 = PROVEN
NEXT_REQUIRED_STAGE = NONE
CONSTRUCTION_ID = SARE-LOTOFACIL-CONSTRUCTION-PROVEN-1.1.10
CONSTRUCTION_SHA = 77d1b6d92edee8c8ed7a0b146441ab6c0ec47e7c
CONSTRUCTION_TAG = construction-proven/v1.1.10
CONSTRUCTION_MANIFEST_HASH = 30deee4a3b38dc12e5c71a601d6eb0663375feeddce0df9e5e3f5ad910eafbd8
RELEASE = v1.1.10
RELEASE_SHA = 07fdcf624c275f554caeac31e70dc1a34b8e99d9
BASELINE_ORIGINAL = main@9c731cfb6206a42b24198256bd16127cd6e39637
```

Este bloco reflete as etapas comprovadas por registros canônicos em `docs/evidence/`. A release formal R4 permanece imutavelmente vinculada ao SHA acima; commits documentais posteriores não alteram o alvo da release.
