"""Control fixture: a stable test. flaky_check must exit 0 on it."""


def test_always_passes():
    assert 1 + 1 == 2
