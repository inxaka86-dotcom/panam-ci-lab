# CLI-Anything LibreOffice executable pilot V2

Status: `PUBLIC_RESEARCH / SYNTHETIC_ONLY / DISPOSABLE_RUNNER / NO_PRODUCTION_AUTHORITY`

## Purpose

V2 executes the exact-pinned public `HKUDS/CLI-Anything` LibreOffice harness in a disposable public GitHub-hosted environment using only synthetic Writer content.

Upstream commit: `810c18b0d1ab9b234bc996c9fd999318523a3ef0`.

This public pilot complements the private PANAM admission/security contract. It does not fetch, inspect or execute private PANAM source.

## Exact-source inheritance

This branch carries forward the exact-source qualification from the earlier public static review. The static workflow still binds the reviewed upstream files and structural markers to exact Git blobs before any PANAM adoption discussion.

The executable workflow additionally fetches the exact upstream commit and verifies the pinned `libreoffice/agent-harness/setup.py` Git blob before running.

## Allowed executable scope

The fixed pilot invokes only:

- Writer document creation;
- `writer add-heading`;
- `writer add-paragraph`;
- `writer add-list`;
- `writer add-table`;
- `writer list`;
- export to ODT;
- export to PDF;
- export to DOCX.

The synthetic marker is `PANAM_SYNTHETIC_EXEC_PILOT_V2`.

## Explicit denials

The pilot does not invoke:

- document import/open of an external Office/ODF file;
- REPL;
- session history/undo/redo;
- Calc or Impress;
- overwrite;
- package publishing;
- real PANAM documents;
- PANAM credentials, DB, Drive, Telegram, production services or private repository source.

No output is uploaded as an artifact. The verifier prints only file sizes and SHA-256 hashes plus pass/fail evidence.

## Execution isolation

Acquisition and disposable dependency installation occur before the execution gate.

The actual CLI/LibreOffice commands run:

- on a disposable GitHub-hosted public runner;
- from an explicit synthetic sandbox root;
- as a non-root user;
- with HOME/TMP/XDG directories redirected beneath the sandbox;
- inside a new Linux network namespace;
- after a fail-closed check proving outbound connectivity is unavailable.

The workflow uses a fixed invocation script. No agent-supplied shell command or free-form executable field exists.

## Output verification

The verifier requires:

- `project.json` to parse and contain the synthetic marker;
- ODT to be a valid ZIP/ODF text package with uncompressed first-entry `mimetype`, `content.xml`, and manifest;
- PDF to have a `%PDF-` header and non-trivial size;
- DOCX to contain `[Content_Types].xml` and `word/document.xml`, contain the marker, and contain no VBA project binary;
- all four outputs to resolve beneath the sandbox and not be symlinks.

## Supply-chain boundary

This is an executable research pilot, not a production dependency lock.

The exact upstream source commit is pinned, but Ubuntu APT and Python dependency artifacts are not cryptographically prelocked. The workflow therefore reports:

`SUPPLY_CHAIN_LOCKED=false`

A successful V2 run can prove functional/sandbox behavior only. It cannot authorize production installation or package promotion.

## Authority boundary

A PASS means only:

`authority = public_research_evidence_only`

It grants no PANAM source-of-truth, Memory, Task/Job, Risk/Approval, External Operations, Control Plane or production authority.

A later private design step may use this evidence to define a fixed argv executor behind the already-merged PANAM admission gate. That later step requires separate review and owner authorization.
