from __future__ import annotations

import hashlib
from pathlib import Path

from sare_lotofacil.persistence.post_contest import list_post_contest_episodes
from sare_lotofacil.rag.core import RagChunk, RepositoryRAG


def _episode_chunks(db_path: str | Path) -> tuple[RagChunk, ...]:
    chunks: list[RagChunk] = []
    for episode in list_post_contest_episodes(db_path, limit=500):
        episode_id = str(episode["episode_id"])
        contest_id = int(episode["contest_id"])
        revision = int(episode["revision"])
        lines = [
            f"episodio pos-concurso {episode_id}",
            f"concurso {contest_id} revisao {revision}",
            f"resultado {' '.join(f'{n:02d}' for n in episode['result'])}",
            f"cartoes congelados {episode['card_count']} maximo de acertos {episode['max_hits']}",
        ]
        for item in episode["cards"]:
            lines.append(
                "cartao "
                f"portfolio={item['portfolio_id']} posicao={item['position']} "
                f"freeze={item['freeze_sha256']} hits={item['hits']} "
                f"dezenas={' '.join(f'{n:02d}' for n in item['card'])} "
                f"acertos={' '.join(f'{n:02d}' for n in item['matched_numbers'])} "
                f"faltantes={' '.join(f'{n:02d}' for n in item['omitted_winners'])}"
            )
        lines.append(
            "politica aprendizado retrospectivo apenas; cartoes congelados imutaveis; "
            "ajuste direto do champion proibido; challenger e validacao predeclarada obrigatorios"
        )
        content = "\n".join(lines)
        path = f"learning/post_contest/{contest_id}/revision-{revision}/{episode_id}.txt"
        material = f"{path}:1:{len(lines)}:{content}"
        chunk_id = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
        chunks.append(
            RagChunk(
                chunk_id=chunk_id,
                path=path,
                line_start=1,
                line_end=len(lines),
                content=content,
            )
        )
    return tuple(chunks)


def build_learning_rag(repository_root: str | Path, db_path: str | Path) -> RepositoryRAG:
    """Combina fontes canônicas do repositório com episódios pós-concurso auditados.

    O índice continua somente leitura: os episódios são materializados a partir do ledger
    de auditoria e nunca alteram previsões, cartões ou estado científico.
    """
    base = RepositoryRAG.from_repository(repository_root)
    episodes = _episode_chunks(db_path)
    digest = hashlib.sha256()
    digest.update(base.source_digest.encode("ascii"))
    for chunk in episodes:
        digest.update(chunk.chunk_id.encode("ascii"))
        digest.update(b"\0")
        digest.update(chunk.content.encode("utf-8"))
        digest.update(b"\0")
    return RepositoryRAG(
        chunks=base.chunks + episodes,
        source_digest=digest.hexdigest(),
        source_count=base.source_count + len(episodes),
    )
