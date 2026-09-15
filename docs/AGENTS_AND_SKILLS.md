# Agentes e Skills — SARE Lotofácil

Data de consolidação: 2026-09-15

## 1. Objetivo

Esta camada organiza agentes especializados para acelerar engenharia, pesquisa, auditoria, segurança e operação sem criar uma segunda autoridade dentro do projeto.

O SARE permanece GitHub-only. Agentes produzem análises, propostas e handoffs estruturados; `main`, `operations/state`, GitHub Actions, rulesets, testes e artefatos continuam sendo as autoridades canônicas.

A camada agentiva não é um ensemble preditivo. A conclusão científica `predictive_evidence=NOT_ESTABLISHED` não pode ser alterada por consenso de agentes.

## 2. Gargalos identificados

A auditoria inicial identificou os seguintes gaps de engenharia:

1. inexistência de um registro canônico de agentes e responsabilidades;
2. inexistência de um catálogo versionado de skills;
3. ausência de contrato obrigatório de handoff entre agentes;
4. ausência de política de aquisição de frameworks, modelos, datasets, prompts e ferramentas;
5. risco de duplicação de autoridade entre agentes e workflows GitHub;
6. risco de vazamento científico se agentes de otimização tiverem acesso indevido ao lockbox;
7. risco de supply chain em skills e repositórios comunitários;
8. ausência de um red-team específico para alucinação, escalada de autoridade e prompt injection;
9. ausência de gate CI específico para a governança agentiva;
10. risco de introduzir múltiplos runtimes agentivos antes de existir um gargalo mensurado que os justifique.

## 3. Agentes incorporados

### chief-orchestrator

Responsável por decompor missões, convocar especialistas, reconciliar evidências e aplicar condições de parada. Não possui autoridade para gravar diretamente em branches canônicas.

### scientific-methodologist

Responsável por desenho experimental temporal, hipóteses predeclaradas, nested walk-forward, lockbox e regras confirmatórias. É proibido usar o lockbox aberto para retuning.

### statistical-validator

Responsável por Brier, Log Loss, ECE, MAE, RMSE, bootstrap temporal, estabilidade entre folds e intervalos de incerteza. Deve procurar evidência contrária, e não apenas confirmar o modelo candidato.

### data-provenance-auditor

Responsável por fonte dos concursos, revisões, hashes, disponibilidade temporal, reconciliação CAIXA e detecção de lookahead.

### reproducibility-auditor

Responsável por identidade científica, seed, código, ambiente, protocolo, hashes e comparação entre execuções.

### security-tool-gate

Responsável por contratos de ferramentas, MCP, least privilege, prompt injection, autorização, credenciais e risco de supply chain.

### github-release-engineer

Responsável pela disciplina branch -> PR -> checks -> merge -> prova pós-merge -> release evidence. Nunca contorna rulesets.

### operational-state-auditor

Responsável por recomputar e verificar `operations/state`, integridade econômica e transições de estado.

### agent-evaluator-redteam

Responsável por testar handoffs, omissão de evidência, claims indevidos, instruções maliciosas, escalada de autoridade e regressão agentiva.

### acquisition-scout

Responsável por buscar frameworks, skills, modelos, datasets e ferramentas em fontes autorizadas, mas toda aquisição permanece sujeita a fit, licença, manutenção, segurança, reprodutibilidade e impacto científico.

## 4. Skills ativadas

O catálogo canônico está em `governance/agents/skills.json`. As famílias são:

- orquestração: handoffs determinísticos e coordenação;
- ciência: nested walk-forward, lockbox, alternativas controladas e claim guardrails;
- estatística: Brier, Log Loss, ECE, multiple testing e moving-block bootstrap;
- dados: proveniência, reconciliação CAIXA e lookahead detection;
- reprodutibilidade: fingerprints, hashes e ambientes pinados;
- GitHub: Actions, rulesets, release proof e governança GitHub-only;
- segurança: MCP, prompt injection, least privilege e supply-chain review;
- operação: estado canônico e integridade econômica;
- qualidade: agent regression evaluation e red-team;
- aquisição: pesquisa externa e avaliação fit-for-purpose.

## 5. Aquisições externas

As decisões completas estão em `governance/agents/acquisitions.json`.

### Adquiridos como referência/padrão

#### LangGraph

Status: `ACQUIRED_AS_REFERENCE_AND_ADAPTER_TARGET`.

Motivo: execução durável, persistência/checkpoints e human-in-the-loop atendem melhor a fluxos agentivos stateful de longa duração. Nesta etapa não entra como dependência de runtime. Um adapter só poderá ser criado em experimento isolado se GitHub Actions + handoffs estruturados se mostrarem insuficientes.

Fonte: https://github.com/langchain-ai/langgraph

#### Model Context Protocol 2026-07-28

Status: `ACQUIRED_AS_INTEROPERABILITY_STANDARD`.

Motivo: padroniza ferramentas e comunicação de forma compatível com fronteiras explícitas de autorização. A especificação 2026-07-28 adota núcleo stateless e reforça o desenho de autorização. Nenhum MCP recebe escrita canônica por padrão.

