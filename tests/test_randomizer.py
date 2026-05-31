"""Acceptance: server/randomizer.py SevenBag."""

from __future__ import annotations

from server.randomizer import SevenBag

TYPES = sorted("IOTSZJL")


def test_same_seed_reproduces_different_seed_differs():
    a = [SevenBag(42).next() for _ in range(20)]
    b = [SevenBag(42).next() for _ in range(20)]
    c = [SevenBag(7).next() for _ in range(20)]
    assert a == b
    assert a != c


def test_every_seven_draws_is_a_full_bag():
    bag = SevenBag(123)
    draws = [bag.next() for _ in range(70)]
    for i in range(0, 70, 7):
        assert sorted(draws[i : i + 7]) == TYPES


def test_peek_is_non_mutating_and_predicts_across_refill():
    bag = SevenBag(99)
    bag.next()  # leave 6 in the current bag so peek(10) crosses a refill
    predicted = bag.peek(10)
    assert bag.peek(10) == predicted  # repeatable
    actual = [bag.next() for _ in range(10)]
    assert actual == predicted


def test_peek_five_then_next_five_matches():
    bag = SevenBag(2024)
    peeked = bag.peek(5)
    assert [bag.next() for _ in range(5)] == peeked


def test_peek_zero_is_empty():
    assert SevenBag(1).peek(0) == []
