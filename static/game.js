/*
 * SHARED CONTEXT (project conventions)
 * Coordinates: x increases right, y increases DOWN, origin top-left. Board is 10
 * wide x 20 tall. Color IDs: I=1, O=2, T=3, S=4, Z=5, J=6, L=7, empty=0.
 * Rotation indices: 0 = spawn, 1 = R, 2 = 180, 3 = L.
 *
 * The server is authoritative. This client only sends intent
 * ({"type":"input",...} / start / pause) and renders whatever snapshot comes
 * back. Client-side prediction is a future upgrade path; on localhost the
 * round-trip is imperceptible.
 *
 * Snapshot shape (server -> client):
 *   { board:[[int]], piece:{type,rot,x,y,cells:[[x,y]]},
 *     ghost:{y,cells:[[x,y]]}, next:[type], hold:type|null,
 *     score, level, lines, over, paused, seq }
 */

"use strict";

const BOARD_W = 10;
const BOARD_H = 20;
const CELL = 30; // px -> board canvas is 300 x 600

// Color IDs 1..7 matching the server (empty = 0 is never drawn).
const COLORS = {
  1: "#31c7ef", // I  cyan
  2: "#f7d308", // O  yellow
  3: "#ad4d9c", // T  purple
  4: "#42b642", // S  green
  5: "#ef2029", // Z  red
  6: "#5a65ad", // J  blue
  7: "#ef7921", // L  orange
};

// type -> color ID, for the next/hold previews (which arrive as bare names).
const TYPE_ID = { I: 1, O: 2, T: 3, S: 4, Z: 5, J: 6, L: 7 };

// Spawn-layout cells per type, box-local -- used ONLY to draw previews, where
// the server sends a type name with no geometry. Mirrors pieces.py spawn states.
const SHAPES = {
  I: [[0, 1], [1, 1], [2, 1], [3, 1]],
  O: [[0, 0], [1, 0], [0, 1], [1, 1]],
  T: [[1, 0], [0, 1], [1, 1], [2, 1]],
  S: [[1, 0], [2, 0], [0, 1], [1, 1]],
  Z: [[0, 0], [1, 0], [1, 1], [2, 1]],
  J: [[0, 0], [0, 1], [1, 1], [2, 1]],
  L: [[2, 0], [0, 1], [1, 1], [2, 1]],
};

// Keyboard -> intent. Values are either {action} (an input) or {type} (a verb).
const KEYMAP = {
  ArrowLeft: { action: "left" },
  ArrowRight: { action: "right" },
  ArrowDown: { action: "soft" },
  ArrowUp: { action: "rotate_cw" },
  KeyX: { action: "rotate_cw" },
  KeyZ: { action: "rotate_ccw" },
  Space: { action: "hard" },
  KeyC: { action: "hold" },
  ShiftLeft: { action: "hold" },
  ShiftRight: { action: "hold" },
  KeyP: { type: "pause" },
};

// Keys we never want to also scroll / activate the page.
const SWALLOW = new Set([
  "ArrowLeft", "ArrowRight", "ArrowDown", "ArrowUp", "Space",
]);

// --------------------------------------------------------------------------- //
// State                                                                       //
// --------------------------------------------------------------------------- //
let latestState = null;
let socket = null;

const els = {
  board: document.getElementById("board"),
  next: document.getElementById("next"),
  hold: document.getElementById("hold"),
  score: document.getElementById("score"),
  level: document.getElementById("level"),
  lines: document.getElementById("lines"),
  overlay: document.getElementById("overlay"),
  overlayScore: document.getElementById("overlay-score"),
  pauseBadge: document.getElementById("pause-badge"),
  stage: document.getElementById("stage"),
};

const boardCtx = els.board.getContext("2d");
const nextCtx = els.next.getContext("2d");
const holdCtx = els.hold.getContext("2d");

// --------------------------------------------------------------------------- //
// Socket                                                                      //
// --------------------------------------------------------------------------- //
function connect() {
  socket = new WebSocket("ws://" + location.host + "/ws");

  socket.addEventListener("open", () => {
    send({ type: "start" });
  });

  socket.addEventListener("message", (ev) => {
    try {
      latestState = JSON.parse(ev.data);
    } catch (_) {
      /* ignore malformed frames */
    }
  });

  // Optional reconnect: the server is authoritative, so just re-handshake.
  socket.addEventListener("close", () => {
    setTimeout(connect, 1000);
  });
}

function send(obj) {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(obj));
  }
}

// --------------------------------------------------------------------------- //
// Input                                                                       //
// --------------------------------------------------------------------------- //
window.addEventListener("keydown", (ev) => {
  if (ev.repeat && ev.code === "Space") return; // no hard-drop auto-repeat
  const intent = KEYMAP[ev.code];
  if (!intent) return;
  if (SWALLOW.has(ev.code)) ev.preventDefault();

  if (intent.type === "pause") {
    send({ type: "pause" });
  } else if (intent.action) {
    send({ type: "input", action: intent.action });
  }
});

