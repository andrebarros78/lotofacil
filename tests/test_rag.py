from __future__ import annotations

from pathlib import Path

from sare_lotofacil.rag.core import RepositoryRAG


def _fixture_repository(root: Path) -> None:
    (root / "README.md").write_text(
        "# Sistema\n\nNão há vantagem preditiva comprovada.\n\nO executor canônico é GitHub Actions.\n",
        encoding="utf-8",
    )
    docs = root / "docs"
    docs.mkdir()
    (docs / "RAG.md").write_text(
        "# RAG\n\nO RAG é somente leitura e toda resposta precisa carregar proveniência.\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("SUPER_SECRET=nao_indexar\n", encoding="utf-8")


def test_rag_retrieves_grounded_source_with_line_provenance(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    rag = RepositoryRAG.from_repository(
        tmp_path,
        source_specs=("README.md", "docs"),
        max_chunk_chars=256,
    )

    hits = rag.search("vantagem preditiva comprovada", top_k=3)

    assert hits
    assert hits[0].path == "README.md"
    assert hits[0].line_start >= 1
    assert hits[0].line_end >= hits[0].line_start
    assert "vantagem preditiva comprovada" in hits[0].content


def test_rag_answer_is_extractive_cited_and_non_hallucinatory(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    rag = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)

    result = rag.answer("Qual é a situação da vantagem preditiva?", top_k=3)

    assert result.abstained is False
    assert result.citations
    assert any(citation.path == "README.md" for citation in result.citations)
    assert "[1]" in result.answer
    assert "vantagem preditiva" in result.answer.casefold()
    assert result.generator == "deterministic_extractive_v1"


def test_rag_abstains_when_repository_has_no_support(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    rag = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)

    result = rag.answer("xilofonium quasar inexistente", top_k=3)

    assert result.abstained is True
    assert result.citations == ()
    assert "Não encontrei evidência suficiente" in result.answer


def test_rag_source_digest_is_deterministic_and_changes_with_source(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    first = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)
    second = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)
    assert first.source_digest == second.source_digest

    (tmp_path / "docs" / "RAG.md").write_text(
        "# RAG\n\nO conteúdo canônico foi alterado de forma auditável.\n",
        encoding="utf-8",
    )
    changed = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)
    assert changed.source_digest != first.source_digest


def test_rag_does_not_index_unlisted_secret_files(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    rag = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)

    assert all(hit.path != ".env" for hit in rag.search("SUPER_SECRET", top_k=5))
    assert rag.answer("SUPER_SECRET", top_k=5).abstained is True


def test_rag_status_declares_read_only_no_external_runtime(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    rag = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)

    status = rag.status()

    assert status["read_only"] is True
    assert status["external_model"] is False
    assert status["external_vector_store"] is False
    assert status["retriever"] == "tfidf_cosine_v1"
    assert status["generator"] == "deterministic_extractive_v1"
    assert status["source_count"] == 2
    assert status["chunk_count"] >= 2


def test_rag_context_pack_contains_source_markers(tmp_path: Path) -> None:
    _fixture_repository(tmp_path)
    rag = RepositoryRAG.from_repository(tmp_path, source_specs=("README.md", "docs"), max_chunk_chars=256)

    context = rag.context("executor canônico GitHub Actions", top_k=2)

    assert "[SOURCE README.md:L" in context
    assert "GitHub Actions" in context
