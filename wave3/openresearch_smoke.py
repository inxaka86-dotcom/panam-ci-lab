#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys

def run(*argv: str) -> str:
    p = subprocess.run(argv, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.stdout.strip()

def require(cond: bool, msg: str) -> None:
    if not cond:
        raise SystemExit(msg)

def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: openresearch_smoke.py <source> <orx> <expected-sha>")
    source = pathlib.Path(sys.argv[1])
    orx = pathlib.Path(sys.argv[2])
    expected_sha = sys.argv[3]

    require(run("git", "-C", str(source), "rev-parse", "HEAD") == expected_sha, "upstream_sha_mismatch")
    require(orx.is_file(), "orx_binary_missing")

    channel = run(str(orx), "--no-telemetry", "version", "--build-channel")
    require(channel == "development", f"unexpected_build_channel:{channel}")

    exp_skill = run(str(orx), "--no-telemetry", "skill", "experiment-tree").lower()
    require("never edit a node" in exp_skill, "experiment_freeze_rule_missing")
    require("fixed" in exp_skill and "run command" in exp_skill, "fixed_run_contract_missing")

    delegation = run(str(orx), "--no-telemetry", "skill", "agent-delegation").lower()
    require("own worktree" in delegation, "helper_worktree_rule_missing")
    require("cannot see this conversation" in delegation, "self_contained_brief_rule_missing")

    projects = json.loads(run(str(orx), "--no-telemetry", "projects", "--json"))
    require(projects == [], f"expected_empty_local_store:{projects!r}")

    data_dir = pathlib.Path(os.environ["ORX_DATA_DIR"])
    require((data_dir / "orx.db").is_file(), "orx_db_not_isolated_in_data_dir")

    print("PANAM_OPENRESEARCH_PUBLIC_SMOKE_V1=PASS")
    print(f"upstream_sha={expected_sha}")
    print(f"build_channel={channel}")
    print("local_store=DISPOSABLE")
    print("production_authority=NONE")

if __name__ == "__main__":
    main()
