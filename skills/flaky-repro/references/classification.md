# Classification — what kind of flaky is it?

Classify *after* reproducing, from evidence, not from vibes. The checker
gives a hint (`--classify`); this reference explains the categories and
the fix direction for each.

## Order-dependent

**Signature:** passes alone (same seed), fails when run with the suite —
or fails only for some seeds and the failing tests share module state.

**Common causes:** module-level mutable state, test pollution (one test
mutates what another reads), fixtures that do not reset, set/dict
iteration order assumed to be stable, database rows left behind.

**Fix:** isolate state (fresh fixture per test, reset in teardown, sort
before asserting order). Never "fix" by reordering tests into a lucky
order — the next shuffle breaks it again.

## Timing

**Signature:** fails alone too, intermittently — and the failure involves
a clock, a sleep, a timeout, or a thread.

**Common causes:** `sleep()` as synchronization, too-tight timeouts,
`Date.now()` / `time.time()` assertions, unsynchronized threads,
waiting on a condition that is only usually true yet.

**Fix:** wait on the actual condition (poll with a deadline, join the
thread, await the event). Never lengthen a timeout or add a sleep —
that only changes the odds.

## Shared state / external service

**Signature:** fails when another test, process, or environment touched
the same resource (file, port, database, cache, network).

**Common causes:** hardcoded ports/paths, a shared test database, a
mock server started once for the suite, environment-dependent paths.

**Fix:** give each test its own resource (temp dir, random port, fresh
database) or make the dependency explicit. Serializing the whole suite
is a workaround, not a fix — record it as one if you do it.

## Consistently failing (not flaky)

**Signature:** fails on every run, every seed.

That is a broken test, not a flaky one. Fix it normally; this skill's
stress loop does not apply. If the checker reports 100% failure, say so
plainly and stop calling it flaky.

## How many runs prove a fix? (the math)

A fix is proven only when the same invocation that reproduced the
failure now passes in full. How many runs are "enough" depends on the
measured failure rate before the fix:

- If the test failed roughly 1 run in 2, 20 passing runs are already
  strong evidence (0.5^20 is about one in a million).
- If it failed 1 run in 50, 50 passing runs are weak: the broken version
  would also pass 50 runs about 36% of the time. You need hundreds of
  executions for a 1-in-50 flake to mean anything.
- If it failed 1 run in 1,000, even 500 passing runs still leave a ~61%
  chance the broken version would have passed them too.

Rule of thumb: required runs ≈ 5 / (failure rate). A 1-in-50 flake
(rate 0.02) needs ~250 runs; a 1-in-1,000 flake needs ~5,000. When in
doubt, run more — the checker is cheap, a false "fixed" is expensive.
Two green runs prove nothing, at any rate.
