#!/usr/bin/env python3
"""Tests for skills/flaky-repro/scripts/flaky_check.py.

Standard library only (unittest). The core behaviour is exercised with
deterministic fake test commands (tests/fixtures/fake_*.py) so the suite
is stable; the real-pytest end-to-end tests run only when pytest is
installed (skipped otherwise).
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "skills" / "flaky-repro" / "scripts"))

import flaky_check  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "flaky-repro" / "scripts" / "flaky_check.py"
FIXTURES = ROOT / "tests" / "fixtures"

try:
    import pytest  # noqa: F401
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False


def run_tool(*args, cwd=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd or ROOT), capture_output=True, text=True, timeout=120)


class TestSeededLoop(unittest.TestCase):
    def test_finds_failing_seed(self):
        """Fake flaky command fails on seeds 3, 10, 17, ... — the tool
        must find seed 3 first, record the replay command, exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            proc = run_tool(
                "dummy-target",
                "--cmd", f"{sys.executable} {FIXTURES}/fake_flaky.py",
                "--runs", "10", "--seed", "0",
                "--report", str(report), "--json")
            self.assertEqual(proc.returncode, 1)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["first_failing_seed"], 3)
            self.assertAlmostEqual(summary["failure_rate"], 0.1)
            self.assertIn("fake_flaky.py", summary["replay_command"])
            text = report.read_text(encoding="utf-8")
            self.assertIn("First failing seed:** 3", text)
            self.assertIn("fake_flaky.py", text)

    def test_passing_fixture_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            proc = run_tool(
                "dummy-target",
                "--cmd", f"{sys.executable} {FIXTURES}/fake_passing.py",
                "--runs", "10", "--report", str(report))
            self.assertEqual(proc.returncode, 0)
            self.assertIn("10/10 runs passed", proc.stdout)
            self.assertIn("10/10 runs passed", report.read_text())

    def test_always_failing_is_not_flaky(self):
        """A test that fails every run reports a 100% rate — the tool
        must not call it flaky, and must still exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            proc = run_tool(
                "dummy-target",
                "--cmd", f"{sys.executable} {FIXTURES}/fake_always_fail.py",
                "--runs", "5", "--report", str(report), "--json")
            self.assertEqual(proc.returncode, 1)
            summary = json.loads(proc.stdout)
            self.assertEqual(summary["failures"], 5)
            self.assertAlmostEqual(summary["failure_rate"], 1.0)

    def test_no_runner_detected(self):
        """An empty directory with no --cmd must fail with exit 2 and a
        clear message — never a hallucinated command."""
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_tool("tests/test_x.py", "--runs", "2", cwd=tmp)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("no test runner detected", proc.stderr)


class TestRunnerDetection(unittest.TestCase):
    def _detect(self, files):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, content in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            return flaky_check.detect_runner(root)

    def test_pytest_ini(self):
        self.assertEqual(
            self._detect({"pytest.ini": "[pytest]\n"}), ("pytest", "pytest"))

    def test_go_mod(self):
        self.assertEqual(
            self._detect({"go.mod": "module example.com/x\n"}), ("go", "go"))

    def test_vitest_before_jest(self):
        pkg = '{"devDependencies": {"vitest": "^3.0.0", "jest": "^29.0.0"}}'
        self.assertEqual(
            self._detect({"package.json": pkg}), ("vitest", "vitest"))

    def test_jest(self):
        pkg = '{"devDependencies": {"jest": "^29.0.0"}}'
        self.assertEqual(
            self._detect({"package.json": pkg}), ("jest", "jest"))

    def test_none(self):
        self.assertIsNone(self._detect({"README.md": "# hi\n"}))


@unittest.skipUnless(HAS_PYTEST, "pytest not installed")
class TestRealPytestEndToEnd(unittest.TestCase):
    def test_order_dependent_fixture_fails_on_some_seed(self):
        """The set-order fixture must fail for some PYTHONHASHSEED in
        30 runs — the tool finds a failing seed and writes a replay
        command that fails when run by hand."""
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            fixture = FIXTURES / "order-dependent" / "test_order.py"
            proc = run_tool(str(fixture), "--runs", "30",
                            "--report", str(report), "--json",
                            cwd=FIXTURES / "order-dependent")
            self.assertEqual(proc.returncode, 1)
            summary = json.loads(proc.stdout)
            self.assertIsNotNone(summary["first_failing_seed"])
            replay = summary["replay_command"]
            # The replay command must actually fail when run by hand.
            check = subprocess.run(
                replay.split(), cwd=str(FIXTURES / "order-dependent"),
                capture_output=True, text=True, timeout=120,
                env={**__import__("os").environ,
                     "PYTHONHASHSEED": str(summary["first_failing_seed"])})
            self.assertNotEqual(check.returncode, 0)

    def test_order_dependent_classifies(self):
        """With --classify, the set-order fixture must be reported as
        order-dependent (it passes alone with the same seed)."""
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            fixture = FIXTURES / "order-dependent" / "test_order.py"
            proc = run_tool(str(fixture), "--runs", "30", "--classify",
                            "--report", str(report), "--json",
                            cwd=FIXTURES / "order-dependent")
            self.assertEqual(proc.returncode, 1)
            summary = json.loads(proc.stdout)
            self.assertIn("order-dependent", summary["classification"])

    def test_fixed_fixture_passes(self):
        """The same invocation that failed on test_order.py must exit 0
        on the fixed version — the proof loop closes."""
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            fixture = FIXTURES / "order-dependent" / "test_order_fixed.py"
            proc = run_tool(str(fixture), "--runs", "30",
                            "--report", str(report),
                            cwd=FIXTURES / "order-dependent")
            self.assertEqual(proc.returncode, 0)
            self.assertIn("30/30 runs passed", proc.stdout)

    def test_passing_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "flaky-report.md"
            fixture = FIXTURES / "passing" / "test_ok.py"
            proc = run_tool(str(fixture), "--runs", "10",
                            "--report", str(report),
                            cwd=FIXTURES / "passing")
            self.assertEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
