"""Public-only synthetic Harness² A/B: scripted recursion, no model credentials.

The upstream Harness² scheduler is exercised; the improver is a deterministic
editor, NOT an LLM. The evaluation oracle never enters a task source directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

from harness2.core import tree
from harness2.core.proposer import Reply
from harness2.core.schedule import run_domain
from harness2.core.spec import BenchPrompts
from harness2.demo import DemoAdapter, DemoProposer

# All texts are invented for this experiment, not citations of law or a tender.
CASES = {
    "legal": {
        "legal-01": (
            ("L1|Вымышленный заявитель обязан направить уведомление.", "L1", "REQUIRED"),
            ("L2|Вымышленный заявитель не обязан направлять копию.", "L2", "NOT_REQUIRED"),
            ("L3|Срок указан в отдельной таблице.", "L3", "UNKNOWN"),
        ),
        "legal-02": (
            ("L4|По учебному правилу исполнитель не обязан приложить письмо.", "L4", "NOT_REQUIRED"),
            ("L5|По учебному правилу исполнитель обязан указать номер.", "L5", "REQUIRED"),
            ("L6|Порядок описан в разделе три.", "L6", "UNKNOWN"),
        ),
    },
    "tender": {
        "tender-01": (
            ("T1|Для условной заявки требуется форма А.", "T1", "REQUIRED"),
            ("T2|Для условной заявки не требуется форма Б.", "T2", "NOT_REQUIRED"),
            ("T3|Цена указана в приложении.", "T3", "UNKNOWN"),
        ),
        "tender-02": (
            ("T4|Для учебной заявки не требуется образец.", "T4", "NOT_REQUIRED"),
            ("T5|Для учебной заявки требуется подпись.", "T5", "REQUIRED"),
            ("T6|Результат рассматривает комиссия.", "T6", "UNKNOWN"),
        ),
    },
}

SCRIPT = '''from pathlib import Path
import sys

MARKER = "CHANGE_ME"
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    identifier, statement = raw.split("|", 1)
    normalized = statement.casefold().strip()
    label = "REQUIRED" if MARKER in normalized else "UNKNOWN"
    print(f"{identifier}={label}")
'''

OLD_RULE = 'label = "REQUIRED" if MARKER in normalized else "UNKNOWN"'
NEW_RULE = (
    'label = "NOT_REQUIRED" if ("не " + MARKER) in normalized '
    'else ("REQUIRED" if MARKER in normalized else "UNKNOWN")'
)


class SyntheticAdapter(DemoAdapter):
    def __init__(self, root: Path, domain: str):
        super().__init__(root)
        self.domain = domain
        self.spec = replace(
            self.spec,
            name=f"panam-synthetic-{domain}",
            prompts=BenchPrompts(work="classify explicitly stated synthetic requirements"),
        )
        marker = "обязан" if domain == "legal" else "требуется"
        initial = {
            name: "" for name in self.substrate.surface().always_on
        }
        initial["systemprompt.md"] = (
            "Classify the lines in clauses.txt using python scripts/summarize.py.\n"
        )
        initial["scripts/summarize.py"] = SCRIPT.replace("CHANGE_ME", marker)
        tree.write_tree(self.substrate.surface(), initial, self.base_harness(), stubs=False)
        self.execution_count = 0
        for task_id, rows in CASES[domain].items():
            source = self.task_files(task_id)
            source.mkdir(parents=True, exist_ok=True)
            (source / "clauses.txt").write_text(
                "\n".join(row[0] for row in rows) + "\n", encoding="utf-8"
            )

    def tasks(self, split: str = "all") -> list[str]:
        return sorted(CASES[self.domain])

    def domain_of(self, task_id: str) -> str:
        return self.domain

    def task_prompt(self, task_id: str) -> str:
        return "Classify each line as REQUIRED, NOT_REQUIRED or UNKNOWN."

    def execute(
        self, task_id: str, harness_dir: Path | None, run_id: str, *, timeout: int | None = None
    ) -> Path:
        self.execution_count += 1
        run_dir = self.root / "executions" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        script = (harness_dir or self.base_harness()) / "scripts/summarize.py"
        result = subprocess.run(
            [sys.executable, str(script), str(self.task_files(task_id) / "clauses.txt")],
            capture_output=True, text=True, check=True, timeout=min(timeout or 10, 10),
        )
        (run_dir / "answer.txt").write_text(result.stdout, encoding="utf-8")
        (run_dir / "trajectory.md").write_text(
            "[ACTION] Classify synthetic statements with summarize.py\n"
            "[OBSERVATION]\n" + result.stdout,
            encoding="utf-8",
        )
        return run_dir


class ScriptedEditor(DemoProposer):
    """Proposes a fixed, human-authored source patch; never reads gold labels."""

    def call(self, mission, context_dir, label, **kwargs) -> Reply:
        context = Path(context_dir)
        if label.startswith("select."):
            raise ValueError("k=1 has exactly one final, so no selector call is expected")
        if label.startswith("experience."):
            reply = Reply(label=label, text="NO_ENTRY", ok=True, attempts=1)
        else:
            workspace = context / "harness"
            path = workspace / "scripts/summarize.py"
            before = path.read_text(encoding="utf-8")
            after = before.replace(OLD_RULE, NEW_RULE)
            # A changed rule is expected for every initial proposal, while
            # subsequent Compose stages may already inherit the improvement.
            if OLD_RULE in before and after == before:
                raise AssertionError("Expected the classification patch to modify the script")
            path.write_text(after, encoding="utf-8")
            reply = Reply(
                label=label,
                text="<notes>Distinguish an explicit negation from an obligation.</notes>",
                ok=True, attempts=1, workspace=workspace,
            )
        self._calls.append(reply)
        return reply


def parse_predictions(path: Path, expected_ids: set[str]) -> dict[str, str]:
    predictions: dict[str, str] = {}
    for row in path.read_text(encoding="utf-8").splitlines():
        if row.count("=") != 1:
            raise ValueError(f"Unparseable output row: {row!r}")
        identifier, value = row.split("=", 1)
        if identifier in predictions or value not in {"REQUIRED", "NOT_REQUIRED", "UNKNOWN"}:
            raise ValueError(f"Duplicate identifier or unknown classification: {row!r}")
        predictions[identifier] = value
    if set(predictions) != expected_ids:
        raise ValueError(
            f"Missing or invented IDs: expected={sorted(expected_ids)}, "
            f"got={sorted(predictions)}"
        )
    return predictions


def score(path: Path, gold: dict[str, str]) -> int:
    predictions = parse_predictions(path, set(gold))
    return sum(predictions[identifier] == truth for identifier, truth in gold.items())


def selftest() -> None:
    """Check a deliberately malformed answer cannot pass or inflate the score."""
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as temp:
        p = Path(temp) / "answer.txt"
        examples = (
            "A=REQUIRED\nA=REQUIRED\n",
            "A=REQUIRED\nEXTRA=UNKNOWN\n",
            "A=BAD\n",
            "A=REQUIRED\nB=REQUIRED\n",
        )
        gold = {"A": "REQUIRED"}
        for bad in examples:
            p.write_text(bad, encoding="utf-8")
            try:
                score(p, gold)
            except ValueError:
                pass
            else:
                raise AssertionError("Malformed prediction passed the scorer")
        p.write_text("A=REQUIRED\n", encoding="utf-8")
        assert score(p, gold) == 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    selftest()
    root = args.output.resolve()
    report: dict = {
        "test_kind": "scripted_synthetic_harness2_integration_ab",
        "k": 1,
        "modes": ["parallel", "sequential"],
        "llm_calls": 0,
        "domains": {},
    }
    for domain in ("legal", "tender"):
        adapter = SyntheticAdapter(root / domain, domain)
        proposer = ScriptedEditor(adapter.spec.channels["proposer"])
        result = run_domain(
            domain, adapter.tasks(), 1,
            adapter=adapter, prop=proposer,
            runs_root=adapter.spec.runs_root,
            library_root=adapter.root / "library",
            modes=("agg", "seq"),
        )
        if result["failed"] or result["done"] != len(CASES[domain]):
            raise AssertionError(f"Recursion failed in {domain}: {result}")

        evaluations = {}
        for task in adapter.tasks():
            location = adapter.spec.runs_root / f"{adapter.spec.name}-oc-agg1" / task / "summary.json"
            data = json.loads(location.read_text(encoding="utf-8"))
            if data["status"] != "ok":
                raise AssertionError(f"Unsuccessful task: {task}")
            gold = {identifier: outcome for _, identifier, outcome in CASES[domain][task]}
            base = Path(data["base"][0]["run_dir"]) / "answer.txt"
            baseline_correct = score(base, gold)
            mode_scores = {}
            for token, name in (("agg", "parallel"), ("seq", "sequential")):
                selected = data["selections"][token]
                if not selected.get("ok") or not selected.get("chosen_run_dir"):
                    raise AssertionError(f"Selection failed: {task}/{name}")
                candidate = Path(selected["chosen_run_dir"]) / "answer.txt"
                refined_correct = score(candidate, gold)
                if refined_correct < baseline_correct:
                    raise AssertionError(f"Regression: {task}/{name}")
                mode_scores[name] = refined_correct
            evaluations[task] = {
                "n_clauses": len(gold),
                "baseline_correct": baseline_correct,
                "refined_correct": mode_scores,
            }
        total = sum(row["n_clauses"] for row in evaluations.values())
        base_correct = sum(row["baseline_correct"] for row in evaluations.values())
        refined = {
            mode: sum(row["refined_correct"][mode] for row in evaluations.values())
            for mode in ("parallel", "sequential")
        }
        if not all(base_correct < v == total for v in refined.values()):
            raise AssertionError(f"Expected synthetic repair not observed: {domain}: {evaluations}")
        report["domains"][domain] = {
            "clauses": total, "baseline_correct": base_correct,
            "refined_correct": refined,
            "tasks": evaluations,
            "execution_count": adapter.execution_count,
            "editor_calls": len(proposer._calls),
        }
    output = root / "panam-harness2-ab.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print("PANAM_HARNESS2_AB=" + json.dumps(report, sort_keys=True, ensure_ascii=False))
    print("PANAM_HARNESS2_REPORT_SHA256=" + digest)
    print("PANAM_HARNESS2_AB=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
