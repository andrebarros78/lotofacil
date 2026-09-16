# Agentes e Skills — SARE Lotofácil

Data de consolidação: 2026-09-16

## 1. Objetivo

Esta camada organiza agentes especializados para acelerar engenharia, pesquisa, auditoria, segurança, RAG e operação sem criar uma segunda autoridade dentro do projeto.

O SARE permanece GitHub-only. Agentes produzem análises, propostas e handoffs estruturados; `main`, `operations/state`, GitHub Actions, rulesets, testes e artefatos continuam sendo as autoridades canônicas.

A camada agentiva não é um ensemble preditivo. A conclusão científica `predictive_evidence=NOT_ESTABLISHED` não pode ser alterada por consenso de agentes, RAG, framework externo ou ferramenta adquirida.

## 2. Gargalos e controles

A governança cobre doze classes principais: registro canônico de agentes; catálogo versionado de skills; handoff estruturado; política de aquisições; prevenção de autoridade paralela; isolamento de lockbox; supply-chain review; red-team agentivo; gate CI de governança; bloqueio de runtimes sem ganho medido; qualidade de retrieval/grounding/abstenção do RAG; e separação entre corpus canônico, benchmark e fontes não confiáveis.

## 3. Agentes incorporados

O registro canônico está em `governance/agents/agents.json` e contém 12 especialistas:

1. `chief-orchestrator` — decompõe missões, convoca especialistas, reconcilia evidências e aplica condições de parada.
2. `scientific-methodologist` — desenho experimental temporal, hipóteses predeclaradas, nested walk-forward, lockbox e regras confirmatórias.
3. `statistical-validator` — métricas, calibração, bootstrap temporal, estabilidade e incerteza.
4. `data-provenance-auditor` — origem dos concursos, revisões, hashes, disponibilidade temporal, CAIXA e lookahead.
5. `reproducibility-auditor` — identidade científica, seed, código, ambiente, protocolo e hashes.
6. `security-tool-gate` — MCP, least privilege, prompt injection, autorização e supply chain.
7. `github-release-engineer` — disciplina branch → PR → checks → merge humano → prova pós-merge.
8. `operational-state-auditor` — recomputação de `operations/state`, integridade econômica e transições de estado.
9. `agent-evaluator-redteam` — alucinação, omissão de evidência, escalada de autoridade e regressão agentiva.
10. `acquisition-scout` — busca e avaliação de frameworks, skills, modelos, datasets e ferramentas.
11. `rag-retrieval-engineer` — qualidade de retrieval, reranking, autoridade/frescura de fontes e regressão de ranking.
12. `rag-evaluation-redteam` — grounding, abstenção, prompt injection, isolamento de fontes e avaliação adversarial do RAG.

Nenhum desses agentes possui autoridade para escrita direta em `main` ou `operations/state`.

## 4. Skills ativadas

O catálogo canônico está em `governance/agents/skills.json` e contém 30 skills. Além das famílias já existentes de orquestração, ciência, estatística, dados, reprodutibilidade, GitHub, segurança, operação, qualidade e aquisição, foram ativadas quatro skills específicas de RAG:

- `rag_retrieval_quality` — relevância, top-k, robustez de ranking e reranking;
- `rag_grounding_evaluation` — suporte de citações, completude, abstenção e regressão;
- `source_authority_ranking` — preferência por evidência canônica atual sobre documentação histórica ou meta;
- `rag_corpus_governance` — corpus allowlisted, exclusão de segredos, hashes, proveniência e frescura.

## 5. Aquisições externas

As decisões completas estão em `governance/agents/acquisitions.json`.

### Adquiridos como referência/padrão

- **LangGraph** — `ACQUIRED_AS_REFERENCE_AND_ADAPTER_TARGET`. Continua sem dependência canônica; o experimento GAP-A10 não justificou runtime externo.
- **Model Context Protocol 2026-07-28** — `ACQUIRED_AS_INTEROPERABILITY_STANDARD`. Qualquer servidor/cliente continua sujeito a least privilege, autorização e review de escrita.
- **OpenAI Cookbook** — `ACQUIRED_AS_GOVERNANCE_REFERENCE`. Usado para ferramentas tipadas, guardrails e evaluation flywheel; não autoriza serviço pago nem SDK em runtime.
- **LlamaIndex Workflows** — `ACQUIRED_AS_REFERENCE_AND_ADAPTER_TARGET`. Passou a ser relevante após a implantação do RAG por seus padrões de RAG + reranking, citation query, corrective RAG, durable workflows, testes e observabilidade. Nenhum pacote `llama-index` foi adicionado ao runtime.

