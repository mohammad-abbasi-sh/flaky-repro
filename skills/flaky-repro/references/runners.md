# Per-runner seed and shuffle flags

The checker (`scripts/flaky_check.py`) uses these commands. A seed must be
recorded in the report — a failure without a seed is not a reproduction.

## pytest

```bash
PYTHONHASHSEED=<seed> python -m pytest <target> -q -p no:cacheprovider
```

`PYTHONHASHSEED` changes hash randomization, which changes set/dict
iteration order — the most common source of order-dependent Python tests.
If `pytest-randomly` is installed, the checker also adds
`--randomly-seed=<seed>`, which shuffles test *order* itself.

To replay one failing test alone:

```bash
PYTHONHASHSEED=<seed> python -m pytest <path>::<test> -q
```

## Go

```bash
go test -shuffle=on -count=1 <package>
```

Go exposes no seed flag: `-shuffle=on` shuffles test order with a random
seed each run. The checker therefore records the **run index** (seed
number in the report is the iteration, not a Go seed) and the exact
command. To replay, run the same command — it will shuffle differently,
so a Go reproduction is weaker than a seeded one; note that honestly in
the report and run more iterations.

## Jest

```bash
npx jest <target> --randomize --seed=<seed>
```

`--randomize` shuffles test order; `--seed` makes it reproducible
(Jest 29+). Replay with the same seed to get the same order.

## Vitest

```bash
npx vitest run <target> --sequence.seed=<seed> --sequence.shuffle
```

Replay with the same seed.

## No runner detected

If the checker prints "no test runner detected", do not guess a command.
Either the project uses a runner this skill does not know (add it to
`references/runners.md` and the detector in `flaky_check.py`), or the
test needs an explicit command — pass it with `--cmd`, e.g.:

```bash
python3 scripts/flaky_check.py <target> \
  --cmd "python3 run_tests.py --seed {seed} {target}"
```

`{seed}` and `{target}` are substituted per run; the seed is also
available as the `FLAKY_SEED` environment variable.
