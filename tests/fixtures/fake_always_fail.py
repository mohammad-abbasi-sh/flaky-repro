#!/usr/bin/env python3
"""Fake always-failing test command (a broken test, not a flaky one)."""
import sys


def main():
    print("FAILED: simulated consistent failure")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
