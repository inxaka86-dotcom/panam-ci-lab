# Wave 10 — Synthetic Runtime Entrypoint

Wave 10 validates the final composition layer before private deployment wiring.

It intentionally uses only public synthetic components and fake dependencies. It does not contain PANAM credentials, real Google Drive identifiers, production folder IDs, real Tokenn endpoints, private documents or private runtime topology.

## What it validates

- provider/generation dependency is lazy;
- artifact-store dependency is lazy;
- generation does not initialize storage;
- storage does not initialize generation;
- generated artifacts require a dedicated protocol-only storage scope;
- there is no fallback to a generic/Inbox-like storage scope;
- the real public Wave 8 generation adapter is used;
- the real public Wave 8 idempotent writer is used;
- the real public Wave 9 one-shot JSON worker is used;
- exact replay is idempotent and does not create a second artifact.

## Private mapping

The private Wave 10 equivalent maps these generic dependencies to:

- PANAM's existing Tokenn provider layer;
- PANAM's existing OAuth refresh-token Google Drive client;
- a mandatory dedicated protocol-drafts folder;
- Wave 8 private adapters;
- Wave 9 private one-shot IPC worker.

The public lab proves only the generic composition contract. It does not prove or authorize real credentials, real Drive operations, deployment, Inbox scanning, Autopilot or sending.
