"""Fixed version of the order-dependent fixture: sorts before asserting,
so it passes for every PYTHONHASHSEED. The same flaky_check invocation
that failed on test_order.py must exit 0 on this file — the proof loop.
"""

ITEMS = {"apple", "banana", "cherry", "date", "elderberry", "fig", "grape"}


def test_set_order_is_stable():
    assert sorted(ITEMS) == [
        "apple", "banana", "cherry", "date", "elderberry", "fig", "grape",
    ]
