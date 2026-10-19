# Public synthetic evidence anchors — V1

Status: **RESEARCH_ONLY / PUBLIC_SYNTHETIC_ONLY / NO_MODEL_OR_PROVIDER_CALLS / NOT_BLIND**.

## Objective and trust boundary

`verify_public_evidence.py` independently re-opens **only a small fixed allowlist** of the four generated synthetic targets and checks whether a submitted answer's cited location actually contains a corresponding *value anchor*.

This closes one narrow testing gap: the existing `score_synthetic.py` checks *answers against public expected values* but does not inspect citations. Here, source-line citations are checked at the exact line number **for a complete single- or double-quoted JavaScript string literal (not a mere substring)**; `nm`, `strings`, `go version -m` and a single function-scoped `objdump` read only the generated synthetic binaries. Commands are passed as argument vectors without shell interpolation; the tool never runs a generated binary, opens private PANAM sources or sends network/model requests.

It is **not** an independent validity check of analytic reasoning. Finding an exported symbol does not establish that it is actually called, a string does not establish runtime behavior, and a constant by itself is not an explanation of a permission rule. For the specially compiled synthetic ELF permission fixture, the detector now requires a call to `geteuid@plt` plus a `cmp $immediate,%register` instruction within `capture_access_check`; it still cannot prove the complete control-flow meaning, portability to other architectures or actual runtime behavior. In particular the public test data and public answer key are searchable, not truly blind.

## Structured submission contract

Input must contain `schema: "panam.leanrea.public-evidence-submission.v1"` and exactly four `responses`, each with `case_id`, `answers` and `evidence`. Each of the nine answer fields must have a matching evidence object with **exactly** `path`, `method`, `line`. All paths are fixed, repository-relative paths within the synthetic target folder, not user-controlled file selectors. The evidence `line` is a 1-based integer only for `source-line` method; for compiled artifacts it must be JSON `null`.

| Case | Field | Allowed evidence |
| --- | --- | --- |
| LR-E01 | `start_channel`, `changed_channel` | `source-line` in `targets/electron-app/.webpack/main.js` or `.vite/preload.js` |
| LR-N01 | `permission_symbol` | `nm-export` on `targets/libcapture_probe.so` |
| LR-N01 | `allowed_euid` | `objdump-immediate` in `capture_access_check` on `targets/libcapture_probe.so`; decimal input must correspond to a `cmp` immediate in the fixed function with a nearby `geteuid@plt` call; not arbitrary MOV values |
| LR-G01 | `module_path`, `toolchain` | `go-build` on `targets/go_probe` |
| LR-D01 | `socket_path`, `accepted_message` | `strings-line` on `targets/libwire_probe.so` |
| LR-D01 | `peer_check_symbol` | `nm-export` on `targets/libwire_probe.so` |

Example excerpt (not a complete submission):

```json
{
  "case_id": "LR-E01",
  "answers": {
    "start_channel": "records:begin-v2",
    "changed_channel": "records:changed-v2"
  },
  "evidence": {
    "start_channel": {
      "path": "targets/electron-app/.webpack/main.js",
      "method": "source-line",
      "line": 2
    },
    "changed_channel": {
      "path": "targets/electron-app/.webpack/main.js",
      "method": "source-line",
      "line": 3
    }
  }
}
```

Malformed packets, extra fields, cross-case target paths, path traversal, invalid or symlinked inspected files, tool substitutions, Boolean/non-integer positions and attempts to assert verified agent results are rejected. Plausible but unsupported answers get `anchor_present=false` rather than a false positive. Negative regression cases specifically cover incomplete IPC channel fragments, arbitrary `mov $immediate` values and comparison immediates without a `geteuid@plt` call. These tests limit **known** false positives in the fixed synthetic fixtures; they do not prove a general disassembler or semantic verifier.

## Output meaning

The checker reports nine booleans and a count of **matching anchors only**. It always sets `semantic_correctness_verified=false`, `agent_trace_verified=false`, `independent_blind_gold_verified=false`, `real_agent_benefit_proven=false` and `authority=NONE`.

Run the independent public synthetic test suite (build dependencies must already be installed):

```sh
python3 -m unittest discover -s wave13 -p 'test_public_evidence.py' -v
```

The public GitHub Actions workflow runs 28 synthetic/adversarial tests against locally generated fixtures. A green result cannot authorize a Codex call, bypass owner-only Control Plane policy or establish speed, cost, model correctness or output trace authenticity.

The user-facing A/B workspace exporter intentionally excludes this checker and the entire scorer/gold/source code. The public GitHub repository itself still exposes the labels; truly blinded evaluation remains a separate private reviewed task.
