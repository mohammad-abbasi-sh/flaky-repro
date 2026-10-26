# Cursor — flaky-repro rule

`cursor/flaky-repro.mdc` is the Cursor version of this skill. It carries
the same contract in condensed form: reproduce first with a recorded
seed, classify, never use a forbidden fix, prove the fix with the same
seeded stress run.

## Install

Copy `cursor/flaky-repro.mdc` into your project's `.cursor/rules/`
directory (create it if needed). Cursor applies it automatically to
matching test files (`test_*.py`, `*_test.go`, `*.test.js/ts`, ...).
The rule points at the checker script — copy the whole
`skills/flaky-repro/` directory into your project, or install the
checker where the rule's commands can find it.

## What it covers

- The reproduce-first contract (no fix without a failing seed).
- The forbidden-fix list (retries, sleeps, skips, longer timeouts,
  quarantining without a tracking issue).
- The proof rule (same invocation, full run count, exit 0).
- Per-runner seed flags (pytest / Go / Jest / Vitest).

The full skill with references and the MCP server lives in
`skills/flaky-repro/` and `mcp-server/`.
