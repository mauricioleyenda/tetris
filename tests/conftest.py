"""Shared test helpers.

SHARED CONTEXT: x right, y down; board 10x20; color IDs I=1..L=7; rotations
0=spawn,1=R,2=180,3=L. These tests exercise the per-module acceptance checks plus
an end-to-end WebSocket integration test.
"""

from __future__ import annotations

from collections.abc import Callable


def scripted_source(*types: str) -> Callable[[], str]:
    """A deterministic piece_source cycling a fixed list (no RNG)."""
    seq = list(types) or ["T"]
    i = {"n": 0}

    def src() -> str:
        t = seq[i["n"] % len(seq)]
        i["n"] += 1
        return t

    return src
