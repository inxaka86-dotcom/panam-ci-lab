"""PANAM autonomous coding agent: isolated one-file proof of concept.

Changes are limited to agent_mvp/coding_lab/buggy.py in a disposable GitHub branch.
The AI API key is available only in the agent invocation step, not the test/commit steps.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from agents import Agent, Runner, function_tool, set_tracing_disabled
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "agent_mvp" / "coding_lab" / "buggy.py"
TEST_DIR = ROOT / "agent_mvp" / "coding_lab"
PROVIDER = "https://aidostup.site/v1"
MODEL = os.environ.get("AGENT_MODEL", "gpt-6-luna")


def _run_unit_tests() -> tuple[bool, str]:
    # Do not inherit AI API keys, GitHub tokens or other job secrets in generated code.
    clean_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(TEST_DIR),
         "-p", "test_priority.py", "-v"],
        cwd=str(ROOT),
        env=clean_env,
        timeout=15,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0, (result.stdout + result.stderr)[-3200:]


@function_tool
def inspect_target() -> str:
    """Read the only source file this agent is permitted to change."""
    print("AI_CODER_TOOL_READ_OK", flush=True)
    return TARGET.read_text(encoding="utf-8")


@function_tool
def replace_target(new_python_code: str) -> str:
    """Overwrite the allowed Python source file with corrected code (no Markdown fences)."""
    if not new_python_code.strip() or len(new_python_code) > 4000:
        return "REJECTED: empty or oversized replacement"
    try:
        parsed = ast.parse(new_python_code)
        functions = [item for item in parsed.body if isinstance(item, ast.FunctionDef)]
        if (len(functions) != 1 or functions[0].name != "priority_bucket"
                or any(not isinstance(item, (ast.FunctionDef, ast.Expr))
                       for item in parsed.body)):
            return "REJECTED: expected one top-level priority_bucket function"
        banned = (ast.Import, ast.ImportFrom, ast.Call, ast.Attribute,
                  ast.Subscript, ast.Lambda, ast.ClassDef, ast.With,
                  ast.AsyncWith, ast.Global, ast.Nonlocal, ast.Try,
                  ast.While, ast.For, ast.AsyncFor, ast.Await)
        if any(isinstance(node, banned) for node in ast.walk(parsed)):
            return "REJECTED: unsafe language construct in submitted code"
        TARGET.write_text(new_python_code.rstrip() + "\n", encoding="utf-8")
        print("AI_CODER_TOOL_WRITE_OK", flush=True)
        return "Saved corrected code to the allowed isolated challenge file"
    except (SyntaxError, OSError, ValueError) as exc:
        return f"REJECTED: {type(exc).__name__}: {exc}"


@function_tool
def run_unit_tests() -> str:
    """Execute deterministic local unit tests on the updated source; return failure details."""
    try:
        passed, result = _run_unit_tests()
        print("AI_CODER_TOOL_TEST_PASS" if passed else "AI_CODER_TOOL_TEST_FAIL", flush=True)
        return ("PASS\n" if passed else "FAIL\n") + result
    except Exception as exc:
        print("AI_CODER_TOOL_TEST_ERROR", flush=True)
        return f"TEST_ERROR: {type(exc).__name__}: {exc}"


def main() -> int:
    key = os.environ.get("AIDOSTUP_API_KEY", "").strip()
    if not key:
        print("FAILED: AIDOSTUP_API_KEY missing", flush=True)
        return 1

    before, details = _run_unit_tests()
    if before:
        print("FAILED: challenge unexpectedly passes before agent", flush=True)
        return 1
    print("AI_CODER_BASELINE_RED", flush=True)

    set_tracing_disabled(True)
    client = AsyncOpenAI(api_key=key, base_url=PROVIDER, timeout=50.0, max_retries=1)
    agent = Agent(
        name="PANAM autonomous programmer - isolated proof of concept",
        model=OpenAIChatCompletionsModel(model=MODEL, openai_client=client),
        instructions=(
            "You are an autonomous Python developer. This is an isolated coding challenge. "
            "Read only the allowed file using inspect_target, repair its boundary logic using "
            "replace_target, run_unit_tests and retry if failing. You MUST actually call tools. "
            "The priority_bucket function must return low for score < 5, medium for 5 <= score < 10, "
            "high for score >= 10. Do not invent test outcomes. Avoid imports and function calls. "
            "Do not modify other files or request network/production access. "
            "When all tests pass, briefly report in Russian exactly what you changed."
        ),
        tools=[inspect_target, replace_target, run_unit_tests],
    )
    result = Runner.run_sync(
        agent,
        "Fix the priority_bucket boundary bug in the allowed Python file and run tests until all green.",
        max_turns=12,
    )
    passed, test_output = _run_unit_tests()
    if not passed:
        print("AI_CODER_FINAL_TEST_FAILED\n" + test_output, flush=True)
        return 1
    print("AI_CODER_FINAL_TEST_PASS", flush=True)
    print("AI_CODER_RESPONSE: " + str(result.final_output or "")[:2500], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
