# Wave 8 — EdenText legal-review compatibility canary

This wave is public-safe and synthetic.

It evaluates one immutable public EdenText revision as a compatibility candidate for a
legal-document review workflow. It does **not** contain or fetch private PANAM source,
real legal documents, credentials, production configuration, or production authority.

## Upstream binding

Repository: `stffnb/edentext`

Commit: `d64db2d7bf2a304b8bbe63e4ab3131f962229799`

Version at the reviewed revision: `0.7.0`

The workflow fetches that exact commit into a temporary directory, verifies HEAD, removes
the remote, installs dependencies from the upstream lockfile, and runs bounded tests.

## Canary scope

The public synthetic canary verifies:

- upstream DOCX/ODT round-trip tests;
- tracked replacement keeps old text as a deletion and new text as an insertion;
- accept/reject semantics;
- a synthetic AI reviewer appears as the revision author;
- a synthetic AI comment with reply/resolved state survives DOCX round trip;
- unsafe link-scheme guards;
- unsafe XML / archive-boundary tests already present upstream.

## Explicit non-goals

- no proprietary-license conclusion;
- no PANAM private adapter source;
- no confidential persistence implementation;
- no real documents or personal data;
- no production access or deployment;
- no automatic acceptance of AI edits.

A green run is compatibility evidence only.
