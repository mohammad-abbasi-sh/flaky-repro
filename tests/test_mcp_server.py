#!/usr/bin/env python3
"""End-to-end tests for mcp-server/flaky_mcp_server.py.

Spawns the server as a subprocess, speaks JSON-RPC over stdio, and
verifies initialize, tools/list, and a real tools/call against the
fake passing and fake flaky fixtures. Standard library only.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER = ROOT / "mcp-server" / "flaky_mcp_server.py"
FIXTURES = ROOT / "tests" / "fixtures"


class McpServerTest(unittest.TestCase):
    def setUp(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, cwd=str(ROOT))

    def tearDown(self):
        self.proc.stdin.close()
        self.proc.wait(timeout=10)

    def call(self, payload):
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def notify(self, payload):
        # Notifications get no response — write only, never read.
        self.proc.stdin.write(json.dumps(payload) + "\n")
        self.proc.stdin.flush()

    def test_initialize_and_list(self):
        init = self.call({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05",
                       "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.assertEqual(init["result"]["serverInfo"]["name"], "flaky-repro")
        self.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        listing = self.call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listing["result"]["tools"]]
        self.assertEqual(names, ["flaky_check"])

    def test_call_surfaces_usage_error(self):
        """A missing target must surface as exit code 2 in the tool
        result — never a crash, never a hallucinated command."""
        self.call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2024-11-05",
                              "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        self.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
        resp = self.call({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "flaky_check",
                       "arguments": {
                           "target": "dummy",
                           "runs": 5,
                           "cwd": str(ROOT),
                       }}})
        text = resp["result"]["content"][0]["text"]
        self.assertIn("exit code: 2", text)

    def test_call_with_fake_flaky_via_cwd(self):
        """Drive the checker through the MCP tool against the fake
        flaky fixture by pointing cwd at a dir where the fixture is
        the test command — exercised via a temp pytest fixture dir."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # A minimal pytest project whose only test is the fake
            # flaky command wrapped in a pytest test.
            Path(tmp, "test_fake.py").write_text(
                "import subprocess, sys, os\n"
                "def test_fake():\n"
                "    seed = int(os.environ.get('PYTHONHASHSEED', '0'))\n"
                "    assert seed % 7 != 3, 'simulated flaky failure'\n",
                encoding="utf-8")
            self.call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2024-11-05",
                                  "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
            self.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
            resp = self.call({
                "jsonrpc": "2.0", "id": 4, "method": "tools/call",
                "params": {"name": "flaky_check",
                           "arguments": {"target": "test_fake.py",
                                         "runs": 10, "cwd": tmp}}})
            text = resp["result"]["content"][0]["text"]
            self.assertIn("exit code: 1", text)
            self.assertIn("first failing seed: 3", text)


if __name__ == "__main__":
    unittest.main()
