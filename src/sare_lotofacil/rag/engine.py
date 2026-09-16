from __future__ import annotations

from collections import Counter

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


def _semantic_tokens(text: str) -> tuple[str, ...]:
    return tuple(token for token in _tokens(text) if token not in _QUERY_FILLERS)


class RepositoryRAG(_BaseRepositoryRAG):
    """Canonical RAG engine with lexical quality ranking and grounded answer selection."""

    def status(self) -> dict[str, object]:
        payload = super().status()
        payload["engine_version"] = "1.1"
        payload["retriever"] = "tfidf_cosine_coverage_bigram_v2"
        return payload

    def search(self, query: str, *, top_k: int = 5, min_score: float = 0.02) -> tuple[RagHit, ...]:
        if not query.strip():
            raise ValueError("RAG_QUERY_EMPTY")
        if not 1 <= top_k <= 20:
            raise ValueError("RAG_TOP_K_OUT_OF_RANGE")
        if not 0.0 <= min_score <= 2.0:
            raise ValueError("RAG_MIN_SCORE_OUT_OF_RANGE")

        query_terms = _semantic_tokens(query)
        if not query_terms:
            return ()
        query_counts = Counter(query_terms)
        query_vector = self._vector(query_counts)
        if not query_vector:
            return ()

        query_set = set(query_terms)
        query_bigrams = set(zip(query_terms, query_terms[1:]))
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
            score = lexical + (0.22 * coverage) + (0.18 * adjacency)
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
        selected = tuple(hit for hit in hits if hit.score >= strong_threshold)[:max_citations]
        query_terms = set(_semantic_tokens(question))
        citations = tuple(
            RagCitation(
                citation_id=index,
                chunk_id=hit.chunk_id,
                path=hit.path,
                line_start=hit.line_start,
                line_end=hit.line_end,
                score=hit.score,
            )
            for index, hit in enumerate(selected, start=1)
        )
        answer_parts = [
            f"{self._best_excerpt(hit, query_terms)} [{index}]"
            for index, hit in enumerate(selected, start=1)
        ]
        return RagAnswer(
            question=question,
            answer=" ".join(answer_parts),
            citations=citations,
            source_digest=self.source_digest,
            generator="deterministic_extractive_v1",
            abstained=False,
        )
