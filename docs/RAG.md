# RAG auditável do SARE Lotofácil

## Objetivo

O RAG do SARE fornece recuperação e resposta fundamentada sobre o próprio repositório canônico sem introduzir autoridade científica, operacional ou preditiva nova.

A implementação é deliberadamente **read-only, determinística e reproduzível**. Ela reconstrói o índice a partir do checkout Git versionado e produz um `source_digest` SHA-256 para vincular cada consulta ao conjunto exato de fontes usado.

## Escopo de fontes

Por padrão são indexados somente caminhos explícitos do checkout:

- `README.md`;
- `AGENTS.md`;
- `docs/`;
- `governance/`;
- `src/sare_lotofacil/`.

São aceitos apenas arquivos textuais com extensões `.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.toml` e `.py`. Symlinks, diretórios de ambiente/cache e arquivos acima do limite interno são excluídos. Arquivos fora dos caminhos declarados, como `.env`, não entram no índice.

## Pipeline

1. descoberta determinística das fontes permitidas;
2. leitura UTF-8 e hash por fonte;
3. chunking por linhas, preservando `path`, `line_start` e `line_end`;
4. tokenização normalizada com remoção limitada de termos interrogativos/fillers;
5. índice TF-IDF em memória;
6. recuperação por `tfidf_cosine_coverage_bigram_authority_v3`, combinando similaridade, cobertura lexical, adjacência de termos e prioridade de autoridade/frescura documental;
7. deduplicação de evidência repetida;
8. geração extrativa determinística a partir dos chunks recuperados;
9. emissão de citações com caminho, faixa de linhas, `chunk_id` e score;
10. abstenção quando a consulta não possui suporte no índice.

A prioridade de autoridade impede que exemplos de uso do próprio RAG ou provas históricas obsoletas precedam documentação canônica mais atual quando a consulta pergunta pelo estado vigente.

## Invariantes

- `read_only=true`;
- nenhum write em `main` ou `operations/state`;
- nenhum banco vetorial externo;
- nenhum modelo externo ou LLM obrigatório;
- nenhuma chamada de rede durante indexação ou resposta;
- nenhuma resposta afirmativa sem chunk recuperado;
- toda resposta não abstida possui citações;
- alteração de qualquer fonte indexada altera o `source_digest`;
- RAG não altera `predictive_evidence`, RIS, promoção de modelo, lockbox ou conclusão científica.

## Modos de uso

Após instalar o projeto no ambiente bloqueado:

```bash
sare-rag --root . status
sare-rag --root . search "vantagem preditiva" --top-k 5
sare-rag --root . context "como funciona a autoridade operacional?" --top-k 5
sare-rag --root . answer "qual é a conclusão científica atual?" --top-k 5
```

`status` reconstrói o índice e informa `source_count`, `chunk_count`, `source_digest`, retriever e generator.

`search` retorna os chunks ordenados com proveniência.

`context` produz um pacote de contexto citável para um consumidor externo, sem permitir que esse consumidor adquira autoridade sobre o estado canônico.

`answer` usa `deterministic_extractive_v1`: seleciona trechos das fontes recuperadas, deduplica evidência repetida e anexa referências `[n]`. Se não houver suporte lexical suficiente, retorna abstenção em vez de inventar conteúdo.

## Benchmark canônico de qualidade

O corpus de avaliação versionado fica em `governance/rag/eval_cases.json` e é executado por `scripts/evaluate_rag.py`.

O benchmark cobre, no mínimo:

- conclusão científica vigente;
- autoridade operacional GitHub-only;
- contrato T30 de carteiras;
- governança do lockbox;
- aquisição/segurança MCP;
- arquitetura do próprio RAG;
- limites de escrita de agentes;
- integridade econômica;
- abstenção para consulta sem suporte;
- isolamento de pseudo-segredo fora do corpus.

A prova calcula `MRR`, taxa de fonte relevante no rank 1, grounding de todas as citações e conformidade das abstenções. O gate falha se qualquer caso obrigatório falhar ou se as métricas mínimas versionadas não forem atingidas.

## Especialistas agentivos responsáveis

A governança mantém dois especialistas dedicados, sem autoridade para mutar branches canônicas:

- `rag-retrieval-engineer`: recuperação, reranking, autoridade/frescura de fontes, digest e regressão de ranking;
- `rag-evaluation-redteam`: grounding, abstenção, prompt injection, isolamento de fontes e avaliação adversarial.

As skills correspondentes são registradas em `governance/agents/skills.json`. LlamaIndex Workflows foi adquirido somente como referência/adapter target para padrões de RAG, reranking, citação, corrective RAG, testes e observabilidade. Nenhum pacote LlamaIndex foi adicionado ao runtime.

## Operação GitHub-only

O workflow `RAG Proof` executa:

1. validação da governança agentiva;
2. testes unitários do RAG;
3. construção do índice e resposta fundamentada de prova;
4. benchmark canônico de qualidade;
5. smoke test da CLI;
6. publicação das evidências.

Os artefatos incluem:

- `rag-status.json`;
- `rag-proof.json`;
- `rag-eval.json`;
- `rag-query.json`, quando uma consulta manual é fornecida.

O workflow é read-only e pode ser disparado por Pull Request, por mudança relevante em `main` e manualmente. A prova operacional só é considerada válida quando o workflow correspondente ao commit passa no GitHub Actions.

## Limites deliberados da versão 1

Esta implementação usa recuperação lexical/reranking determinístico e geração extrativa. Ela não reivindica recuperação semântica por embeddings nem geração livre por LLM. Uma futura camada semântica exige experimento separado, revisão de dependência/licença/segurança e prova de ganho no benchmark canônico antes de entrar no runtime.
