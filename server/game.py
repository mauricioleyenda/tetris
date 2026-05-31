"""Pure synchronous Tetris logic.

SHARED CONTEXT (project conventions)
------------------------------------
Coordinates: x increases right, y increases DOWN, origin top-left. Every cell is
an integer (x, y) pair. Board is 10 wide (BOARD_W=10) x 20 tall (BOARD_H=20).
Board representation: 20 rows of 10 ints; 0 = empty, 1..7 = a locked cell's color
ID. The active piece and its ghost are NEVER written into the board until lock();
they travel separately in the snapshot. Color IDs: I=1, O=2, T=3, S=4, Z=5, J=6,
L=7, empty=0. Rotation indices: 0 = spawn, 1 = R, 2 = 180, 3 = L.

Dependency rule: pure synchronous logic only -- no asyncio, no sockets, no
`import random`. All randomness enters through the injected `piece_source`
callable. The only import is `pieces`.

Note: the spec lists both a `hold` state field and a `hold()` action. In Python an
instance attribute `self.hold` would shadow the method, so the held piece is
stored as `self.held` and surfaced as `"hold"` in the snapshot wire contract.
"""

from __future__ import annotations

from collections.abc import Callable

try:  # package context (e.g. `uvicorn server.main:app`)
    from . import pieces
except ImportError:  # standalone (e.g. `python server/game.py`)
    import pieces


