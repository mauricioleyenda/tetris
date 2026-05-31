"""Acceptance: server/pieces.py geometry + SRS kicks."""

from __future__ import annotations

import pytest

from server import pieces
from server.pieces import _JLSTZ_KICKS_YUP

ALL_TYPES = {"I", "O", "T", "S", "Z", "J", "L"}


def test_all_types_present_with_four_unique_cells():
    assert set(pieces.SPAWN_STATES) == ALL_TYPES == set(pieces.COLORS)
    for t in ALL_TYPES:
        for r in range(4):
            cells = pieces.cells(t, r)
            assert len(cells) == 4
            assert len(set(cells)) == 4


def test_o_identical_for_all_rotations():
    assert pieces.cells("O", 0) == pieces.cells("O", 1)
    assert pieces.cells("O", 1) == pieces.cells("O", 2) == pieces.cells("O", 3)


def test_i_spawn_horizontal_r_state_vertical():
    i0 = pieces.cells("I", 0)
    assert len({y for _x, y in i0}) == 1  # one horizontal line
    assert len({x for x, _y in i0}) == 4
    i1 = pieces.cells("I", 1)
    assert len({x for x, _y in i1}) == 1  # one vertical line
    assert len({y for _x, y in i1}) == 4


def test_colors_match_shared_context():
    assert pieces.COLORS == {"I": 1, "O": 2, "T": 3, "S": 4, "Z": 5, "J": 6, "L": 7}


def test_kicks_jlstz_0_to_1_and_dy_flipped():
    k = pieces.kicks("J", 0, 1)
    assert len(k) == 5
    assert k[0] == (0, 0)
    # Stored dy is negated relative to the authored y-up source table.
    for (dx, dy), (ux, uy) in zip(k, _JLSTZ_KICKS_YUP[(0, 1)]):
        assert dx == ux and dy == -uy


def test_kicks_o_never_moves_and_i_has_own_table():
    assert pieces.kicks("O", 0, 1) == [(0, 0)]
    assert pieces.kicks("O", 2, 3) == [(0, 0)]
    assert pieces.kicks("I", 0, 1) != pieces.kicks("T", 0, 1)


@pytest.mark.parametrize("frm,to", [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2), (3, 0), (0, 3)])
def test_every_transition_has_five_offsets(frm, to):
    assert len(pieces.kicks("T", frm, to)) == 5
    assert len(pieces.kicks("I", frm, to)) == 5
