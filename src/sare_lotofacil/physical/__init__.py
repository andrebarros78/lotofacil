"""Physical/operational observation research for the P15 one-card program.

This package must only consume information available before or during the
observed draw procedure.  Extracted variables are research evidence and never
constitute predictive proof by themselves.
"""

from .video_index import (
    PhysicalVideoIndex,
    VideoIndexRecord,
    VideoMetadata,
    build_video_index,
    parse_lotofacil_contest_ids,
    parse_title_date,
)

__all__ = [
    "PhysicalVideoIndex",
    "VideoIndexRecord",
    "VideoMetadata",
    "build_video_index",
    "parse_lotofacil_contest_ids",
    "parse_title_date",
]
