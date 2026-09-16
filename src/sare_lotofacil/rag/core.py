from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

RAG_ENGINE_VERSION = "1.0"
DEFAULT_SOURCE_SPECS = (
    "README.md",
    "AGENTS.md",
    "docs",
    "governance",
    "src/sare_lotofacil",
)
ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".py"}
EXCLUDED_DIR_NAMES = {".git", ".pytest_cache", ".venv", "venv", "__pycache__", "node_modules"}
MAX_FILE_BYTES = 512_000

_STOPWORDS = {
    "a", "as", "ao", "aos", "com", "como", "da", "das", "de", "do", "dos", "e", "em",
    "entre", "esta", "este", "foi", "na", "nas", "no", "nos", "o", "os", "ou", "para",
    "por", "que", "se", "sem", "ser", "sua", "suas", "um", "uma", "uns", "umas",
}
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_.:/+-]*")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n{2,}")


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _tokens(text: str) -> tuple[str, ...]:
    values = _TOKEN_RE.findall(_normalize(text))
    return tuple(token for token in values if len(token) > 1 and token not in _STOPWORDS)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RagChunk:
    chunk_id: str
    path: str
    line_start: int
    line_end: int
    content: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RagHit:
    chunk_id: str
    path: str
    line_start: int
    line_end: int
    score: float
    content: str

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["score"] = round(self.score, 12)
        return payload


@dataclass(frozen=True)
class RagCitation:
    citation_id: int
    chunk_id: str
    path: str
    line_start: int
    line_end: int
    score: float

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["score"] = round(self.score, 12)
        return payload


@dataclass(frozen=True)
class RagAnswer:
    question: str
    answer: str
    citations: tuple[RagCitation, ...]
    source_digest: str
    generator: str
    abstained: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "source_digest": self.source_digest,
            "generator": self.generator,
            "abstained": self.abstained,
        }


def _safe_repository_file(root: Path, candidate: Path) -> bool:
    if candidate.is_symlink() or not candidate.is_file():
        return False
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError):
        return False
    if any(part in EXCLUDED_DIR_NAMES for part in resolved.parts):
        return False
    if resolved.suffix.lower() not in ALLOWED_SUFFIXES:
        return False
    try:
        return resolved.stat().st_size <= MAX_FILE_BYTES
    except OSError:
        return False


def _discover_sources(root: Path, source_specs: Iterable[str]) -> tuple[Path, ...]:
    found: set[Path] = set()
    for raw_spec in source_specs:
        spec = (root / raw_spec).resolve()
        try:
            spec.relative_to(root)
        except ValueError:
            continue
        if spec.is_file():
            if _safe_repository_file(root, spec):
                found.add(spec)
            continue
        if not spec.is_dir():
            continue
        for candidate in spec.rglob("*"):
            if _safe_repository_file(root, candidate):
                found.add(candidate.resolve())
    return tuple(sorted(found, key=lambda path: path.relative_to(root).as_posix()))


def _chunk_text(path: str, text: str, *, max_chars: int, overlap_lines: int) -> tuple[RagChunk, ...]:
    lines = text.splitlines()
    if not lines:
        return ()
    chunks: list[RagChunk] = []
    start = 0
    while start < len(lines):
        end = start
        size = 0
        while end < len(lines):
            line_size = len(lines[end]) + 1
            if end > start and size + line_size > max_chars:
                break
            size += line_size
            end += 1
        content = "\n".join(lines[start:end]).strip()
        if content:
            material = f"{path}:{start + 1}:{end}:{content}"
            chunks.append(
                RagChunk(
                    chunk_id=_sha256_text(material)[:20],
                    path=path,
                    line_start=start + 1,
                    line_end=end,
                    content=content,
                )
            )
        if end >= len(lines):
            break
        start = max(start + 1, end - overlap_lines)
    return tuple(chunks)