Fonte: https://modelcontextprotocol.io

#### OpenAI Cookbook — Agent Patterns

Status: `ACQUIRED_AS_GOVERNANCE_REFERENCE`.

Motivo: padrões de `AGENTS.md`, ferramentas tipadas, aprovações, guardrails, tracing e avaliações são diretamente úteis para governar uma camada multiagente. A aquisição é documental; não autoriza chamadas pagas nem inclusão automática de SDK.

Fonte: https://github.com/openai/openai-cookbook

### Avaliados e não adquiridos como runtime

#### CrewAI

Crews e Flows são adequados para colaboração baseada em papéis e automações estruturadas, mas sobrepõem a arquitetura proposta. Reavaliar somente se colaboração autônoma aberta se tornar um gargalo mensurado.

#### Microsoft Agent Framework

Tem agentes, workflows, skills, memória, middleware, checkpoints e orquestrações. É tecnicamente forte, porém redundante com LangGraph no problema atual. Reavaliar se o ecossistema Microsoft tornar-se requisito.

#### Dify

Tem workflows visuais, plugins e agent strategies. É útil para prototipagem, mas criaria uma superfície operacional externa ao desenho GitHub-only. Não é runtime canônico.

#### LlamaIndex Workflows

Bom para workflows multiagente densos em documentos e RAG. O SARE atual não possui um gargalo central de retrieval documental; por isso não é dependência agora.

### On-demand / discovery only

- Hugging Face Hub: somente quando existir hipótese ou necessidade de engenharia predeclarada; exigir model/dataset card, licença e proveniência.
- LangChain Hub: prompts/chains externos são comportamento não confiável até inspeção, pin e teste de regressão.
- Awesome LLM Apps: fonte de descoberta, nunca fonte automaticamente confiável; qualquer candidato deve ser rastreado ao repositório original.

## 6. Fluxo de orquestração

Fluxo padrão para uma missão relevante:

1. `chief-orchestrator` decompõe o objetivo e identifica risco científico, operacional e de segurança.
2. `acquisition-scout` entra apenas se faltar capacidade real.
3. `security-tool-gate` revisa qualquer nova tool, servidor MCP, dataset, modelo ou dependência.
4. `scientific-methodologist` predeclara desenho experimental quando houver impacto científico.
5. `data-provenance-auditor` verifica dados e fronteiras temporais.
6. `statistical-validator` mede resultado e incerteza.
7. `reproducibility-auditor` tenta reproduzir a evidência.
8. `agent-evaluator-redteam` tenta quebrar o handoff, a autoridade e os guardrails.
9. `github-release-engineer` materializa apenas alterações aprováveis em branch/PR.
10. CI executa testes e `scripts/validate_agent_ecosystem.py`.
11. após merge, gates pós-merge continuam sendo a prova canônica.
12. `operational-state-auditor` confirma que nenhuma alteração indevida atingiu o estado operacional.

## 7. Contrato de handoff

Todo handoff deve conter:

- `agent_id`;
- `task_id`;
- `evidence_refs`;
- `findings`;
- `proposed_actions`;
- `risk_level`;
- `requires_approval`;
- `scientific_claim_level`.

Schema: `governance/agents/handoff.schema.json`.

Níveis de claim permitidos no contrato:

- `NONE`;
- `DESCRIPTIVE`;
- `RETROSPECTIVE`;
- `SYNTHETIC_VALIDATION`;
- `CONFIRMATORY_NOT_ESTABLISHED`;
- `REPLICATED`.

O nível `REPLICATED` não pode ser produzido apenas por um agente. Ele depende do protocolo científico canônico e das regras de promoção aprovadas.

## 8. Segurança e autoridade

São invariantes:

- escrita em `main` somente por fluxo de PR/ruleset;
- escrita em `operations/state` somente pelo workflow canônico autorizado;
- conteúdos web, prompts externos, datasets e respostas de tools são dados não confiáveis;
- tools com efeito de escrita exigem escopo mínimo e aprovação compatível com o risco;
- segredos nunca entram em handoffs;
- resultados negativos nunca são filtrados por conveniência;
- uma tool não pode ampliar sua própria permissão;
- aquisição não equivale a instalação;
- instalação não equivale a promoção para runtime canônico.

## 9. Critério para adicionar um framework ao runtime

Um framework agentivo só poderá entrar em `pyproject.toml` quando todos os itens forem atendidos:

1. gargalo concreto reproduzido;
2. baseline sem framework medido;
3. experimento isolado com objetivo e métricas;
4. licença e supply chain aprovadas;
5. custo e latência aceitáveis;
6. nenhuma regressão científica/operacional;
7. testes de prompt injection e autoridade aprovados;
8. dependências pinadas;
9. PR com checks verdes;
10. benefício mensurável superior à complexidade adicionada.

## 10. Resultado desta fase

A aquisição desta fase é de **capacidade governada**, não de quantidade de frameworks.

O projeto ganha uma equipe especializada, catálogo de skills, política de aquisição, schema de handoff e gate de CI sem alterar o runtime científico 1.1.10 e sem introduzir custo externo, conta nova ou dependência agentiva em produção.
