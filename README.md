# flaky-repro

**Fail on demand, then prove the fix.** An Agent Skill + deterministic
checker for flaky tests — the kind that pass locally, fail in CI, and
get "fixed" by an agent that ran them twice and saw green.

## The problem

Agents routinely "fix" flaky tests without ever seeing them fail: they
run the test twice, get green, and report it fixed. Two green runs are
exactly what the broken version produces most of the time. The agent
proved nothing — and the test fails again next week.

The math, from [this article](https://dev.to/gabrielanhaia/flaky-tests-are-not-a-ci-problem-they-are-an-agent-problem-4akf)
(17 Oct 2026): a test that fails 1 run in 1,000 still passes 500
executions about 61% of the time. Two green runs prove nothing, at any
failure rate.

## The contract

1. **Reproduce first.** Run the checker until it produces a failing
   seed and an exact replay command. No fix without a failing seed.
2. **Record the evidence.** The checker writes `flaky-report.md`:
   target, runner, runs, seeds tried, first failing seed + replay
   command, failure rate, classification hint.
3. **Classify before fixing** — order-dependent, timing, or shared
   state. Each has its own fix direction (see
   `skills/flaky-repro/references/classification.md`).
4. **Forbidden fixes:** retries, `sleep()`, skips, longer timeouts,
   quarantining the test without a tracking issue.
5. **Prove the fix.** Run the *same* checker invocation that reproduced
   the failure. It must exit 0 over the full run count. Required runs
   follow the measured failure rate (≈ 5 / rate: a 1-in-50 flake needs
   ~250 runs; a 1-in-1,000 flake needs ~5,000).

## Quick start

```bash
# Reproduce: run the target 50 seeded times (default)
python3 skills/flaky-repro/scripts/flaky_check.py tests/test_api.py

# FAILURE REPRODUCED — first failing seed: 3
# Replay command: PYTHONHASHSEED=3 python -m pytest tests/test_api.py -q

# ... fix the test ...

# Prove it: the same invocation must now exit 0
python3 skills/flaky-repro/scripts/flaky_check.py tests/test_api.py
# 50/50 runs passed — no failure reproduced.
```

Exit codes: `0` = all runs passed · `1` = failure reproduced ·
`2` = usage error / no runner detected (never guesses a command).

## Supported runners

| Runner | Seed mechanism |
| ------ | -------------- |
| pytest | `PYTHONHASHSEED=<seed>` (+ `--randomly-seed` if pytest-randomly is installed) |
| Go | `go test -shuffle=on -count=1` (Go exposes no seed flag — run index is recorded) |
| Jest | `jest --randomize --seed=<seed>` |
| Vitest | `vitest run --sequence.seed=<seed> --sequence.shuffle` |

No runner detected? Pass an explicit command with `--cmd`:
`--cmd "python3 run_tests.py --seed {seed} {target}"` (seed also in
`$FLAKY_SEED`).

## Install

- **Claude Code / Claude.ai:** copy `skills/flaky-repro/` into your
  skills directory, or use the zip in `dist/` (extract it there).
- **Cursor:** copy `cursor/flaky-repro.mdc` into `.cursor/rules/`
  (see `cursor/README.md`).
- **MCP:** `mcp-server/flaky_mcp_server.py` is a zero-dependency stdio
  MCP server exposing one tool, `flaky_check` (see `mcp-server/`).

## How this differs from existing flaky-test tools

Existing small tools in this lane are detectors and analyzers: they run
tests repeatedly or scan code and report *that* a test looks flaky.
None of them record a failing seed, give you an exact replay command,
enforce "no fix without a failing seed", or prove the fix with a seeded
stress run. That reproduce-first contract is what this skill adds.
The lane is fragmented, not empty — this is the best-in-lane entry, not
the first tool to touch flaky tests.

## Tests

```bash
python3 -m unittest discover -s tests
```

13 checker tests (fake-command fixtures for determinism, plus real
pytest end-to-end tests that run when pytest is installed) and 3 MCP
server end-to-end tests — all passing.

## Layout

```
skills/flaky-repro/
  SKILL.md                     the skill: the contract
  scripts/flaky_check.py       the checker (stdlib only)
  references/runners.md        per-runner seed/shuffle flags
  references/classification.md failure classes + the run-count math
  templates/flaky-report.md    report template
cursor/flaky-repro.mdc         Cursor rule (condensed contract)
mcp-server/flaky_mcp_server.py MCP server (one tool: flaky_check)
tests/                         checker + MCP tests, deterministic fixtures
dist/flaky-repro-skill.zip     packaged skill
```

## License

MIT — see `LICENSE`.
