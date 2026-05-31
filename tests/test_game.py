"""Acceptance: server/game.py TetrisGame."""

from __future__ import annotations

from conftest import scripted_source

from server.game import TetrisGame


def fresh(*types: str) -> TetrisGame:
    g = TetrisGame(scripted_source(*(types or ("T",))))
    g.board = [[0] * g.BOARD_W for _ in range(g.BOARD_H)]
    return g


def test_single_clear_level1_is_100():
    g = fresh()
    g.score = g.lines = 0
    g.level = 1
    g.board[19] = [1] * 10
    g.clear_lines()
    assert (g.score, g.lines, g.level) == (100, 1, 1)


def test_tetris_level1_is_800():
    g = fresh()
    g.score = g.lines = 0
    g.level = 1
    for y in range(16, 20):
        g.board[y] = [1] * 10
    g.clear_lines()
    assert g.score == 800 and g.lines == 4


def test_clear_uses_level_at_clear_time():
    g = fresh()
    g.score = 0
    g.lines = 20
    g.level = 3
    g.board[19] = [1] * 10
    g.clear_lines()
    assert g.score == TetrisGame.SCORES[1] * 3 == 300


def test_ten_lines_advances_level_1_to_2():
    g = fresh()
    g.score = g.lines = 0
    g.level = 1
    for _ in range(10):
        g.board[19] = [1] * 10
        g.clear_lines()
    assert g.lines == 10 and g.level == 2


def test_soft_drop_adds_one_per_row():
    g = fresh()
    g._set_active("T")
    s0, y0 = g.score, g.cur_y
    assert g.soft_drop() is True
    assert g.score == s0 + 1 and g.cur_y == y0 + 1


def test_hard_drop_adds_two_per_row_and_locks():
    g = fresh()
    g._set_active("T")
    drop = g.ghost_y() - g.cur_y
    s0 = g.score
    g.hard_drop()
    assert g.score == s0 + 2 * drop
    assert any(c != 0 for row in g.board for c in row)


def test_hold_once_per_piece_then_after_lock():
    g = TetrisGame(scripted_source("T", "S", "Z", "J", "L", "I", "O"))
    g.board = [[0] * g.BOARD_W for _ in range(g.BOARD_H)]
    assert g.cur_type == "T" and g.held is None
    g.hold()
    assert g.held == "T" and g.cur_type == "S" and g.hold_used
    g.hold()  # second hold before lock is a no-op
    assert g.held == "T" and g.cur_type == "S"
    g.hard_drop()  # locks, spawns, resets hold_used
    assert g.hold_used is False
    locked = g.cur_type
    g.hold()
    assert g.held == locked and g.cur_type == "T"


def test_left_wall_kick_shifts_piece():
    g = fresh("I")
    g._set_active("I")
    assert g.rotate("cw")  # vertical
    while g.move(-1):
        pass  # slam flush left
    flush_x = g.cur_x
    assert g.rotate("cw") is True
    assert g.cur_x != flush_x  # a kick moved it off the wall


def test_filling_spawn_area_tops_out():
    g = TetrisGame(scripted_source("T"))
    g.board = [[1] * g.BOARD_W for _ in range(g.BOARD_H)]
    g.over = False
    g.spawn_piece()
    assert g.over is True


def test_snapshot_excludes_active_piece_from_board():
    g = fresh()
    g._set_active("T")
    snap = g.snapshot()
    assert len(snap["board"]) == 20
    assert all(len(row) == 10 for row in snap["board"])
    for x, y in snap["piece"]["cells"]:
        if 0 <= y < 20:
            assert snap["board"][y][x] == 0


def test_snapshot_seq_increments():
    g = fresh()
    g._set_active("T")
    assert g.snapshot()["seq"] == 1
    assert g.snapshot()["seq"] == 2
