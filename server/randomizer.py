"""Seven-bag tetromino randomizer.

SHARED CONTEXT (project conventions)
------------------------------------
Coordinates: x increases right, y increases DOWN, origin top-left. Board is 10
wide (BOARD_W=10) x 20 tall (BOARD_H=20). Color IDs: I=1, O=2, T=3, S=4, Z=5,
J=6, L=7, empty=0. Rotation indices: 0 = spawn, 1 = R, 2 = 180, 3 = L.

Dependency rule: this is the ONLY module allowed to import `random`. All other
modules (game.py in particular) receive randomness through an injected
piece-source callable, never by importing this directly into their logic.
"""

from __future__ import annotations

import random

_TYPES: tuple[str, ...] = ("I", "O", "T", "S", "Z", "J", "L")


class SevenBag:
    """Standard 7-bag randomizer over a private, seeded RNG.

    Each bag is a freshly shuffled permutation of all seven piece types, so any
    7 consecutive draws contain each type exactly once. A private
    ``random.Random`` instance keeps sequences reproducible and isolated from the
    module-global RNG.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)
        self._bag: list[str] = []

    def _new_bag(self, rng: random.Random) -> list[str]:
        """Return a freshly shuffled full bag, drawing entropy from `rng`."""
        bag = list(_TYPES)
        rng.shuffle(bag)
        return bag

    def next(self) -> str:
        """Pop and return the next piece type, refilling the bag first if empty."""
        if not self._bag:
            self._bag = self._new_bag(self._rng)
        return self._bag.pop(0)

    def peek(self, n: int) -> list[str]:
        """Return the next `n` upcoming types without mutating state.

        Refills happen on a cloned RNG and a local bag copy, so peeking can look
        arbitrarily far ahead while leaving the real RNG state and current bag
        untouched -- what ``next`` will return is unchanged.
        """
        if n <= 0:
            return []
        rng = random.Random()
        rng.setstate(self._rng.getstate())
        local = list(self._bag)
        out: list[str] = []
        while len(out) < n:
            if not local:
                local = self._new_bag(rng)
            out.append(local.pop(0))
        return out


def _self_check() -> None:
    # Reproducible across instances with the same seed; different seeds differ.
    a = [SevenBag(42).next() for _ in range(20)]
    b = [SevenBag(42).next() for _ in range(20)]
    assert a == b, "same seed must reproduce the same sequence"
    c = [SevenBag(7).next() for _ in range(20)]
    assert a != c, "different seeds should differ"

    # Any 7 consecutive draws contain each type exactly once.
    bag = SevenBag(123)
    draws = [bag.next() for _ in range(70)]
    for i in range(0, 70, 7):
        assert sorted(draws[i : i + 7]) == sorted(_TYPES), draws[i : i + 7]

    # peek does not mutate state, and matches the subsequent draws -- including
    # across a bag refill boundary.
    bag = SevenBag(99)
    bag.next()  # leave 6 in the current bag so peek(10) must cross a refill
    predicted = bag.peek(10)
    assert bag.peek(10) == predicted, "peek must be repeatable / non-mutating"
    actual = [bag.next() for _ in range(10)]
    assert predicted == actual, (predicted, actual)

    # Acceptance: peek(5) then five next() calls return exactly the peeked list.
    bag = SevenBag(2024)
    peeked = bag.peek(5)
    assert [bag.next() for _ in range(5)] == peeked

    print("randomizer.py self-check OK")


if __name__ == "__main__":
    _self_check()
