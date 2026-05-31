"""Tetromino geometry and SRS wall-kick data.

SHARED CONTEXT (project conventions)
------------------------------------
Coordinates: x increases right, y increases DOWN, origin top-left. Every cell is
an integer (x, y) pair. Board is 10 wide (BOARD_W=10) x 20 tall (BOARD_H=20).
Color IDs: I=1, O=2, T=3, S=4, Z=5, J=6, L=7, empty=0.
Rotation indices: 0 = spawn, 1 = R (one CW turn), 2 = 180 degrees, 3 = L (one CCW
turn). Cells produced here are box-local; board placement is box_origin + local.

This module is pure data + pure lookups (stdlib only, no state, no I/O). Cells are
authored on each piece's SRS bounding box at spawn (rotation 0); rotation states
1..3 are derived programmatically by rotating the box CLOCKWISE so they can never
disagree with the authored spawn layout.
"""

from __future__ import annotations

Cell = tuple[int, int]

# Color IDs per the shared context.
COLORS: dict[str, int] = {
    "I": 1,
    "O": 2,
    "T": 3,
    "S": 4,
    "Z": 5,
    "J": 6,
    "L": 7,
}

# --------------------------------------------------------------------------- #
# Piece geometry                                                              #
# --------------------------------------------------------------------------- #
#
# Each piece is authored as its spawn (rotation 0) layout on its SRS bounding
# box. JLSTZ use a 3x3 box, I uses 4x4, O uses 2x2. "X" = filled cell.
_SPAWN_GRIDS: dict[str, list[str]] = {
    "T": [
        ".X.",
        "XXX",
        "...",
    ],
    "J": [
        "X..",
        "XXX",
        "...",
    ],
    "L": [
        "..X",
        "XXX",
        "...",
    ],
    "S": [
        ".XX",
        "XX.",
        "...",
    ],
    "Z": [
        "XX.",
        ".XX",
        "...",
    ],
    "I": [
        "....",
        "XXXX",
        "....",
        "....",
    ],
    "O": [
        "XX",
        "XX",
    ],
}


def _grid_cells(grid: list[str]) -> list[Cell]:
    """Collect filled (x, y) coords from a grid, in reading order (y, then x)."""
    return [
        (x, y)
        for y, row in enumerate(grid)
        for x, ch in enumerate(row)
        if ch == "X"
    ]


