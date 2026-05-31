"""FastAPI wiring -- HTTP routes, static assets, and the /ws game socket.

SHARED CONTEXT (project conventions)
------------------------------------
Coordinates: x increases right, y increases DOWN, origin top-left. Board is 10
wide x 20 tall. Color IDs: I=1, O=2, T=3, S=4, Z=5, J=6, L=7, empty=0. Rotation
indices: 0 = spawn, 1 = R, 2 = 180, 3 = L.

Dependency rule: this file is FastAPI wiring ONLY -- zero game logic. Each socket
hands off entirely to a GameSession, which owns the asyncio + game loop.
"""

from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .session import GameSession

app = FastAPI()

# Static assets (game.js, style.css, ...). Paths are relative to the repo root,
# matching `uvicorn server.main:app` launched from there.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    """Serve the game page."""
    return FileResponse("static/index.html")


@app.get("/health")
async def health() -> dict:
    """Liveness probe."""
    return {"ok": True}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    """Accept a connection and hand it to a per-connection GameSession."""
    await ws.accept()
    session = GameSession(ws)
    try:
        await session.run()
    except WebSocketDisconnect:
        pass
