# Leanrea equal-workspace dry run — researcher handoff

Status: **RESEARCH_ONLY / NO AGENT / NO MODEL / NO SECRETS / NO PRODUCTION / NOT SANDBOXED**

## What this solves

The source repository contains not only the synthetic fixture generator but also grading code and public answer keys. Passing the whole checkout to an analysis agent would contaminate an A/B comparison. `export_equal_workspaces.py` creates two separately copied workspaces with the **same seven files by path and byte SHA-256**: `base` and `leanrea`. They contain the four synthetic tasks, three synthetic Electron JSON/JS files (including hidden .webpack/.vite), two ELF shared libraries and one Go binary.

This is evidence of *workspace equality and separation*, not truly blind ground truth. The scorer remains discoverable in this publicly visible repository. A model with internet access can recover it; a private restricted, independently sealed test set would be needed for a real blind A/B.

## How to reproduce offline

From repository root, with preinstalled Python 3, Go, C compiler and ELF inspection tools:

```sh
python3 wave13/export_equal_workspaces.py --out /path/to/new/disposable-output
python3 -m unittest discover -s wave13 -p 'test_equal_workspaces.py' -v
```

The output location must be a previously nonexistent leaf of a real existing directory that is disposable and has no credentials. The exporter itself calls the existing synthetic compiler in an ephemeral private directory, then copies exact selected bytes to both arms. The exporter never executes the compiled targets and does not launch Codex, access AiDostup, load credentials, or install dependencies. It is not designed for the production host.

## Output

`base/` and `leanrea/` contain identical content. The root-level `WORKSPACE_MANIFEST.json` lists content SHA-256 values and explicitly states `agent_execution=false`, `network_sandbox_verified=false` and `mode=OFFLINE_SYNTHETIC_NO_AGENT`.

There is **no** `SKILL.md`, `score_synthetic.py`, test source, answer key, git metadata, API key, network configuration or runtime credential in either workspace. All copied files are mode `0600`; binary execute permissions are cleared. This prevents direct execution through filesystem permission bits, but a different interpreter/loader could still inspect and execute bytes. Thus, **not a security sandbox**. Future approved runtime must independently enforce no-exec and egress restrictions.

To compare agent instruction strategies in the future, the approved test launcher must inject the pinned Leanrea skill **outside** the `leanrea/` artifact workspace, leaving the `base/` workspace without it. This exporter does **not** invoke the launcher or choose provider routes.

## How to interpret success

Positive export tests show identical SHA-256 manifests, four identical task entries, no answer key or skill file in either workspace, read-only research authority, and that unexpected files, preexisting targets, dangling symlinks and unsafe permissions fail closed.

This does not measure Codex quality, cost, token use, tool count or elapsed time. Repository public graders prevent any claim of independently blinded labels. No merge/deploy/production authority is supplied by the exporter or green CI.
