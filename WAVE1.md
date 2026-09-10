# Wave 1: public synthetic contracts

This wave contains only generic, synthetic checks that are safe to execute on standard GitHub-hosted runners.

Included:
- a resumable task-state contract with integrity checking;
- an engine-agnostic OCR/text quality benchmark harness with six invented fixtures;
- a deterministic query-only ranking contract that preserves a protected prefix and allows at most one promotion.

Boundaries:
- no private repository access;
- no credentials or secret contexts;
- no self-hosted runners;
- no real documents, people, organizations, production identifiers, logs or receipts;
- no production deployment or promotion authority.

A passing public workflow is test evidence only. Private integration remains separately reviewed and pinned to an explicit public revision before any production use.
