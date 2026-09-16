# Integração Executável de Agentes e Skills — SARE Lotofácil

## Objetivo

A camada agentiva do SARE deixa de ser apenas um catálogo de papéis e passa a possuir uma ligação executável e auditável entre **agente → skills → missão → tool → handoff**.

A integração permanece `GITHUB_ONLY`, read-only no baseline autônomo e sem runtime agentivo externo canônico.

## Contratos versionados

A integração é formada por quatro registros em `governance/agents/`:

- `agents.json`: agentes, papéis, skills possuídas, ações permitidas e proibições;
- `skills.json`: catálogo canônico de skills;
- `capability_missions.json`: missões executáveis e `required_skills` obrigatórias;
- `tool_bindings.json`: tools read-only autorizadas para as missões.

`src/sare_lotofacil/agents/integration.py` carrega os quatro registros e rejeita qualquer estado em que:

- uma skill de agente não exista no catálogo;
- uma skill do catálogo não esteja atribuída a pelo menos um agente;
- uma missão não declare `required_skills`;
- uma missão exija skill que o agente designado não possua;
- uma missão referencie agente ou tool inexistente;
- algum agente não tenha ao menos uma missão executável;
- a autoridade deixe de ser `GITHUB_ONLY`;
- o baseline passe a permitir escrita direta em `main` ou `operations/state`;
- o baseline introduza runtime framework externo como autoridade canônica.

## Cobertura atual

O baseline integrado contém:

- 12 agentes;
- 30 skills;
- 12 missões executáveis;
- 10 tool bindings read-only.

Todos os 12 agentes possuem missão executável. Todas as 30 skills estão atribuídas a pelo menos um agente.

Os especialistas RAG possuem missões explícitas:

- `CAP-011-rag-retrieval-integration` → `rag-retrieval-engineer`;
- `CAP-012-rag-redteam-integration` → `rag-evaluation-redteam`.

O `chief-orchestrator` possui a missão `CAP-009-orchestrator-skill-routing`, que prova o roteamento entre os registros. O `acquisition-scout` possui `CAP-010-acquisition-governance-integration`, mantendo aquisição ligada aos gates de segurança e governança.

## CLI

O executável `sare-agents` fornece inspeção determinística do estado integrado:

```bash
sare-agents --root . status
sare-agents --root . plan
sare-agents --root . resolve CAP-011-rag-retrieval-integration
sare-agents --root . recommend --skill rag_grounding_evaluation --skill prompt_injection_defense
```

`status` informa contagens, cobertura e `registry_fingerprint_sha256`.

`plan` resolve todas as missões para seus agentes, skills e tools.

`resolve` materializa uma missão específica com o agente designado, todas as skills do agente, skills exigidas e tool autorizada.

`recommend` retorna somente agentes que possuem **todas** as skills solicitadas; não faz matching parcial como autorização de execução.

O subcomando `handoff` gera um handoff usando o contrato da missão e os campos canônicos definidos em `handoff.schema.json`.

## Integração com Agent Capability Proof

`scripts/run_agent_capability_proof.py` agora valida explicitamente as skills. Uma missão não pode ser executada pelo proof se o agente designado não possuir todas as `required_skills`.

O fingerprint de definição inclui agentes, skills, missões e tools. Assim, mudança em qualquer uma dessas quatro camadas altera a identidade da prova.

## Prova GitHub Actions

O workflow `Agent Skill Integration Proof` executa:

1. validação do ecossistema agentivo;
2. testes específicos de integração;
3. `sare-agents status`;
4. plano integrado completo;
5. resolução da missão RAG de retrieval;
6. recomendação por conjunto de skills;
7. validação do plano do Agent Capability Proof;
8. upload de artefatos JSON.

A integração só deve ser classificada como operacional para um commit quando o workflow desse commit terminar com `SUCCESS`.

## Fronteiras

A integração não transforma os agentes em uma nova autoridade. Ela não permite merge automático, escrita direta em branches canônicas, promoção científica, retuning de lockbox ou aquisição automática de dependência externa.

Frameworks como LangGraph, LlamaIndex Workflows, CrewAI ou Microsoft Agent Framework permanecem referências/targets experimentais conforme a governança existente. Entrar no runtime exige prova separada de benefício mensurável.
