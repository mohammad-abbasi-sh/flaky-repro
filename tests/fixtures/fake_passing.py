#!/usr/bin/env python3
"""Fake always-passing test command for the flaky_check test suite."""
import os
import sys


def main():
    print(f"fake test run, seed={os.environ.get('FLAKY_SEED', '?')}")
    print("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
