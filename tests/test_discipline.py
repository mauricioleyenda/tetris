"""Dependency-discipline checks (parse actual imports, not doc mentions).

- `random` may only be imported by randomizer.py.
- game.py and pieces.py must not import asyncio or socket.
"""

from __future__ import annotations

import ast
import pathlib

SERVER = pathlib.Path(__file__).resolve().parents[1] / "server"


def _top_level_imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
    return mods


def test_random_only_in_randomizer():
    for py in SERVER.glob("*.py"):
        imports = _top_level_imports(py)
        if py.name == "randomizer.py":
            assert "random" in imports  # it genuinely owns randomness
        else:
            assert "random" not in imports, f"{py.name} must not import random"


def test_pure_modules_have_no_asyncio_or_socket():
    for name in ("game.py", "pieces.py"):
        imports = _top_level_imports(SERVER / name)
        assert "asyncio" not in imports, f"{name} must not import asyncio"
        assert "socket" not in imports, f"{name} must not import socket"


def test_pieces_imports_stdlib_only():
    # pieces.py is pure data: no sibling/server imports.
    imports = _top_level_imports(SERVER / "pieces.py")
    assert "server" not in imports
    assert "game" not in imports and "session" not in imports