class RepositoryRAG:
    """Read-only, deterministic and auditable retrieval-augmented answering over repository sources."""

    def __init__(self, *, chunks: tuple[RagChunk, ...], source_digest: str, source_count: int):
        self.chunks = chunks
        self.source_digest = source_digest
        self.source_count = source_count
        self._token_counts: dict[str, Counter[str]] = {}
        document_frequency: Counter[str] = Counter()
        for chunk in chunks:
            counts = Counter(_tokens(chunk.content))
            self._token_counts[chunk.chunk_id] = counts
            document_frequency.update(counts.keys())
        total = max(1, len(chunks))
        self._idf = {
            term: math.log((total + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }

    @classmethod
    def from_repository(
        cls,
        root: str | Path,
        *,
        source_specs: Iterable[str] = DEFAULT_SOURCE_SPECS,
        max_chunk_chars: int = 1_600,
        overlap_lines: int = 3,
    ) -> "RepositoryRAG":
        root_path = Path(root).resolve(strict=True)
        if not root_path.is_dir():
            raise ValueError("RAG_ROOT_NOT_DIRECTORY")
        if max_chunk_chars < 256:
            raise ValueError("RAG_CHUNK_TOO_SMALL")
        if overlap_lines < 0 or overlap_lines > 20:
            raise ValueError("RAG_OVERLAP_OUT_OF_RANGE")

        source_paths = _discover_sources(root_path, source_specs)
        digest = hashlib.sha256()
        chunks: list[RagChunk] = []
        for source_path in source_paths:
            relative = source_path.relative_to(root_path).as_posix()
            try:
                text = source_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(text.encode("utf-8")).digest())
            digest.update(b"\0")
            chunks.extend(
                _chunk_text(
                    relative,
                    text,
                    max_chars=max_chunk_chars,
                    overlap_lines=overlap_lines,
                )
            )
        return cls(chunks=tuple(chunks), source_digest=digest.hexdigest(), source_count=len(source_paths))

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def status(self) -> dict[str, object]:
        return {
            "engine_version": RAG_ENGINE_VERSION,
            "source_count": self.source_count,
            "chunk_count": self.chunk_count,
            "source_digest": self.source_digest,
            "retriever": "tfidf_cosine_v1",
            "generator": "deterministic_extractive_v1",
            "external_model": False,
            "external_vector_store": False,
            "read_only": True,
        }

    def _vector(self, counts: Counter[str]) -> dict[str, float]:
        vector: dict[str, float] = {}
        for term, frequency in counts.items():
            idf = self._idf.get(term)
            if idf is None:
                continue
            vector[term] = (1.0 + math.log(frequency)) * idf
        return vector

    @staticmethod
    def _cosine(left: dict[str, float], right: dict[str, float]) -> float:
        if not left or not right:
            return 0.0
        common = left.keys() & right.keys()
        numerator = sum(left[term] * right[term] for term in common)
        left_norm = math.sqrt(sum(value * value for value in left.values()))
        right_norm = math.sqrt(sum(value * value for value in right.values()))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)

    def search(self, query: str, *, top_k: int = 5, min_score: float = 0.02) -> tuple[RagHit, ...]:
        if not query.strip():
            raise ValueError("RAG_QUERY_EMPTY")
        if not 1 <= top_k <= 20:
            raise ValueError("RAG_TOP_K_OUT_OF_RANGE")
        if not 0.0 <= min_score <= 2.0:
            raise ValueError("RAG_MIN_SCORE_OUT_OF_RANGE")

        query_counts = Counter(_tokens(query))
        query_vector = self._vector(query_counts)
        if not query_vector:
            return ()
        normalized_query = " ".join(_tokens(query))
        ranked: list[RagHit] = []
        for chunk in self.chunks:
            score = self._cosine(query_vector, self._vector(self._token_counts[chunk.chunk_id]))
            if normalized_query and normalized_query in " ".join(_tokens(chunk.content)):
                score += 0.15
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

    def context(self, query: str, *, top_k: int = 5) -> str:
        hits = self.search(query, top_k=top_k)
        blocks = [
            f"[SOURCE {hit.path}:L{hit.line_start}-L{hit.line_end} chunk={hit.chunk_id} score={hit.score:.6f}]\n{hit.content}"
            for hit in hits
        ]
        return "\n\n".join(blocks)

    @staticmethod
    def _best_excerpt(hit: RagHit, query_terms: set[str]) -> str:
        candidates = [segment.strip() for segment in _SENTENCE_RE.split(hit.content) if segment.strip()]
        if not candidates:
            return hit.content[:600].strip()
        scored: list[tuple[int, int, str]] = []
        for position, candidate in enumerate(candidates):
            candidate_terms = set(_tokens(candidate))
            overlap = len(query_terms & candidate_terms)
            scored.append((overlap, -position, candidate))
        scored.sort(reverse=True)
        excerpt = scored[0][2]
        if len(excerpt) <= 600:
            return excerpt
        shortened = excerpt[:597].rsplit(" ", 1)[0].rstrip()
        return f"{shortened}…"

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

        query_terms = set(_tokens(question))
        selected = hits[:max_citations]
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
