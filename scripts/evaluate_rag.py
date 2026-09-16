from __future__ import annotations

import argparse
import json
from pathlib import Path

from sare_lotofacil.rag import RepositoryRAG


def _path_matches(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def evaluate(root: Path, cases_path: Path) -> dict[str, object]:
    document = json.loads(cases_path.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1:
        raise ValueError("RAG_EVAL_SCHEMA_UNSUPPORTED")

    rag = RepositoryRAG.from_repository(root)
    known_chunks = {
        chunk.chunk_id: (chunk.path, chunk.line_start, chunk.line_end)
        for chunk in rag.chunks
    }

    results: list[dict[str, object]] = []
    reciprocal_ranks: list[float] = []
    relevant_at_1 = 0

    for case in document.get("cases", []):
        case_id = str(case["id"])
        query = str(case["query"])
        top_k = int(case.get("top_k", 5))
        expected = list(case.get("expected_path_prefixes", []))
        forbidden_first = list(case.get("forbidden_first_path_prefixes", []))
        expect_abstain = bool(case.get("expect_abstain", False))

        hits = rag.search(query, top_k=top_k)
        answer = rag.answer(query, top_k=top_k)

        grounding_ok = all(
            citation.chunk_id in known_chunks
            and known_chunks[citation.chunk_id]
            == (citation.path, citation.line_start, citation.line_end)
            for citation in answer.citations
        )

        first_forbidden = bool(
            hits and forbidden_first and _path_matches(hits[0].path, forbidden_first)
        )

        if expect_abstain:
            relevant_rank = None
            reciprocal_rank = 1.0 if answer.abstained and not answer.citations else 0.0
            case_pass = bool(answer.abstained and not answer.citations and grounding_ok)
            relevant_at_1 += int(case_pass)
        else:
            relevant_rank = next(
                (
                    index
                    for index, hit in enumerate(hits, start=1)
                    if _path_matches(hit.path, expected)
                ),
                None,
            )
            reciprocal_rank = 1.0 / relevant_rank if relevant_rank else 0.0
            relevant_at_1 += int(relevant_rank == 1)
            case_pass = bool(
                not answer.abstained
                and answer.citations
                and relevant_rank is not None
                and grounding_ok
                and not first_forbidden
            )

        reciprocal_ranks.append(reciprocal_rank)
        results.append(
            {
                "id": case_id,
                "pass": case_pass,
                "expect_abstain": expect_abstain,
                "abstained": answer.abstained,
                "relevant_rank": relevant_rank,
                "reciprocal_rank": reciprocal_rank,
                "grounding_ok": grounding_ok,
                "first_path": hits[0].path if hits else None,
                "citation_paths": [citation.path for citation in answer.citations],
                "source_digest": answer.source_digest,
            }
        )

    total = len(results)
    if total == 0:
        raise ValueError("RAG_EVAL_EMPTY")

    mrr = sum(reciprocal_ranks) / total
    relevant_at_1_rate = relevant_at_1 / total
    acceptance = document.get("acceptance", {})
    minimum_mrr = float(acceptance.get("minimum_mrr", 0.0))
    minimum_relevant_at_1 = float(acceptance.get("minimum_relevant_at_1", 0.0))
    all_cases_pass = all(bool(item["pass"]) for item in results)

    status = "RAG_EVAL_PASS" if (
        all_cases_pass
        and mrr >= minimum_mrr
        and relevant_at_1_rate >= minimum_relevant_at_1
    ) else "RAG_EVAL_FAIL"

    return {
        "schema_version": 1,
        "status": status,
        "engine": rag.status(),
        "case_count": total,
        "passed_cases": sum(int(bool(item["pass"])) for item in results),
        "mrr": mrr,
        "relevant_at_1": relevant_at_1_rate,
        "minimum_mrr": minimum_mrr,
        "minimum_relevant_at_1": minimum_relevant_at_1,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("governance/rag/eval_cases.json"),
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    payload = evaluate(args.root, args.cases)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if payload["status"] == "RAG_EVAL_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
