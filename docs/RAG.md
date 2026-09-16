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
4. tokenização normalizada;
5. índice TF-IDF em memória;
6. recuperação top-k por similaridade cosseno;
7. geração extrativa determinística a partir dos chunks recuperados;
8. emissão de citações com caminho, faixa de linhas, `chunk_id` e score;
9. abstenção quando a consulta não possui suporte no índice.

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

`answer` usa `deterministic_extractive_v1`: seleciona trechos das fontes recuperadas e anexa referências `[n]`. Se não houver suporte lexical suficiente, retorna abstenção em vez de inventar conteúdo.

## Operação GitHub-only

O workflow `RAG Proof` executa o teste específico do RAG e produz, como artefatos:

- `rag-status.json`;
- `rag-answer.json`.

O workflow é read-only e pode ser disparado por Pull Request, por mudança relevante em `main` e manualmente. A prova operacional só é considerada válida quando o workflow correspondente ao commit passa no GitHub Actions.

## Limites deliberados da versão 1

Esta implementação usa recuperação lexical TF-IDF e geração extrativa. Ela não reivindica recuperação semântica por embeddings nem geração livre por LLM. Uma futura camada semântica exige experimento separado, revisão de dependência/licença/segurança e prova de valor antes de entrar no runtime canônico.
