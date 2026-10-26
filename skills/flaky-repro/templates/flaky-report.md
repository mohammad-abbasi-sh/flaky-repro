# Flaky-test report

- **Target:** {target}
- **Runner:** {runner}
- **Runs:** {runs} (seeds {first_seed}–{last_seed})
- **Failures:** {failures}
- **Failure rate:** {rate}
- **Result:** {result}

## Reproduction

- **First failing seed:** {failing_seed}
- **Replay command:** `{replay_command}`
- **Classification hint:** {classification}

## Failing output (last {tail_lines} lines)

```
{tail}
```

## Notes

- A fix is not proven until this exact invocation exits 0 over the full
  run count. Two green runs prove nothing.
- Forbidden as a fix: retries, sleeps, skips, longer timeouts,
  quarantining the test without a tracking issue.
