"""Order-dependent fixture: asserts on set iteration order.

Set iteration order for strings depends on PYTHONHASHSEED, so this test
passes for some seeds and fails for others — a genuine order-dependent
flaky test with no plugins required. flaky_check.py should find a
failing seed for it within a few runs. (Asserting on the *first*
element, not the full order: the full sorted order almost never occurs
by chance, which would make this a consistently-failing test instead.)

The fixed version is test_order_fixed.py (sorts before asserting).
"""

ITEMS = {"apple", "banana", "cherry", "date", "elderberry", "fig", "grape"}


def test_first_item_is_apple():
    assert list(ITEMS)[0] == "apple"
