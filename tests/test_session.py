"""Acceptance: server/session.py GameSession (unit, fake ws)."""

from __future__ import annotations

import asyncio

from server.session import GameSession, WebSocketDisconnect


class FakeWS:
    """Minimal async ws: replays `incoming`, records sent frames, then EOFs."""

    def __init__(self, incoming):
        self._incoming = list(incoming)
        self._idx = 0
        self.sent = []

    async def receive_json(self):
        await asyncio.sleep(0)
        if self._idx >= len(self._incoming):
            raise WebSocketDisconnect()
        msg = self._incoming[self._idx]
        self._idx += 1
        return msg

    async def send_json(self, data):
        await asyncio.sleep(0)
        self.sent.append(data)


def test_gravity_strictly_decreasing_and_floored():
    vals = [GameSession.gravity_seconds(lvl) for lvl in range(1, 11)]
    assert all(a > b for a, b in zip(vals, vals[1:]))
    assert all(v >= 0.016 for v in vals)


def test_gravity_floor_holds_at_high_levels():
    assert GameSession.gravity_seconds(50) == 0.016


async def test_start_then_left_produces_shifted_snapshot():
    ws = FakeWS([{"type": "start"}, {"type": "input", "action": "left"}])
    await GameSession(ws).run()
    assert len(ws.sent) >= 2
    assert ws.sent[1]["piece"]["x"] == ws.sent[0]["piece"]["x"] - 1
    # active piece never leaks into the board
    assert all(c == 0 for row in ws.sent[0]["board"] for c in row)


async def test_pause_toggles_state():
    ws = FakeWS([{"type": "start"}, {"type": "pause"}])
    await GameSession(ws).run()
    assert ws.sent[-1]["paused"] is True
