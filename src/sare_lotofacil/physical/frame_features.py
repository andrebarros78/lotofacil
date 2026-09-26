from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class FrameFingerprint:
    algorithm: str
    width: int
    height: int
    average_hash_hex: str
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def average_hash_gray(raw_gray: bytes, *, width: int = 16, height: int = 16) -> FrameFingerprint:
    """Create a stable coarse visual fingerprint from one grayscale frame.

    The hash is a scene fingerprint, not a claim that a machine/ball-set identity
    has been established. Identity requires prospective clustering and review.
    """

    expected = width * height
    if len(raw_gray) != expected:
        raise ValueError(f"P15_FRAME_SIZE_INVALID:{len(raw_gray)}!={expected}")
    mean = sum(raw_gray) / expected
    bits = 0
    for value in raw_gray:
        bits = (bits << 1) | int(value >= mean)
    hex_len = (expected + 3) // 4
    return FrameFingerprint(
        algorithm="AHASH_GRAY_V1",
        width=width,
        height=height,
        average_hash_hex=f"{bits:0{hex_len}x}",
        sha256=hashlib.sha256(raw_gray).hexdigest(),
    )


def hamming_distance_hex(left: str, right: str) -> int:
    if len(left) != len(right):
        raise ValueError("P15_FRAME_HASH_LENGTH_MISMATCH")
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError as exc:
        raise ValueError("P15_FRAME_HASH_HEX_INVALID") from exc


def mean_adjacent_distance(fingerprints: Sequence[FrameFingerprint]) -> float | None:
    if len(fingerprints) < 2:
        return None
    distances = [
        hamming_distance_hex(left.average_hash_hex, right.average_hash_hex)
        for left, right in zip(fingerprints, fingerprints[1:])
    ]
    return sum(distances) / len(distances)