class TetrisGame:
    BOARD_W, BOARD_H = 10, 20
    SCORES = {1: 100, 2: 300, 3: 500, 4: 800}
    LINES_PER_LEVEL = 10
    LOCK_DELAY_TICKS = 1     # grounded grace ticks before locking
    LOCK_RESET_CAP = 15      # max lock-timer resets per piece

    def __init__(self, piece_source: Callable[[], str]) -> None:
        self.piece_source = piece_source
        self.board: list[list[int]] = [
            [0] * self.BOARD_W for _ in range(self.BOARD_H)
        ]
        # Active piece state (set by spawn_piece / _set_active).
        self.cur_type: str = ""
        self.cur_rot: int = 0
        self.cur_x: int = 0
        self.cur_y: int = 0
        # Hold / queue.
        self.held: str | None = None
        self.hold_used: bool = False
        self.queue: list[str] = []
        # Scoring / progress.
        self.score: int = 0
        self.level: int = 1
        self.lines: int = 0
        # Flags / lock state / sequence.
        self.over: bool = False
        self.paused: bool = False
        self.lock_timer: int | None = None
        self.lock_resets: int = 0
        self.seq: int = 0

        self.spawn_piece()

    # ------------------------------------------------------------------ #
    # Queue / placement helpers                                          #
    # ------------------------------------------------------------------ #
    def _top_up_queue(self) -> None:
        """Keep the upcoming queue at least 5 deep by pulling from the source."""
        while len(self.queue) < 5:
            self.queue.append(self.piece_source())

    def _spawn_x(self, ptype: str) -> int:
        """Spawn x for a piece's box: O's 2x2 at x=4, 3x3/4x4 boxes at x=3."""
        return 4 if ptype == "O" else 3

    def _set_active(self, ptype: str) -> None:
        """Place `ptype` at its spawn position/rotation and reset lock state."""
        self.cur_type = ptype
        self.cur_rot = 0
        self.cur_x = self._spawn_x(ptype)
        self.cur_y = 0
        self.lock_timer = None
        self.lock_resets = 0

    # ------------------------------------------------------------------ #
    # Collision primitive (single source of truth)                       #
    # ------------------------------------------------------------------ #
    def _abs_cells(self, ptype: str, rot: int, x: int, y: int) -> list[tuple[int, int]]:
        """pieces.cells offset by (x, y) -> absolute board cells."""
        return [(cx + x, cy + y) for cx, cy in pieces.cells(ptype, rot)]

    def _collides(self, ptype: str, rot: int, x: int, y: int) -> bool:
        """True if placement is illegal.

        Illegal = out of horizontal bounds, below the floor, or overlapping a
        non-zero board cell. Cells above the top (y < 0) are allowed so that
        spawning/rotating near the ceiling works.
        """
        for cx, cy in self._abs_cells(ptype, rot, x, y):
            if cx < 0 or cx >= self.BOARD_W:
                return True
            if cy >= self.BOARD_H:
                return True
            if cy >= 0 and self.board[cy][cx] != 0:
                return True
        return False

    # ------------------------------------------------------------------ #
    # Spawning                                                           #
    # ------------------------------------------------------------------ #
    def spawn_piece(self) -> None:
        """Pop the next piece from the queue and make it active.

        Tops the queue back up to >= 5, resets per-piece lock/hold state, and
        flags `over` if the new piece collides immediately (top-out).
        """
        self._top_up_queue()
        ptype = self.queue.pop(0)
        self._top_up_queue()
        self._set_active(ptype)
        self.hold_used = False
        if self._collides(self.cur_type, self.cur_rot, self.cur_x, self.cur_y):
            self.over = True

    # ------------------------------------------------------------------ #
    # Lock timer                                                         #
    # ------------------------------------------------------------------ #
    def _reset_lock(self) -> None:
        """Refresh the lock grace timer after a successful move/rotate.

        Only acts while grounded, and only up to LOCK_RESET_CAP times per piece.
        """
        grounded = self._collides(self.cur_type, self.cur_rot, self.cur_x, self.cur_y + 1)
        if grounded and self.lock_resets < self.LOCK_RESET_CAP:
            self.lock_timer = self.LOCK_DELAY_TICKS
            self.lock_resets += 1

    # ------------------------------------------------------------------ #
    # Inputs                                                             #
    # ------------------------------------------------------------------ #
    def move(self, dx: int) -> bool:
        """Shift horizontally if clear; refresh lock timer on success."""
        if not self._collides(self.cur_type, self.cur_rot, self.cur_x + dx, self.cur_y):
            self.cur_x += dx
            self._reset_lock()
            return True
        return False

    def soft_drop(self) -> bool:
        """Move down one row if clear: +1 score, refresh lock timer."""
        if not self._collides(self.cur_type, self.cur_rot, self.cur_x, self.cur_y + 1):
            self.cur_y += 1
            self.score += 1
            self._reset_lock()
            return True
        return False

    def hard_drop(self) -> None:
        """Drop to the ghost position (+2 per row), then lock immediately."""
        target = self.ghost_y()
        self.score += 2 * (target - self.cur_y)
        self.cur_y = target
        self.lock()

    def rotate(self, direction: str) -> bool:
        """Rotate cw/ccw, trying SRS kicks in order; first that clears wins."""
        to_rot = (self.cur_rot + 1) % 4 if direction == "cw" else (self.cur_rot - 1) % 4
        for dx, dy in pieces.kicks(self.cur_type, self.cur_rot, to_rot):
            if not self._collides(self.cur_type, to_rot, self.cur_x + dx, self.cur_y + dy):
                self.cur_x += dx
                self.cur_y += dy
                self.cur_rot = to_rot
                self._reset_lock()
                return True
        return False

    def hold(self) -> None:
        """Swap the active piece with the hold slot (once per piece)."""
        if self.hold_used:
            return
        if self.held is None:
            self.held = self.cur_type
            self._top_up_queue()
            ptype = self.queue.pop(0)
            self._top_up_queue()
        else:
            self.held, ptype = self.cur_type, self.held
        self._set_active(ptype)
        self.hold_used = True
        if self._collides(self.cur_type, self.cur_rot, self.cur_x, self.cur_y):
            self.over = True

    # ------------------------------------------------------------------ #
    # Gravity / locking / line clears                                    #
    # ------------------------------------------------------------------ #
    def ghost_y(self) -> int:
        """Lowest y the current piece can occupy unobstructed."""
        y = self.cur_y
        while not self._collides(self.cur_type, self.cur_rot, self.cur_x, y + 1):
            y += 1
        return y

    def lock(self) -> None:
        """Write the active piece into the board, clear lines, spawn next."""
        color = pieces.COLORS[self.cur_type]
        for cx, cy in self._abs_cells(self.cur_type, self.cur_rot, self.cur_x, self.cur_y):
            if 0 <= cy < self.BOARD_H and 0 <= cx < self.BOARD_W:
                self.board[cy][cx] = color
        self.clear_lines()
        self.spawn_piece()

    def clear_lines(self) -> None:
        """Remove full rows, refill from the top, and score using level-at-clear."""
        kept = [row for row in self.board if any(c == 0 for c in row)]
        n = self.BOARD_H - len(kept)
        if n == 0:
            return
        self.board = [[0] * self.BOARD_W for _ in range(n)] + kept
        self.score += self.SCORES[n] * self.level
        self.lines += n
        self.level = self.lines // self.LINES_PER_LEVEL + 1

    def tick(self) -> None:
        """One gravity step. No-op while paused or over."""
        if self.paused or self.over:
            return
        if not self._collides(self.cur_type, self.cur_rot, self.cur_x, self.cur_y + 1):
            self.cur_y += 1
            self.lock_timer = None
        else:
            if self.lock_timer is None:
                self.lock_timer = self.LOCK_DELAY_TICKS
            else:
                self.lock_timer -= 1
            if self.lock_timer == 0:
                self.lock()

    # ------------------------------------------------------------------ #
    # Wire contract                                                      #
    # ------------------------------------------------------------------ #
    def snapshot(self) -> dict:
        """Full server -> client snapshot (per SHARED CONTEXT)."""
        self.seq += 1
        piece_cells = self._abs_cells(self.cur_type, self.cur_rot, self.cur_x, self.cur_y)
        gy = self.ghost_y()
        ghost_cells = self._abs_cells(self.cur_type, self.cur_rot, self.cur_x, gy)
        return {
            "board": [row[:] for row in self.board],
            "piece": {
                "type": self.cur_type,
                "rot": self.cur_rot,
                "x": self.cur_x,
                "y": self.cur_y,
                "cells": [[x, y] for x, y in piece_cells],
            },
            "ghost": {
                "y": gy,
                "cells": [[x, y] for x, y in ghost_cells],
            },
            "next": self.queue[:3],
            "hold": self.held,
            "score": self.score,
            "level": self.level,
            "lines": self.lines,
            "over": self.over,
            "paused": self.paused,
            "seq": self.seq,
        }


