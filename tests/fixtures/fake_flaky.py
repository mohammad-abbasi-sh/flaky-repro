#!/usr/bin/env python3
"""Fake flaky test command for the flaky_check test suite.

Exits 1 when the seed is a multiple of 7 plus 3 (seeds 3, 10, 17, ...),
0 otherwise. The seed comes from $FLAKY_SEED (set by flaky_check.py
for --cmd invocations) or from --seed.
"""
import os
import sys


def main():
    seed = None
    args = sys.argv[1:]
    if "--seed" in args:
        seed = int(args[args.index("--seed") + 1])
    else:
        seed = int(os.environ.get("FLAKY_SEED", "0"))
    print(f"fake test run, seed={seed}")
    if seed % 7 == 3:
        print("FAILED: simulated flaky failure (seed % 7 == 3)")
        return 1
    print("passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
