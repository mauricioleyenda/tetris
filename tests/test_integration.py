"""End-to-end: boot the real app and drive it over a WebSocket client."""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    port = _free_port()
    config = uvicorn.Config(
        "server.main:app", host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):  # wait up to ~10s for startup
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, "uvicorn failed to start"
    yield port
    server.should_exit = True
    thread.join(timeout=5)


async def test_ws_full_session(live_server):
    from websockets.asyncio.client import connect

    uri = f"ws://127.0.0.1:{live_server}/ws"
    async with connect(uri) as ws:
        await ws.send(json.dumps({"type": "start"}))
        snaps = [json.loads(await ws.recv())]

        # A scripted sequence of moves; each mutating input yields a snapshot.
        for action in ["left", "left", "rotate_cw", "right", "soft", "rotate_ccw"]:
            await ws.send(json.dumps({"type": "input", "action": action}))
            snaps.append(json.loads(await ws.recv()))

    # seq is strictly monotonically increasing across every snapshot.
    seqs = [s["seq"] for s in snaps]
    assert seqs == sorted(seqs)
    assert len(set(seqs)) == len(seqs)

    # Board is always 20 rows x 10 cols.
    for s in snaps:
        assert len(s["board"]) == 20
        assert all(len(row) == 10 for row in s["board"])

    # The piece actually moves (its x is not constant across the run).
    xs = [s["piece"]["x"] for s in snaps]
    assert len(set(xs)) > 1

    # Every snapshot carries a ghost and a real piece type.
    for s in snaps:
        assert s["piece"]["type"] in set("IOTSZJL")
        assert "cells" in s["ghost"]
