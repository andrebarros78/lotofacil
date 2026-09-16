from __future__ import annotations

import argparse
import json
from pathlib import Path

from sare_lotofacil.rag.core import RepositoryRAG


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sare-rag")
    parser.add_argument("--root", type=Path, default=Path("."), help="raiz do checkout canônico")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="reconstrói o índice e informa o estado do RAG")

    search = subparsers.add_parser("search", help="recupera chunks relevantes com proveniência")
    search.add_argument("query")
    search.add_argument("--top-k", type=int, default=5)

    context = subparsers.add_parser("context", help="gera pacote de contexto citável para consumidor externo")
    context.add_argument("query")
    context.add_argument("--top-k", type=int, default=5)

    answer = subparsers.add_parser("answer", help="gera resposta extrativa estritamente ancorada nas fontes recuperadas")
    answer.add_argument("question")
    answer.add_argument("--top-k", type=int, default=5)
    answer.add_argument("--max-citations", type=int, default=4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rag = RepositoryRAG.from_repository(args.root)

    if args.command == "status":
        print(json.dumps(rag.status(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "search":
        payload = {
            "query": args.query,
            "source_digest": rag.source_digest,
            "hits": [hit.to_dict() for hit in rag.search(args.query, top_k=args.top_k)],
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "context":
        print(rag.context(args.query, top_k=args.top_k))
        return 0
    if args.command == "answer":
        answer = rag.answer(args.question, top_k=args.top_k, max_citations=args.max_citations)
        print(json.dumps(answer.to_dict(), ensure_ascii=False, sort_keys=True))
        return 2 if answer.abstained else 0
    raise RuntimeError("comando RAG não tratado")


if __name__ == "__main__":
    raise SystemExit(main())