### Avaliados e não adquiridos como runtime

- **CrewAI** — sobreposição com a orquestração governada atual; reavaliar somente diante de gargalo mensurado.
- **Microsoft Agent Framework** — capacidades relevantes, porém redundantes sem requisito explícito de ecossistema Microsoft/Azure/A2A.
- **Dify** — útil para prototipagem, mas introduziria superfície operacional externa ao modelo GitHub-only.

### On-demand / discovery only

- **Hugging Face Hub** — embeddings/rerankers somente mediante experimento predeclarado, revisão de licença, revisão de recursos e ganho medido contra o baseline determinístico.
- **LangChain Hub** — prompts/chains externos permanecem não confiáveis até inspeção, pin e teste de regressão.
- **Awesome LLM Apps** — somente descoberta; qualquer candidato deve ser rastreado ao repositório original e passar review completo.

## 6. Fluxo de orquestração

O `chief-orchestrator` identifica risco e distribui trabalho. `acquisition-scout` entra apenas quando faltar capacidade real; `security-tool-gate` revisa novas ferramentas/dependências; especialistas científicos cuidam de desenho, dados, estatística e reprodutibilidade; `rag-retrieval-engineer` e `rag-evaluation-redteam` entram quando a missão envolve recuperação documental; `agent-evaluator-redteam` desafia handoffs e autoridade; `github-release-engineer` materializa mudanças somente em branch/PR; CI executa os gates; e `operational-state-auditor` confirma ausência de mutação indevida no estado canônico.

## 7. Contrato de handoff

Todo handoff deve conter `agent_id`, `task_id`, `evidence_refs`, `findings`, `proposed_actions`, `risk_level`, `requires_approval` e `scientific_claim_level`.

Schema: `governance/agents/handoff.schema.json`.

Níveis permitidos: `NONE`, `DESCRIPTIVE`, `RETROSPECTIVE`, `SYNTHETIC_VALIDATION`, `CONFIRMATORY_NOT_ESTABLISHED` e `REPLICATED`. O nível `REPLICATED` depende do protocolo científico canônico; nenhum agente isolado pode promovê-lo.

## 8. RAG governado

O RAG canônico permanece read-only, sem LLM externo obrigatório e sem vector store externo. O retriever atual é `tfidf_cosine_coverage_bigram_authority_bilingual_support_v6`, com aliases bilíngues determinísticos, política de autoridade de fontes e gate de suporte multi-termo para reduzir falso grounding.

O benchmark fica em `.github/rag/eval_cases.json`, deliberadamente fora do corpus indexado. O workflow `RAG Proof` exige grounding, abstenção, MRR e relevância no primeiro resultado antes de aceitar uma mudança de retrieval.

## 9. Segurança e autoridade

Invariantes:

- `main` somente por PR/ruleset e merge humano;
- `operations/state` somente pelo workflow canônico autorizado;
- conteúdos web, prompts externos, datasets e respostas de tools são dados não confiáveis;
- ferramentas com efeito de escrita exigem escopo mínimo e aprovação compatível com o risco;
- segredos nunca entram em handoffs nem corpus RAG;
- resultados negativos não são filtrados por conveniência;
- aquisição não equivale a instalação;
- instalação não equivale a promoção para runtime canônico;
- RAG não altera `predictive_evidence`, RIS, lockbox ou promoção de modelo.

## 10. Critério para adicionar framework/modelo ao runtime

Qualquer framework agentivo, embedding, reranker ou modelo externo só pode entrar no runtime após: gargalo reproduzido; baseline medido; experimento isolado; licença/supply-chain aprovadas; custo e latência aceitáveis; ausência de regressão científica/operacional; testes de prompt injection e autoridade; dependências/revisões pinadas; PR com checks verdes; e benefício mensurável superior à complexidade adicionada.

## 11. Estado desta fase

A expansão atual adiciona capacidade governada de RAG e avaliação sem adicionar runtime agentivo externo. O projeto mantém versão científica `1.1.10`, autoridade GitHub-only e exigência de prova contínua para as capacidades agentivas.