// --------------------------------------------------------------------------- //
// Rendering                                                                   //
// --------------------------------------------------------------------------- //
function drawCell(ctx, x, y, size, color, mode) {
  const px = x * size;
  const py = y * size;
  if (mode === "ghost") {
    ctx.globalAlpha = 0.25;
    ctx.fillStyle = color;
    ctx.fillRect(px + 1, py + 1, size - 2, size - 2);
    ctx.globalAlpha = 1;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(px + 1.5, py + 1.5, size - 3, size - 3);
  } else {
    ctx.fillStyle = color;
    ctx.fillRect(px, py, size, size);
    // subtle bevel
    ctx.fillStyle = "rgba(255,255,255,0.18)";
    ctx.fillRect(px, py, size, 3);
    ctx.fillStyle = "rgba(0,0,0,0.25)";
    ctx.fillRect(px, py + size - 3, size, 3);
    ctx.strokeStyle = "rgba(0,0,0,0.35)";
    ctx.lineWidth = 1;
    ctx.strokeRect(px + 0.5, py + 0.5, size - 1, size - 1);
  }
}

function drawGrid() {
  boardCtx.strokeStyle = "rgba(255,255,255,0.05)";
  boardCtx.lineWidth = 1;
  for (let x = 1; x < BOARD_W; x++) {
    boardCtx.beginPath();
    boardCtx.moveTo(x * CELL + 0.5, 0);
    boardCtx.lineTo(x * CELL + 0.5, BOARD_H * CELL);
    boardCtx.stroke();
  }
  for (let y = 1; y < BOARD_H; y++) {
    boardCtx.beginPath();
    boardCtx.moveTo(0, y * CELL + 0.5);
    boardCtx.lineTo(BOARD_W * CELL, y * CELL + 0.5);
    boardCtx.stroke();
  }
}

function drawBoard(state) {
  boardCtx.fillStyle = "#0a0e16";
  boardCtx.fillRect(0, 0, els.board.width, els.board.height);
  drawGrid();

  // 1) locked cells
  for (let y = 0; y < state.board.length; y++) {
    const row = state.board[y];
    for (let x = 0; x < row.length; x++) {
      const id = row[x];
      if (id !== 0) drawCell(boardCtx, x, y, CELL, COLORS[id], "solid");
    }
  }

  const color = COLORS[TYPE_ID[state.piece.type]];

  // 2) ghost (translucent landing position)
  for (const [x, y] of state.ghost.cells) {
    if (y >= 0) drawCell(boardCtx, x, y, CELL, color, "ghost");
  }

  // 3) active piece (solid, on top)
  for (const [x, y] of state.piece.cells) {
    if (y >= 0) drawCell(boardCtx, x, y, CELL, color, "solid");
  }
}

// Draw a single piece centered in a preview canvas.
function drawPreview(ctx, canvas, type, originY) {
  const size = 22;
  const cells = SHAPES[type];
  if (!cells) return;
  const xs = cells.map((c) => c[0]);
  const ys = cells.map((c) => c[1]);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const w = (maxX - minX + 1) * size;
  const h = (maxY - minY + 1) * size;
  const offX = (canvas.width - w) / 2 - minX * size;
  const offY = originY + (60 - h) / 2 - minY * size;
  const color = COLORS[TYPE_ID[type]];
  for (const [x, y] of cells) {
    const px = offX + x * size;
    const py = offY + y * size;
    ctx.fillStyle = color;
    ctx.fillRect(px, py, size, size);
    ctx.strokeStyle = "rgba(0,0,0,0.35)";
    ctx.strokeRect(px + 0.5, py + 0.5, size - 1, size - 1);
  }
}

function clearCanvas(ctx, canvas) {
  ctx.fillStyle = "#0a0e16";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
}

function drawNext(state) {
  clearCanvas(nextCtx, els.next);
  const queue = state.next || [];
  queue.slice(0, 3).forEach((type, i) => {
    drawPreview(nextCtx, els.next, type, i * 100 + 10);
  });
}

function drawHold(state) {
  clearCanvas(holdCtx, els.hold);
  if (state.hold) drawPreview(holdCtx, els.hold, state.hold, 0);
}

function updateSidebar(state) {
  els.score.textContent = state.score;
  els.level.textContent = state.level;
  els.lines.textContent = state.lines;
}

function updateOverlays(state) {
  els.overlay.classList.toggle("hidden", !state.over);
  if (state.over) els.overlayScore.textContent = "Score: " + state.score;

  const paused = state.paused && !state.over;
  els.pauseBadge.classList.toggle("hidden", !paused);
  els.stage.classList.toggle("dim", paused);
}

function frame() {
  const state = latestState;
  if (state) {
    drawBoard(state);
    drawNext(state);
    drawHold(state);
    updateSidebar(state);
    updateOverlays(state);
  }
  requestAnimationFrame(frame);
}

// --------------------------------------------------------------------------- //
// Boot                                                                        //
// --------------------------------------------------------------------------- //
connect();
requestAnimationFrame(frame);
