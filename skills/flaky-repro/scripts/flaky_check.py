#!/usr/bin/env python3
"""flaky_check — reproduce a flaky test on demand, then prove the fix.

Zero-dependency (Python standard library only).

Contract: no fix without a failing seed, no "done" without a passing
stress run. The tool runs a test target N times with different seeds,
records the first failing seed and the exact replay command, writes a
report, and exits non-zero until the same invocation passes in full.

Exit codes:
    0  all runs passed (N/N)
    1  failure reproduced — see the report for the replay command
    2  usage error / no test runner detected (never guesses a command)

Seed mechanism per runner (see references/runners.md):
    pytest  PYTHONHASHSEED=<seed> (+ --randomly-seed if pytest-randomly
            is installed) — shuffles hash order, which is what makes
            order-dependent tests flip.
    go      go test -shuffle=on -count=1 (Go exposes no seed flag;
            the run index is recorded instead).
    jest    jest --randomize --seed=<seed>
    vitest  vitest run --sequence.seed=<seed> --sequence.shuffle

Usage:
    python3 flaky_check.py <target> [--runs N] [--seed S]
                             [--cmd "..."] [--report PATH] [--json]
                             [--classify] [--timeout SECS]

    <target>  test file, directory, or test id, e.g.
              tests/test_api.py, tests/test_api.py::test_login, ./...
    --cmd     custom test command instead of runner detection.
              Use {seed} and {target} placeholders, e.g.
              --cmd "python3 run_tests.py --seed {seed} {target}"
              The seed is also exported as FLAKY_SEED.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_RUNS = 50
TAIL_LINES = 40


# --------------------------------------------------------------------------
# Runner detection
# --------------------------------------------------------------------------

def detect_runner(root: Path):
    """Detect the test runner from repo files. Returns (name, kind) or None.

    Priority: pytest > go > vitest > jest. Vitest is checked before jest
    because a repo can have both and vitest is the one actually run.
    """
    if (root / "pytest.ini").exists():
        return ("pytest", "pytest")
    setup_cfg = root / "setup.cfg"
    if setup_cfg.exists() and "[tool:pytest]" in setup_cfg.read_text(
            encoding="utf-8", errors="replace"):
        return ("pytest", "pytest")
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = pyproject.read_text(encoding="utf-8", errors="replace")
        if "[tool.pytest" in text or '"pytest"' in text or "'pytest'" in text:
            return ("pytest", "pytest")
    tests_dir = root / "tests"
    if tests_dir.is_dir() and any(tests_dir.glob("test_*.py")):
        return ("pytest", "pytest")
    if any(root.glob("test_*.py")):
        return ("pytest", "pytest")
    if (root / "go.mod").exists():
        return ("go", "go")
    package_json = root / "package.json"
    if package_json.exists():
        try:
            pkg = json.loads(package_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "vitest" in deps:
            return ("vitest", "vitest")
        if "jest" in deps:
            return ("jest", "jest")
    return None


def pytest_randomly_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("pytest_randomly") is not None
    except Exception:
        return False


def build_command(runner, target, seed):
    """Return (argv, extra_env) for one seeded run."""
    if runner == "pytest":
        cmd = [sys.executable, "-m", "pytest", target,
               "-q", "-p", "no:cacheprovider"]
        if pytest_randomly_available():
            cmd.append(f"--randomly-seed={seed}")
        return cmd, {"PYTHONHASHSEED": str(seed)}
    if runner == "go":
        return ["go", "test", "-shuffle=on", "-count=1", target], {}
    if runner == "jest":
        return ["npx", "jest", target, "--randomize", f"--seed={seed}"], {}
    if runner == "vitest":
        return ["npx", "vitest", "run", target,
                f"--sequence.seed={seed}", "--sequence.shuffle"], {}
    raise ValueError(f"unknown runner: {runner}")


def format_command(argv):
    """Shell-readable rendering of a command for the report."""
    return " ".join(f'"{a}"' if " " in a else a for a in argv)


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------

def run_once(argv, env, cwd, timeout):
    """Run one seeded attempt. Returns (returncode, tail_text, elapsed)."""
    full_env = dict(os.environ)
    full_env.update(env)
    start = time.monotonic()
    try:
        proc = subprocess.run(
            argv, env=full_env, cwd=str(cwd), capture_output=True,
            text=True, timeout=timeout)
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, "\n".join(out.splitlines()[-TAIL_LINES:]), \
            time.monotonic() - start
    except subprocess.TimeoutExpired as exc:
        out = ((exc.stdout or b"").decode("utf-8", "replace")
               if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
        out += ((exc.stderr or b"").decode("utf-8", "replace")
                if isinstance(exc.stderr, bytes) else (exc.stderr or ""))
        return 124, "\n".join(out.splitlines()[-TAIL_LINES:]), \
            time.monotonic() - start
    except FileNotFoundError as exc:
        return 127, f"command not found: {exc.filename}", 0.0


def target_exists(root: Path, target: str) -> bool:
    """Check the file part of a target (before any ::test id) exists."""
    file_part = target.split("::")[0]
    if not file_part or file_part in (".", "./..."):
        return True
    return (root / file_part).exists()


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

REPORT_TEMPLATE = """# Flaky-test report

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
"""


def write_report(path: Path, context: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(REPORT_TEMPLATE.format(**context), encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="flaky_check.py",
        description="Reproduce a flaky test on demand, then prove the fix.")
    parser.add_argument("target", help="test file, directory, or test id")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help=f"seeded runs to attempt (default {DEFAULT_RUNS})")
    parser.add_argument("--seed", type=int, default=0,
                        help="first seed (default 0)")
    parser.add_argument("--cmd", default=None,
                        help='custom test command with {seed} and {target} '
                             'placeholders; seed is also in $FLAKY_SEED')
    parser.add_argument("--report", default="flaky-report.md",
                        help="report path (default flaky-report.md)")
    parser.add_argument("--json", action="store_true",
                        help="print a machine-readable summary as JSON")
    parser.add_argument("--classify", action="store_true",
                        help="after a failure, re-run the failing test in "
                             "isolation once to separate order-dependent "
                             "from timing failures")
    parser.add_argument("--timeout", type=int, default=300,
                        help="seconds per run (default 300)")
    return parser.parse_args(argv)


FAILED_RE = re.compile(r"FAILED\s+(\S+::\S+)")


def classify_failure(runner, target, seed, cwd, timeout, tail="",
                     passed_seeds=None):
    """Isolation re-runs to separate order-dependent from timing.

    Step 1: re-run the failing test alone with the same seed. If it
    passes, the failure needs the suite — order-dependent (test
    pollution / shared state).
    Step 2: if it still fails, re-run it alone with a seed that PASSED
    in the main loop. If it passes now, the failure is seed-dependent
    (hash/iteration order or randomness) — order-dependent of a
    different kind. If it fails with the passing seed too, the seed
    does not matter for this test.
    Step 3: if it fails in isolation under every seed tried, it is
    timing or shared-state (races, sleeps, timeouts, leaked state).

    `passed_seeds` comes from the main loop — reusing observed passing
    seeds instead of guessing offsets, which would miss sparse passing
    seeds (a hash-order flake can pass on only 3 of 30 seeds).

    For pytest, the failing test id is parsed from the failure output
    and re-run alone. Returns a hint string — never a verdict; the
    agent still has to read the failure.
    """
    isolated = target
    if runner == "pytest":
        match = FAILED_RE.search(tail or "")
        if match:
            isolated = match.group(1)
    argv, env = build_command(runner, isolated, seed)
    rc, _, _ = run_once(argv, env, cwd, timeout)
    if rc == 0:
        return ("order-dependent (passes alone with the same seed, "
                "fails in the suite — suspect shared state / test "
                "pollution)")
    for good_seed in (passed_seeds or []):
        argv2, env2 = build_command(runner, isolated, good_seed)
        rc2, _, _ = run_once(argv2, env2, cwd, timeout)
        if rc2 == 0:
            return ("order-dependent (seed-dependent: fails with seed "
                    f"{seed}, passes alone with seed {good_seed} — "
                    "suspect hash/iteration order or unseeded "
                    "randomness)")
    return ("timing or shared-state (fails in isolation under every "
            "seed tried — suspect races, sleeps, timeouts, or leaked "
            "state)")


def main(argv=None):
    args = parse_args(argv)
    root = Path.cwd()

    if args.runs < 1:
        print("error: --runs must be at least 1", file=sys.stderr)
        return 2

    runner = "custom"
    if args.cmd is None:
        detected = detect_runner(root)
        if detected is None:
            print("error: no test runner detected in this directory "
                  "(looked for pytest, go, jest, vitest). Pass an explicit "
                  "command with --cmd.", file=sys.stderr)
            return 2
        runner, _ = detected
        if not target_exists(root, args.target):
            print(f"error: target not found: {args.target}",
                  file=sys.stderr)
            return 2

    failures = 0
    passed_seeds = []
    first_failing = None  # (seed, command, tail)

    for i in range(args.runs):
        seed = args.seed + i
        if args.cmd is not None:
            cmd_str = args.cmd.format(seed=seed, target=args.target)
            argv = cmd_str.split()
            env = {"FLAKY_SEED": str(seed)}
            display_cmd = cmd_str
        else:
            argv, env = build_command(runner, args.target, seed)
            display_cmd = format_command(argv)
        rc, tail, _ = run_once(argv, env, root, args.timeout)
        if rc != 0:
            failures += 1
            if first_failing is None:
                first_failing = (seed, display_cmd, tail)
        else:
            passed_seeds.append(seed)

    total = args.runs
    rate = f"{failures}/{total} ({100.0 * failures / total:.1f}%)"

    if first_failing is None:
        result = "PASS"
        classification = "n/a — no failure reproduced"
        context = {
            "target": args.target, "runner": runner, "runs": total,
            "first_seed": args.seed, "last_seed": args.seed + total - 1,
            "failures": 0, "rate": rate, "result": f"PASS ({total}/{total} runs passed)",
            "failing_seed": "n/a", "replay_command": "n/a",
            "classification": classification, "tail_lines": TAIL_LINES,
            "tail": "(no failures)",
        }
        write_report(Path(args.report), context)
        if args.json:
            print(json.dumps({
                "target": args.target, "runner": runner, "runs": total,
                "failures": 0, "failure_rate": 0.0,
                "first_failing_seed": None, "replay_command": None,
                "classification": None, "report": str(args.report),
            }, indent=2))
        else:
            print(f"{total}/{total} runs passed — no failure reproduced.")
            print(f"Report: {args.report}")
        return 0

    seed, display_cmd, tail = first_failing
    if args.cmd is not None:
        classification = ("custom command — re-run the replay command by "
                          "hand to confirm, then classify with "
                          "references/classification.md")
    elif args.classify:
        classification = classify_failure(runner, args.target, seed, root,
                                          args.timeout, tail, passed_seeds)
    else:
        classification = ("not classified — re-run with --classify, or "
                          "run the replay command in isolation by hand")

    context = {
        "target": args.target, "runner": runner, "runs": total,
        "first_seed": args.seed, "last_seed": args.seed + total - 1,
        "failures": failures, "rate": rate,
        "result": f"FAIL — failure reproduced (first failing seed {seed})",
        "failing_seed": seed, "replay_command": display_cmd,
        "classification": classification, "tail_lines": TAIL_LINES,
        "tail": tail,
    }
    write_report(Path(args.report), context)
    if args.json:
        print(json.dumps({
            "target": args.target, "runner": runner, "runs": total,
            "failures": failures, "failure_rate": failures / total,
            "first_failing_seed": seed, "replay_command": display_cmd,
            "classification": classification, "report": str(args.report),
        }, indent=2))
    else:
        print(f"FAILURE REPRODUCED — first failing seed: {seed}")
        print(f"Replay command: {display_cmd}")
        print(f"Failure rate so far: {rate}")
        print(f"Classification: {classification}")
        print(f"Report: {args.report}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
