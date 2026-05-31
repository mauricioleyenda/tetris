"""Per-connection game session: the asyncio + WebSocket boundary.

SHARED CONTEXT (project conventions)
------------------------------------
Coordinates: x increases right, y increases DOWN, origin top-left. Board is 10
wide x 20 tall. Color IDs: I=1, O=2, T=3, S=4, Z=5, J=6, L=7, empty=0. Rotation
indices: 0 = spawn, 1 = R, 2 = 180, 3 = L. Wire contract (client -> server):
    {"type":"input","action":"left|right|rotate_cw|rotate_ccw|soft|hard|hold"}
    {"type":"start"}  {"type":"pause"}
The server replies with the full snapshot (game.snapshot()) every tick and after
every mutating input.

Dependency rule: this is the ONLY file that touches both asyncio and the
WebSocket. TetrisGame stays pure/synchronous; SevenBag owns randomness. No locks
are needed -- asyncio is single-threaded and every TetrisGame mutation is
synchronous (no await mid-mutation). Keep it that way.
"""

from __future__ import annotations

import asyncio

try:  # package context (e.g. `uvicorn server.main:app`)
    from .game import TetrisGame
    from .randomizer import SevenBag
except ImportError:  # standalone (e.g. `python server/session.py`)
    from game import TetrisGame
    from randomizer import SevenBag

try:  # real disconnect signal when running under Starlette/FastAPI
    from starlette.websockets import WebSocketDisconnect
except Exception:  # keep the module importable/testable without Starlette
    class WebSocketDisconnect(Exception):
        """Fallback used only when Starlette is unavailable (e.g. unit tests)."""


# Flat action map: action name -> mutation on the (synchronous) game.
ACTIONS = {
    "left": lambda g: g.move(-1),
    "right": lambda g: g.move(1),
    "soft": lambda g: g.soft_drop(),
    "hard": lambda g: g.hard_drop(),
    "rotate_cw": lambda g: g.rotate("cw"),
    "rotate_ccw": lambda g: g.rotate("ccw"),
    "hold": lambda g: g.hold(),
}


class GameSession:
    ACTIONS = ACTIONS

    def __init__(self, ws) -> None:
        self.ws = ws                       # Starlette/FastAPI WebSocket
        self.bag = SevenBag()
        self.game = TetrisGame(self.bag.next)
        self.running = False
        self._started: asyncio.Event | None = None
        self._receiver_task: asyncio.Task | None = None
        self._ticker_task: asyncio.Task | None = None

    @staticmethod
    def gravity_seconds(level: int) -> float:
        """Guideline gravity per level, clamped to a sane floor.

        (0.8 - (level-1)*0.007) ** (level-1), floored so high levels do not
        busy-loop. Recomputed every tick so speed scales with level.
        """
        return max((0.8 - (level - 1) * 0.007) ** (level - 1), 0.016)

    async def _push(self) -> None:
        """Send a full snapshot to the client."""
        await self.ws.send_json(self.game.snapshot())

    # ------------------------------------------------------------------ #
    # Receiver task                                                      #
    # ------------------------------------------------------------------ #
    async def _handle(self, msg: dict) -> None:
        """Apply one client message; push a snapshot after any mutation."""
        mtype = msg.get("type")
        if mtype == "start":
            if not self._started.is_set():
                self._started.set()
            await self._push()                      # first snapshot
        elif mtype == "pause":
            self.game.paused = not self.game.paused
            await self._push()
        elif mtype == "input":
            action = self.ACTIONS.get(msg.get("action"))
            if action is not None:
                action(self.game)
                await self._push()                  # show the move immediately

    async def _receiver(self) -> None:
        try:
            while self.running:
                try:
                    msg = await self.ws.receive_json()
                except WebSocketDisconnect:
                    break
                await self._handle(msg)
                if self.game.over:
                    break
        finally:
            self.running = False
            if self._ticker_task is not None:
                self._ticker_task.cancel()

    # ------------------------------------------------------------------ #
    # Ticker task                                                        #
    # ------------------------------------------------------------------ #
    async def _ticker(self) -> None:
        try:
            await self._started.wait()              # don't tick until "start"
            while self.running and not self.game.over:
                await asyncio.sleep(self.gravity_seconds(self.game.level))
                if self.game.paused:
                    continue
                self.game.tick()
                await self._push()
        finally:
            self.running = False
            if self._receiver_task is not None:
                self._receiver_task.cancel()

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #
    async def run(self) -> None:
        """Drive the session until disconnect or game over, then clean up."""
        self.running = True
        self._started = asyncio.Event()
        self._receiver_task = asyncio.create_task(self._receiver())
        self._ticker_task = asyncio.create_task(self._ticker())
        try:
            await asyncio.gather(self._receiver_task, self._ticker_task)
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
        finally:
            self.running = False
            for task in (self._receiver_task, self._ticker_task):
                if task is not None:
                    task.cancel()
            for task in (self._receiver_task, self._ticker_task):
                if task is None:
                    continue
                try:
                    await task
                except (asyncio.CancelledError, WebSocketDisconnect):
                    pass
                except Exception:
                    # A connection that dies mid-send shouldn't crash shutdown.
                    pass


# --------------------------------------------------------------------------- #
# Self-check (acceptance) -- fake ws backed by a list/queue, no real sockets.  #
# --------------------------------------------------------------------------- #
def _self_check() -> None:
    class FakeWS:
        def __init__(self, incoming: list[dict]) -> None:
            self._incoming = list(incoming)
            self._idx = 0
            self.sent: list[dict] = []

        async def receive_json(self) -> dict:
            await asyncio.sleep(0)                   # yield to the event loop
            if self._idx >= len(self._incoming):
                raise WebSocketDisconnect()
            msg = self._incoming[self._idx]
            self._idx += 1
            return msg

        async def send_json(self, data: dict) -> None:
            await asyncio.sleep(0)
            self.sent.append(data)

    async def scenario() -> None:
        ws = FakeWS([{"type": "start"}, {"type": "input", "action": "left"}])
        session = GameSession(ws)
        await session.run()
        # At least two snapshots: the start snapshot and the post-move snapshot.
        assert len(ws.sent) >= 2, len(ws.sent)
        x0 = ws.sent[0]["piece"]["x"]
        x1 = ws.sent[1]["piece"]["x"]
        assert x1 == x0 - 1, (x0, x1)
        # Active piece never leaks into the board.
        assert all(c == 0 for row in ws.sent[0]["board"] for c in row)

    asyncio.run(scenario())

    # gravity_seconds strictly decreasing across levels 1..10, never below floor.
    vals = [GameSession.gravity_seconds(level) for level in range(1, 11)]
    assert all(a > b for a, b in zip(vals, vals[1:])), vals
    assert all(v >= 0.016 for v in vals), vals

    print("session.py self-check OK")


if __name__ == "__main__":
    _self_check()
