#!/usr/bin/env python3
"""MCP server for flaky-repro — expose the flaky-test checker as a tool.

Zero-dependency (Python standard library only). Speaks JSON-RPC 2.0
over stdio, newline-delimited, following the MCP lifecycle:

    initialize -> notifications/initialized -> tools/list -> tools/call

Tool:
    flaky_check
        target    test file, directory, or test id (required)
        runs      seeded runs to attempt (default 50)
        seed      first seed (default 0)
        classify  run the isolation classifier after a failure (bool)
        timeout   seconds per run (default 300)
        cwd       working directory of the repo under test
                  (default: this server's directory)

The tool runs skills/flaky-repro/scripts/flaky_check.py as a subprocess
and returns its summary plus the report path. Exit-code semantics are
preserved in the returned text (0 = all passed, 1 = reproduced,
2 = usage error).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKER = HERE.parent / "skills" / "flaky-repro" / "scripts" / "flaky_check.py"

SERVER_INFO = {"name": "flaky-repro", "version": "0.1.0"}
PROTOCOL_VERSION = "2024-11-05"


def run_checker(args):
    target = args.get("target")
    if not target:
        raise ValueError("flaky_check requires 'target'")
    cmd = [sys.executable, str(CHECKER), target]
    runs = args.get("runs", 50)
    cmd += ["--runs", str(runs)]
    cmd += ["--seed", str(args.get("seed", 0))]
    if args.get("classify"):
        cmd.append("--classify")
    cmd += ["--timeout", str(args.get("timeout", 300))]
    cmd += ["--json"]
    cwd = args.get("cwd") or str(HERE.parent)
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          timeout=3600)
    try:
        summary = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except json.JSONDecodeError:
        summary = {}
    lines = [f"flaky_check exit code: {proc.returncode}"]
    if summary:
        lines.append(f"target: {summary.get('target')}")
        lines.append(f"runner: {summary.get('runner')}")
        runs_done = summary.get("runs")
        failures = summary.get("failures")
        lines.append(f"runs: {runs_done}, failures: {failures}")
        seed = summary.get("first_failing_seed")
        if seed is not None:
            lines.append(f"first failing seed: {seed}")
            lines.append(f"replay command: {summary.get('replay_command')}")
        lines.append(f"classification: {summary.get('classification')}")
        lines.append(f"report: {summary.get('report')}")
    if proc.stderr.strip():
        lines.append("stderr:")
        lines.append(proc.stderr.strip())
    return "\n".join(lines)


TOOLS = [
    {
        "name": "flaky_check",
        "description": (
            "Reproduce a flaky test on demand with a recorded seed and "
            "replay command, then prove the fix with a seeded stress run. "
            "Runs the test target N times with different seeds; returns "
            "the first failing seed, the exact replay command, the "
            "failure rate, and a classification hint. Exit 0 in the "
            "returned text means all runs passed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "test file, directory, or test id",
                },
                "runs": {
                    "type": "integer",
                    "description": "seeded runs to attempt (default 50)",
                },
                "seed": {
                    "type": "integer",
                    "description": "first seed (default 0)",
                },
                "classify": {
                    "type": "boolean",
                    "description": "classify the failure after reproducing",
                },
                "timeout": {
                    "type": "integer",
                    "description": "seconds per run (default 300)",
                },
                "cwd": {
                    "type": "string",
                    "description": "repo directory under test",
                },
            },
            "required": ["target"],
        },
    }
]


def handle(request):
    method = request.get("method", "")
    req_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {"tools": TOOLS},
        }
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name != "flaky_check":
            return {
                "jsonrpc": "2.0", "id": req_id,
                "error": {"code": -32602,
                          "message": f"unknown tool: {name}"},
            }
        try:
            text = run_checker(arguments)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        except Exception as exc:  # noqa: BLE001 - surface as tool error
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text",
                                        "text": f"error: {exc}"}],
                           "isError": True},
            }
    return {
        "jsonrpc": "2.0", "id": req_id,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
