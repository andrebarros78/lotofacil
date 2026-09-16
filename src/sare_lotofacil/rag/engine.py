from __future__ import annotations

from collections import Counter

from sare_lotofacil import __version__
from sare_lotofacil.rag.core import RagAnswer, RagCitation, RagHit, RepositoryRAG as _BaseRepositoryRAG, _tokens

_QUERY_FILLERS = {
    "atual",
    "atualmente",
    "como",
    "onde",
    "pergunta",
    "qual",
    "quais",
    "resposta",
    "situacao",
    "sobre",
    "status",
}
_RAG_META_TERMS = {
    "chunk",
    "contexto",
    "grounding",
    "index",
    "indice",
    "proveniencia",
    "rag",
    "retrieval",
    "retriever",
    "tfidf",
}
_QUERY_ALIASES = {
    "agente": ("agent",),
    "agentes": ("agent", "agents"),
    "escrever": ("write", "writes"),
    "escrita": ("write", "writing"),
    "diretamente": ("direct", "directly"),
    "autoridade": ("authority",),
    "operacional": ("operational",),
    "operacao": ("operation", "operational"),
    "canonica": ("canonical",),
    "canonico": ("canonical",),
    "executor": ("executor",),
    "aceito": ("accepted", "allowed"),
    "adquirido": ("acquired",),
    "autorizacao": ("authorization", "auth"),
    "controles": ("controls",),
    "carteira": ("portfolio",),
    "carteiras": ("portfolio", "portfolios"),
    "cartoes": ("cards",),
    "quantidade": ("count", "quantity"),
    "custo": ("cost",),
    "despesa": ("spend", "expense", "actual"),
    "real": ("actual",),
    "protege": ("protect", "protection"),
    "aberto": ("opened", "open"),
    "vantagem": ("advantage",),
    "preditiva": ("predictive",),
    "conclusao": ("conclusion",),
    "cientifica": ("scientific",),
    "padrao": ("standard",),
    "exigidos": ("required",),
}
_CURRENT_MISSION_PATH = f"docs/MISSION_PROVEN_{__version__.replace('.', '_')}.md"


def _semantic_tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in _tokens(text) if token not in _QUERY_FILLERS)


def _query_tokens(text: str) -> tuple[str, ...]:
    base = _semantic_tokens(text)
    expanded: list[str] = list(base)
    for token in base:
        expanded.extend(_QUERY_ALIASES.get(token, ()))
    return tuple(expanded)


def _source_weight(path: str, query_terms: set[str]) -> float:
    rag_meta_query = bool(query_terms & _RAG_META_TERMS)
    if path == "docs/RAG.md":
        return 1.15 if rag_meta_query else 0.35
    if path.startswith("src/sare_lotofacil/rag/"):
        return 1.08 if rag_meta_query else 0.18
    if path == _CURRENT_MISSION_PATH:
        return 1.30
    if path.startswith("docs/MISSION_PROVEN_1_1_") and path.endswith(".md"):
        return 0.68
    if path == "AGENTS.md" and query_terms & {"agent", "agents", "write", "direct", "directly", "main", "operations/state"}:
        return 1.32
    if path == "docs/GITHUB_OPERATIONS.md" and query_terms & {"authority", "operational", "canonical", "github", "executor"}:
        return 1.25
    if path.startswith("governance/agents/") and query_terms & {"agent", "agents", "mcp", "acquired", "authorization", "write"}:
        return 1.18
    if path == "README.md":
        return 1.18
    if path == "docs/MISSION_PROVEN.md":
        return 1.08
    return 1.0