# --------------------------------------------------------------------------- #
# Self-check (acceptance) -- scripted deterministic piece_source, no RNG.      #
# --------------------------------------------------------------------------- #
def _self_check() -> None:
    def source(*types: str) -> Callable[[], str]:
        seq = list(types)
        i = {"n": 0}

        def src() -> str:
            t = seq[i["n"] % len(seq)]
            i["n"] += 1
            return t

        return src

    def empty(g: TetrisGame) -> None:
        g.board = [[0] * g.BOARD_W for _ in range(g.BOARD_H)]

    # --- Scoring: single / tetris / level multiplier -----------------------
    g = TetrisGame(source("T"))
    empty(g)
    g.score = g.lines = 0
    g.level = 1
    g.board[19] = [1] * 10
    g.clear_lines()
    assert g.score == 100 and g.lines == 1 and g.level == 1, (g.score, g.lines, g.level)

    g = TetrisGame(source("T"))
    empty(g)
    g.score = g.lines = 0
    g.level = 1
    for y in range(16, 20):
        g.board[y] = [1] * 10
    g.clear_lines()
    assert g.score == 800 and g.lines == 4, (g.score, g.lines)

    g = TetrisGame(source("T"))
    empty(g)
    g.score = 0
    g.lines = 20
    g.level = 3
    g.board[19] = [1] * 10
    g.clear_lines()
    assert g.score == TetrisGame.SCORES[1] * 3 == 300, g.score

    # --- 10 lines moves level 1 -> 2 ---------------------------------------
    g = TetrisGame(source("T"))
    empty(g)
    g.score = g.lines = 0
    g.level = 1
    for _ in range(10):
        g.board[19] = [1] * 10
        g.clear_lines()
    assert g.lines == 10 and g.level == 2, (g.lines, g.level)

    # --- Soft drop adds 1/row ----------------------------------------------
    g = TetrisGame(source("T"))
    empty(g)
    g._set_active("T")
    s0, y0 = g.score, g.cur_y
    assert g.soft_drop() and g.score == s0 + 1 and g.cur_y == y0 + 1

    # --- Hard drop adds 2/row and locks immediately ------------------------
    g = TetrisGame(source("T"))
    empty(g)
    g._set_active("T")
    drop = g.ghost_y() - g.cur_y
    s0 = g.score
    g.hard_drop()
    assert g.score == s0 + 2 * drop, (g.score, drop)
    assert any(c != 0 for row in g.board for c in row), "hard_drop must lock the piece"

    # --- Hold: once per piece; second is no-op; works again after lock -----
    g = TetrisGame(source("T", "S", "Z", "J", "L", "I", "O"))
    empty(g)
    assert g.cur_type == "T" and g.held is None
    g.hold()
    assert g.held == "T" and g.cur_type == "S" and g.hold_used
    g.hold()  # no-op
    assert g.held == "T" and g.cur_type == "S"
    g.hard_drop()  # locks S, spawns next, resets hold_used
    assert not g.hold_used
    locked_type = g.cur_type
    g.hold()
    assert g.held == locked_type and g.cur_type == "T", (g.held, g.cur_type)

    # --- Left-wall kick: vertical I flush left rotates and shifts right -----
    g = TetrisGame(source("I"))
    empty(g)
    g._set_active("I")
    assert g.rotate("cw")            # now vertical (rot 1)
    while g.move(-1):
        pass                         # slam flush against the left wall
    flush_x = g.cur_x
    assert g.rotate("cw"), "rotation at the wall must succeed via a kick"
    assert g.cur_x != flush_x, "a wall kick must have shifted the piece"

    # --- Top-out: filling the spawn area then spawning sets over ----------
    g = TetrisGame(source("T"))
    g.board = [[1] * g.BOARD_W for _ in range(g.BOARD_H)]
    g.over = False
    g.spawn_piece()
    assert g.over is True

    # --- snapshot never bakes the active piece into the board -------------
    g = TetrisGame(source("T"))
    empty(g)
    g._set_active("T")
    snap = g.snapshot()
    for x, y in snap["piece"]["cells"]:
        if 0 <= y < g.BOARD_H:
            assert snap["board"][y][x] == 0, "active piece leaked into board"
    assert all(c == 0 for row in snap["board"] for c in row)

    print("game.py self-check OK")


if __name__ == "__main__":
    _self_check()
