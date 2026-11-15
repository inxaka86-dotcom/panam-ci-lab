"""Offline local Qwen source-generation through the pinned mini-SWE-agent framework.

Only public synthetic data. The model runs in a separate no-network container;
generated Python code executes in a second, restricted disposable container.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import os
import subprocess
from pathlib import Path

from minisweagent.agents.default import DefaultAgent
from minisweagent.environments.docker import DockerEnvironment

MODEL_SHA = "1d9614638d18024d0fbb36575a15f1302a3adf044df10345688ec4f6e1c4ff32"
TESTS = """cat > /work/test_solution.py <<'PY'
import unittest
from solution import add
class Tests(unittest.TestCase):
    def test_positive(self): self.assertEqual(add(2, 3), 5)
    def test_negative(self): self.assertEqual(add(-4, 3), -1)
    def test_zero(self): self.assertEqual(add(0, 0), 0)
    def test_mixed(self): self.assertEqual(add(-5, -9), -14)
if __name__ == '__main__': unittest.main()
PY"""


class LocalQwenModel:
    def __init__(self, binary_dir: Path, model_file: Path):
        self.binary_dir = binary_dir
        self.model_file = model_file
        self.attempts = 0

    def format_message(self, **kwargs):
        return kwargs

    def get_template_vars(self, **kwargs):
        return {}

    def serialize(self):
        return {"info": {"model_name": "Qwen2.5-Coder-0.5B-Instruct Q4_K_M",
                         "model_sha256": MODEL_SHA}}

    def format_observation_messages(self, message, outputs, template_vars=None):
        return [{"role": "user",
                 "content": f"returncode={x['returncode']}: {x['output'][-900:]}",
                 "extra": {"returncode": x["returncode"], "raw_output": x["output"][-900:]}}
                for x in outputs]

    @staticmethod
    def parse_source(raw: str) -> str | None:
        if "def add(" not in raw:
            return None
        text = raw[raw.index("def add("):].split("<|im_end|>")[0]
        text = text.split("\x60\x60\x60")[0].split("\n\n")[0].strip() + "\n"
        if len(text) > 1200:
            return None
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return None
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            return None
        function = tree.body[0]
        if function.name != "add" or len(function.args.args) != 2:
            return None
        if function.decorator_list or len(function.body) > 5:
            return None
        forbidden = (ast.Import, ast.ImportFrom, ast.Call, ast.Attribute,
                     ast.Global, ast.Nonlocal, ast.ClassDef, ast.With, ast.AsyncWith)
        if any(isinstance(n, forbidden) for n in ast.walk(tree)):
            return None
        return text

    def run_inference(self, feedback: str) -> str:
        prompt = (
            "<|im_start|>system\n"
            "You are a precise Python developer. Output ONLY Python source code "
            "for one function. No markdown, explanation, imports, tests or examples.\n"
            "<|im_end|>\n<|im_start|>user\n"
            "Implement def add(a: int, b: int) -> int using a single return "
            "statement that returns arithmetic sum for positive and negative inputs.\n"
            f"Test feedback if previous attempt failed: {feedback[:500]}\n"
            "<|im_end|>\n<|im_start|>assistant\n"
        )
        cmd = [
            "docker", "run", "--rm", "--network=none", "--ipc=none", "--read-only",
            "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
            "--memory=2g", "--cpus=2", "--user=65532:65532",
            "--tmpfs=/tmp:rw,nosuid,nodev,size=32m",
            "--mount", f"type=bind,source={self.binary_dir},target=/opt/llama,readonly",
            "--mount", f"type=bind,source={self.model_file},target=/model/model.gguf,readonly",
            "--env", "LD_LIBRARY_PATH=/opt/llama",
            "panam-public-llama-runtime:research",
            "/opt/llama/llama-cli", "-m", "/model/model.gguf", "-p", prompt,
            "-n", "180", "--temp", "0", "-c", "1024", "-t", "2",
            "--no-display-prompt", "--simple-io",
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=140, check=False)
        if r.returncode != 0:
            raise RuntimeError("model execution failed: " + r.stderr[-1000:])
        print(f"LOCAL_INFERENCE_OUTPUT_CHARS={len(r.stdout)}")
        return r.stdout

    def query(self, messages, **kwargs):
        last = messages[-1]
        meta = last.get("extra", {})
        if meta.get("returncode") == 0 and "OK" in meta.get("raw_output", ""):
            return {"role": "assistant", "content": "submit", "extra": {
                "cost": 0.0, "actions": [
                    {"command": "printf 'COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\\nLOCAL_MODEL_CODE=PASS\\n'"}
                ]}}
        self.attempts += 1
        if self.attempts > 3:
            return {"role": "assistant", "content": "limit", "extra": {
                "cost": 0.0, "actions": [{"command": "echo MODEL_CAPABILITY=NOT_READY; exit 2"}]}}
        output = self.run_inference(last.get("content", ""))
        source = self.parse_source(output)
        if source is None:
            print(f"MODEL_SOURCE_PARSE=FAIL attempt={self.attempts}")
            return {"role": "assistant", "content": "invalid model output", "extra": {
                "cost": 0.0, "actions": [{"command": "echo MODEL_OUTPUT_INVALID; exit 3"}]}}
        digest = hashlib.sha256(source.encode()).hexdigest()
        print(f"MODEL_SOURCE_PARSE=PASS attempt={self.attempts} sha256={digest}")
        encoded = base64.b64encode(source.encode()).decode()
        action = ("python3 -c 'import base64,pathlib; "
                  f'pathlib.Path("/work/solution.py").write_bytes(base64.b64decode("{encoded}"))'
                  "' && python3 -B -m unittest -v test_solution.py")
        return {"role": "assistant", "content": "generated source test", "extra": {
            "cost": 0.0, "actions": [{"command": action}]}}


def main() -> None:
    model_file = Path(os.environ["PANAM_MODEL_FILE"]).resolve(strict=True)
    binary_dir = Path(os.environ["PANAM_LLAMA_BIN_DIR"]).resolve(strict=True)
    assert hashlib.sha256(model_file.read_bytes()).hexdigest() == MODEL_SHA
    env = DockerEnvironment(
        image=os.environ["PANAM_SYNTHETIC_IMAGE"], cwd="/work",
        timeout=20, container_timeout="10m",
        run_args=["--rm", "--network=none", "--ipc=none", "--read-only",
                  "--cap-drop=ALL", "--security-opt=no-new-privileges",
                  "--pids-limit=48", "--memory=256m", "--cpus=1",
                  "--user=65532:65532",
                  "--tmpfs=/work:rw,nosuid,nodev,size=32m,uid=65532,gid=65532",
                  "--tmpfs=/tmp:rw,nosuid,nodev,size=16m"],
    )
    try:
        assert env.execute({"command": TESTS})["returncode"] == 0
        model = LocalQwenModel(binary_dir, model_file)
        agent = DefaultAgent(
            model, env, system_template="Only public synthetic generated Python.",
            instance_template="Task: {{ task }}",
            step_limit=7, wall_time_limit_seconds=500, cost_limit=0,
        )
        result = agent.run("Implement pure addition function from task.")
        checks = [m.get("extra", {}) for m in agent.messages
                  if m["role"] == "user" and "returncode" in m.get("extra", {})]
        passed = any(x["returncode"] == 0 and "OK" in x["raw_output"] for x in checks)
        if result.get("exit_status") != "Submitted" or not passed or model.attempts > 3:
            print("LOCAL_MODEL_CODE=NOT_READY")
            raise AssertionError(f"local model task not passed, attempts={model.attempts}")
        print("LOCAL_MODEL_CODE=PASS")
        print(f"LOCAL_MODEL_INFERENCE_CALLS={model.attempts}")
        print("SYNTHETIC_TESTS=4")
        print("PAID_MODEL_API_CALLS=0")
        print("PRIVATE_CODE_ACCESS=NO")
        print("PRODUCTION_ACCESS=NO")
    finally:
        if env.container_id:
            subprocess.run(["docker", "rm", "-f", env.container_id],
                           capture_output=True, text=True, timeout=30)


if __name__ == "__main__":
    main()
