# Tetris — server-authoritative (FastAPI + WebSocket)

A small, framework-free Tetris. The **server** owns all game state and rules; the
**browser** sends intent and renders snapshots. No build step, no frontend
framework.

## Conventions (shared context)

- Coordinates: `x` increases right, `y` increases **down**, origin top-left.
- Board: 10 wide × 20 tall.
- Color IDs: `I=1, O=2, T=3, S=4, Z=5, J=6, L=7`, empty `=0`.
- Rotation indices: `0=spawn, 1=R, 2=180°, 3=L` (SRS, with wall kicks).

## Architecture

```
server/
  pieces.py      pure data + lookups (geometry, SRS kicks). stdlib only.
  randomizer.py  SevenBag — the ONLY module that imports `random`.
  game.py        TetrisGame — pure synchronous logic. no asyncio/sockets/random.
  session.py     GameSession — the ONLY file touching asyncio + the WebSocket.
  main.py        FastAPI wiring only. zero game logic.
static/
  index.html     structure (canvases + sidebar + overlay)
  game.js        socket + input + requestAnimationFrame renderer
  style.css      cosmetics (CSS grid, 30px cells → 300×600 board)
```

The server sends the full snapshot every gravity tick and after every mutating
input, so the player always sees their own move immediately.

## Install

```bash
pip install -r requirements.txt
```

(Python 3.11+.)

## Run

```bash
uvicorn server.main:app --reload
```

Then open <http://localhost:8000>. The page connects over WebSocket and the piece
starts falling immediately.

## Controls

| Key            | Action      |
| -------------- | ----------- |
| ← / →          | Move left / right |
| ↓              | Soft drop (+1/row) |
| Space          | Hard drop (+2/row, locks) |
| ↑ or X         | Rotate clockwise |
| Z              | Rotate counter-clockwise |
| C or Shift     | Hold (once per piece) |
| P              | Pause / resume |

## Scoring

Line clears use the level **at clear time**: 1→100, 2→300, 3→500, 4→800, each
multiplied by the current level. Every 10 cleared lines advances the level, which
also speeds up gravity.

## Tests

```bash
pip install pytest pytest-asyncio
pytest
```

The suite covers each module's acceptance checks, an async end-to-end WebSocket
integration test, and a dependency-discipline check (no `random` outside
`randomizer.py`; no `asyncio`/`socket` imports in `game.py` or `pieces.py`).