def _rotate_grid_cw(grid: list[str]) -> list[str]:
    """Rotate a square box grid 90 degrees CLOCKWISE (x right, y down).

    A filled cell at (x, y) moves to (n-1-y, x).
    """
    n = len(grid)
    new = [["."] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            if grid[y][x] == "X":
                new[x][n - 1 - y] = "X"
    return ["".join(row) for row in new]


def _build_states(grid: list[str]) -> list[list[Cell]]:
    """Derive the 4 rotation states by rotating the box CW from spawn."""
    states: list[list[Cell]] = []
    g = grid
    for _ in range(4):
        cells = sorted(_grid_cells(g), key=lambda c: (c[1], c[0]))
        states.append(cells)
        g = _rotate_grid_cw(g)
    return states


# type -> 4 rotation states -> 4 cells each.
SPAWN_STATES: dict[str, list[list[Cell]]] = {
    t: _build_states(g) for t, g in _SPAWN_GRIDS.items()
}

# O is rotationally symmetric: a single state shared across all 4 indices.
SPAWN_STATES["O"] = [SPAWN_STATES["O"][0]] * 4

# Derivation invariant: every state of every piece is exactly 4 unique cells.
for _t, _states in SPAWN_STATES.items():
    assert len(_states) == 4, _t
    for _st in _states:
        assert len(_st) == 4 and len(set(_st)) == 4, (_t, _st)


# --------------------------------------------------------------------------- #
# Wall kicks (SRS)                                                            #
# --------------------------------------------------------------------------- #
#
# Authored in the standard y-UP convention. Our game is y-DOWN, so the dy of
# every offset is negated when stored (done programmatically below so the stored
# tables cannot drift from the authored y-up source). Offsets are tried in order.
_JLSTZ_KICKS_YUP: dict[tuple[int, int], list[Cell]] = {
    (0, 1): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (1, 0): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
    (1, 2): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
    (2, 1): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (2, 3): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (3, 2): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (3, 0): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (0, 3): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
}

_I_KICKS_YUP: dict[tuple[int, int], list[Cell]] = {
    (0, 1): [(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)],
    (1, 0): [(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)],
    (1, 2): [(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)],
    (2, 1): [(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)],
    (2, 3): [(0, 0), (2, 0), (-1, 0), (2, 1), (-1, -2)],
    (3, 2): [(0, 0), (-2, 0), (1, 0), (-2, -1), (1, 2)],
    (3, 0): [(0, 0), (1, 0), (-2, 0), (1, -2), (-2, 1)],
    (0, 3): [(0, 0), (-1, 0), (2, 0), (-1, 2), (2, -1)],
}


def _to_ydown(table: dict[tuple[int, int], list[Cell]]) -> dict[tuple[int, int], list[Cell]]:
    """Negate dy of every offset to convert y-up SRS data into our y-down frame."""
    return {key: [(dx, -dy) for dx, dy in offsets] for key, offsets in table.items()}


SRS_KICKS: dict[tuple[int, int], list[Cell]] = _to_ydown(_JLSTZ_KICKS_YUP)
SRS_KICKS_I: dict[tuple[int, int], list[Cell]] = _to_ydown(_I_KICKS_YUP)


# --------------------------------------------------------------------------- #
# Public lookups                                                             #
# --------------------------------------------------------------------------- #
def cells(piece_type: str, rot: int) -> list[Cell]:
    """Box-local cells of `piece_type` in rotation state `rot` (0..3)."""
    return SPAWN_STATES[piece_type][rot % 4]


def kicks(piece_type: str, from_rot: int, to_rot: int) -> list[Cell]:
    """Ordered wall-kick offsets to test when rotating from -> to.

    I uses the I-table, O never kicks ([(0, 0)]), everything else uses JLSTZ.
    """
    if piece_type == "O":
        return [(0, 0)]
    table = SRS_KICKS_I if piece_type == "I" else SRS_KICKS
    return table[(from_rot, to_rot)]


# --------------------------------------------------------------------------- #
# Self-check                                                                 #
# --------------------------------------------------------------------------- #
def _self_check() -> None:
    # All 7 types present; every state has exactly 4 unique cells.
    assert set(SPAWN_STATES) == set(COLORS) == {"I", "O", "T", "S", "Z", "J", "L"}
    for t in SPAWN_STATES:
        for r in range(4):
            st = cells(t, r)
            assert len(st) == 4 and len(set(st)) == 4, (t, r, st)

    # O is identical for all rotations.
    assert cells("O", 0) == cells("O", 1) == cells("O", 2) == cells("O", 3)

    # I spawn lies on one horizontal line; R state on one vertical line.
    i0 = cells("I", 0)
    assert len({y for _x, y in i0}) == 1 and len({x for x, _y in i0}) == 4
    i1 = cells("I", 1)
    assert len({x for x, _y in i1}) == 1 and len({y for _x, y in i1}) == 4

    # Every kick transition exists for JLSTZ and I.
    transitions = {(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2), (3, 0), (0, 3)}
    assert set(SRS_KICKS) == set(SRS_KICKS_I) == transitions

    # kicks("J", 0, 1) has 5 entries, starts with (0, 0), and its stored dy
    # signs are flipped relative to the authored y-up table.
    j01 = kicks("J", 0, 1)
    assert len(j01) == 5 and j01[0] == (0, 0)
    for (dx, dy), (ux, uy) in zip(j01, _JLSTZ_KICKS_YUP[(0, 1)]):
        assert dx == ux and dy == -uy

    # O never kicks; I uses the dedicated I-table.
    assert kicks("O", 0, 1) == kicks("O", 2, 3) == [(0, 0)]
    assert kicks("I", 0, 1) == SRS_KICKS_I[(0, 1)]
    assert kicks("I", 0, 1) != kicks("T", 0, 1)

    print("pieces.py self-check OK:", len(SPAWN_STATES), "pieces,", len(transitions), "kick transitions")


if __name__ == "__main__":
    _self_check()