class RepositoryRAG(_BaseRepositoryRAG):
    """Canonical RAG engine with lexical quality ranking and grounded answer selection."""

    def status(self) -> dict[str, object]:
        payload = super().status()
        payload["engine_version"] = "1.4"
        payload["retriever"] = "tfidf_cosine_coverage_bigram_authority_bilingual_v5"
        payload["current_mission_path"] = _CURRENT_MISSION_PATH
        payload["query_expansion"] = "deterministic_domain_aliases_v1"
        payload["implementation_source_policy"] = "rag_code_meta_priority_only_v1"
        return payload

    def search(self, query: str, *, top_k: int = 5, min_score: float = 0.02) -> tuple[RagHit, ...]:
        if not query.strip():
            raise ValueError("RAG_QUERY_EMPTY")
        if not 1 <= top_k <= 20:
            raise ValueError("RAG_TOP_K_OUT_OF_RANGE")
        if not 0.0 <= min_score <= 2.0:
            raise ValueError("RAG_MIN_SCORE_OUT_OF_RANGE")

        query_terms = _query_tokens(query)
        if not query_terms:
            return ()
        query_counts = Counter(query_terms)
        query_vector = self._vector(query_counts)
        if not query_vector:
            return ()

        query_set = set(query_terms)
        semantic_query_terms = _semantic_tokens(query)
        query_bigrams = set(zip(semantic_query_terms, semantic_query_terms[1:]))
        ranked: list[RagHit] = []
        for chunk in self.chunks:
            chunk_terms = _semantic_tokens(chunk.content)
            chunk_set = set(chunk_terms)
            lexical = self._cosine(query_vector, self._vector(self._token_counts[chunk.chunk_id]))
            coverage = len(query_set & chunk_set) / len(query_set)
            if query_bigrams:
                chunk_bigrams = set(zip(chunk_terms, chunk_terms[1:]))
                adjacency = len(query_bigrams & chunk_bigrams) / len(query_bigrams)
            else:
                adjacency = 0.0
            raw_score = lexical + (0.22 * coverage) + (0.18 * adjacency)
            score = raw_score * _source_weight(chunk.path, query_set)
            if score < min_score:
                continue
            ranked.append(
                RagHit(
                    chunk_id=chunk.chunk_id,
                    path=chunk.path,
                    line_start=chunk.line_start,
                    line_end=chunk.line_end,
                    score=score,
                    content=chunk.content,
                )
            )
        ranked.sort(key=lambda hit: (-hit.score, hit.path, hit.line_start, hit.chunk_id))
        return tuple(ranked[:top_k])

    def answer(self, question: str, *, top_k: int = 5, max_citations: int = 4) -> RagAnswer:
        if not 1 <= max_citations <= 8:
            raise ValueError("RAG_MAX_CITATIONS_OUT_OF_RANGE")
        hits = self.search(question, top_k=top_k)
        if not hits:
            return RagAnswer(
                question=question,
                answer="Não encontrei evidência suficiente nas fontes canônicas indexadas para responder com segurança.",
                citations=(),
                source_digest=self.source_digest,
                generator="deterministic_extractive_v1",
                abstained=True,
            )

        strong_threshold = max(0.05, hits[0].score * 0.55)
        query_terms = set(_query_tokens(question))
        selected: list[tuple[RagHit, str]] = []
        seen_excerpts: set[str] = set()
        for hit in hits:
            if hit.score < strong_threshold:
                continue
            excerpt = self._best_excerpt(hit, query_terms)
            excerpt_key = " ".join(_semantic_tokens(excerpt))
            if not excerpt_key or excerpt_key in seen_excerpts:
                continue
            seen_excerpts.add(excerpt_key)
            selected.append((hit, excerpt))
            if len(selected) >= max_citations:
                break

        if not selected:
            return RagAnswer(
                question=question,
                answer="Não encontrei evidência suficiente nas fontes canônicas indexadas para responder com segurança.",
                citations=(),
                source_digest=self.source_digest,
                generator="deterministic_extractive_v1",
                abstained=True,
            )

        citations = tuple(
            RagCitation(
                citation_id=index,
                chunk_id=hit.chunk_id,
                path=hit.path,
                line_start=hit.line_start,
                line_end=hit.line_end,
                score=hit.score,
            )
            for index, (hit, _) in enumerate(selected, start=1)
        )
        answer_parts = [
            f"{excerpt} [{index}]"
            for index, (_, excerpt) in enumerate(selected, start=1)
        ]
        return RagAnswer(
            question=question,
            answer=" ".join(answer_parts),
            citations=citations,
            source_digest=self.source_digest,
            generator="deterministic_extractive_v1",
            abstained=False,
        )
