# CLI-Anything LibreOffice public static qualification V1

Status: `PUBLIC_ONLY / STATIC_RESEARCH / NO_UPSTREAM_EXECUTION / NO_PRIVATE_REPO_ACCESS`

This public CI workload qualifies selected files from `HKUDS/CLI-Anything` at exact commit:

`810c18b0d1ab9b234bc996c9fd999318523a3ef0`

It exists to answer one narrow question: is the pinned LibreOffice harness sufficiently structured to justify a later isolated synthetic execution pilot?

## What this job does

- enforces this repository's public-only publication gate;
- downloads only selected public upstream source files at the exact commit;
- verifies exact Git blob identities;
- parses selected source statically;
- confirms expected security/engineering properties;
- records material gaps that a stricter downstream sandbox must close.

## What this job does not do

- it does not clone or access any private PANAM repository;
- it does not install CLI-Anything;
- it does not install or execute LibreOffice;
- it does not import upstream Python modules;
- it does not run upstream agent commands, REPLs or tests;
- it does not use real documents, user data, credentials or production systems;
- it does not publish packages;
- it grants no merge, deployment or production authority.

## Expected positive controls

The pinned selected files are expected to show:

- an upstream threat model for autonomous AI-agent command construction;
- explicit upstream guidance against `shell=True`;
- `subprocess.run()` list-style backend integration;
- a temporary isolated LibreOffice user profile;
- bounded export presets;
- an import extension allowlist;
- `defusedxml` for ODF XML parsing.

## Expected PANAM gaps

Static qualification intentionally records that the upstream model also exposes broader capabilities than a PANAM pilot should receive initially:

- its security guidance is separate from the agent generation SOP;
- REPL and persistent session state are part of the normal interface;
- package installation/publishing are part of the methodology;
- existing-document import is supported;
- overwrite is supported;
- agent guidance uses absolute file paths but the selected files do not establish a PANAM-style sandbox root as an authority boundary.

A PASS means only that the exact-pinned candidate is suitable for continued research. It is not an adoption decision.
