# Reusing the existing PANAM disposable sandbox for Leanrea — scope assessment

**RESEARCH_ONLY / OFFLINE / PUBLIC-SAFE / NO CONTROL PLANE ACTION / NO EXECUTION AUTHORITY**

## What exists

PANAM already has an independently documented trust architecture combining a one-use disposable VM with an additional non-root, networkless container. Its fixed synthetic smoke showed no host Docker socket, read-only rootfs, zero capabilities, no-new-privileges, bounded writable tmpfs, absence of production credentials and verified VM teardown.

Later fixed-command testing demonstrated one reviewed static script could run in that boundary, suppress arbitrary untrusted stdout from affecting GitHub workflow interpretation and still destroy the one-use VM afterward.

These are accepted historical **fixed-smoke** results, not evidence that Codex, a live model, the Leanrea skill or its four static-analysis tasks have been admitted. The candidate execution route is controlled by protected trusted-main workflows and is deliberately NOT arbitrary command execution.

## The current integration gap

The existing trusted route only admits a live, non-draft **same-repository** PR and an explicitly reviewed fixed command choice. Leanrea research in this public CI laboratory is a **different repository** and is deliberately still a **Draft PR**. It has no automatic right to cross the source-boundary or reuse the trusted fixed-execution operation for arbitrary task/agent commands.

The present fixed smoke mode provides **no** general Leanrea A/B execution, no API broker and no provider call. Its network-none policy is appropriate for an offline static-analysis child but cannot directly call AiDostup; a separate reviewed credential-holding broker and IPC/egress trust design would be needed before any model work.

## What this PR adds (limited compatibility model)

`assess_sandbox_reuse.py` is a strict, non-executable **synthetic declaration comparator**. It explains why a proposed route is out of scope: cross-repository input, unsupported requested operation, upgrading fixed smoke to a model agent, historical evidence mistaken for new workload proof, network widening, agent-environment API credentials, missing immutable source pin/teardown, public answer keys or unknown USD hard cap.

`test_sandbox_reuse.py` checks those failures and forged approval/booleans. Every output, including one built from all hypothetically positive declarations, reports `execution_allowed=false`, `sandbox_evidence_authenticated=false`, `real_network_isolation_verified_for_leanrea=false`, and `production_change_allowed=false`. Input booleans are **untrusted claims**, not a signed receipt.

Reproduce with only Python standard library:

```sh
python3 -m unittest discover -s wave13 -p 'test_sandbox_reuse.py' -v
```

No network, subprocess, credential, cloud action, production path, API client, fixture execution, root/sudo, workspace mount or provider call is required.

## Conditions before extending the trusted PANAM route

A *separate, private, protected-main reviewed* extension would need to bind the public fixture archive **as untrusted data** to an immutable source commit and digest, without accepting source-selected host commands or cross-repository workflows. It should reuse the proven disposable-VM and inner-containment boundary only after explicit review and authority, not by weakening the present same-repo PR guard or changing a draft PR's status.

First pass should be **strictly offline**: a new fixed trusted operation, digest-pinned tool image containing exact preinstalled `file`, `rg`, `readelf`, `nm`, `objdump`, `strings` and Go metadata utilities; no network, credentials or model, read-only synthetic fixture inputs, no execution of analyzed binaries, pinned Leanrea instructions only for the candidate arm, independently verified teardown, and redacted bounded output. The baseline/candidate tool environments must match byte for byte.

Only after independent negative containment checks and correctness evaluation would a separate request broker be reviewed. That broker must remain outside the untrusted agent, enforce the actual USD-denominated provider spend limit and a fixed model route, and resist hidden Codex model turns, retries and concurrent calls. This is not part of this PR.

**No positive result from the public GitHub-hosted `unshare` probe is required to reuse an independently proven networkless inner sandbox.** Conversely, the old container's success is not evidence that the current Leanrea runner would be contained. Both must remain independently evaluated.

## Current decision

**DO NOT DISPATCH.** Existing sandbox = feasible **containment reference**, current fixed trusted route = **incompatible** with the separate public Leanrea PR and live-model A/B execution. No owner decision or production privileges should be inferred from the history or from the compatibility test. The correct next step is an independently reviewed restricted **offline** source-admission/agent-task interface, not a live AiDostup request.
