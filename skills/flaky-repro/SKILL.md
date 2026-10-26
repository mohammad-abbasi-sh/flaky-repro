---
name: flaky-repro
description: Reproduce a flaky or intermittent test failure on demand with a recorded seed and replay command before fixing it, then prove the fix with a deterministic seeded stress run. Use when a test "sometimes fails", "passes locally but fails in CI", "fails once in a while", or an agent previously reported a flaky test fixed after only a couple of green runs. Also run the bundled checker to verify a fix is real before reporting done.
---

# Flaky-test reproduction — fail on demand, then prove the fix

Agents routinely "fix" flaky tests without ever seeing them fail: they run the
test twice, get green, and report it fixed. Two green runs are exactly what
the broken version produces most of the time. The agent proved nothing.

This skill enforces a contract: **no fix without a failing seed, no "done"
without a passing stress run.**

## The contract

1. **Reproduce first.** Before touching any code, run the bundled checker
   until it produces a failing seed and an exact replay command:

   ```bash
   python3 scripts/flaky_check.py <test-target> [--runs N] [--seed S]
   ```

   If the checker cannot reproduce the failure in N runs, do NOT claim the
   test is fixed — report "could not reproduce in N runs" and increase N or
   widen the target (the whole file / module, not one test). A test you
   cannot fail on demand is a test you cannot prove fixed.

2. **Record the evidence.** The checker writes `flaky-report.md`: target,
   runner, runs, seeds tried, first failing seed + replay command, failure
   rate, classification hint. The replay command must fail when run by hand.
   If it does not, the reproduction is invalid — find the real trigger.

3. **Classify before fixing** (`references/classification.md`):
   - **Order-dependent** — passes alone, fails with the suite (shared
     module state, test pollution). Fix by isolating state, never by
     reordering tests into a "lucky" order.
   - **Timing** — fails alone too, intermittently (`sleep`, `Date.now()`,
     tight timeouts, thread races). Fix the race / wait condition, never
     by lengthening a timeout.
   - **Shared state / external** — fails when another test or service
     touched the same resource. Fix the isolation, never by serializing
     the suite as a permanent workaround.
   - **Consistently failing** — fails every run. That is not a flaky test,
     it is a broken test. Fix it normally; this skill's stress loop does
     not apply.

4. **Forbidden fixes.** These are never a fix for a flaky test, and the
   report must record them as violations if they appear in the diff:
   retries (`retry`, `flaky` plugins that re-run), `sleep()` added to make
   a race "go away", skipping (`t.Skip`, `@pytest.mark.skip`, `test.skip`),
   longer timeouts, quarantining / deleting the test without a tracking
   issue. Any of these turns a real bug into a hidden one.

5. **Prove the fix.** After the fix, run the *same* checker invocation
   that reproduced the failure. It must exit 0 over the full run count
   before you report done. The required run count follows the measured
   failure rate: a 1-in-50 flake needs hundreds of executions to mean
   anything (see `references/classification.md` for the math) — two green
   runs prove nothing. Quote the `N/N runs passed` line in your report.

## How the checker works

- Detects the runner from the repo (pytest, Go, Jest, Vitest — see
  `references/runners.md` for the exact seed/shuffle flags per runner).
- Runs the target N seeded runs (default 50), recording the first failing
  seed, the exact replay command, and the failure rate.
- Exit codes: `0` = all runs passed · `1` = failure reproduced (report
  written) · `2` = usage error / no test runner detected (never guess a
  command).
- `--classify` runs the failing target in isolation to separate
  order-dependent from timing failures.
- `--json` prints a machine-readable summary for CI or MCP use.

## When NOT to use this skill

- The test fails every time (broken, not flaky) — fix it directly.
- The failure needs a live external service or a specific CI-only
  environment to reproduce — say so explicitly and reproduce in that
  environment instead of guessing locally.
- You already have a failing seed and replay command from a previous
  run — reuse it; do not re-run the loop to "be safe" unless the code
  changed since.
