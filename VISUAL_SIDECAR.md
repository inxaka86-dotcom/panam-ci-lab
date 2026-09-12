# Public visual sidecar synthetic contract

This directory is a separately authored public-safe CI fixture for testing an exact-pinned static presentation renderer.

It intentionally contains no private PANAM source, private repository history, production topology, credentials, real documents, user data, logs, receipts, incidents or production authority.

The test uses only:

- a synthetic Quick-spec JSON fixture;
- a public verification script;
- the exact public Visual Explainer Quick renderer at release `0.11.0`, commit `7163c3e10660912e0b89e1af465db9f387282b88`;
- exact Git blob checks for the downloaded renderer assets.

The public CI result proves only the bounded synthetic renderer properties checked here: exact upstream binding, deterministic output, hostile-text escaping, absence of bounded active-content markers and absence of external HTTP href/src references.

It does not validate private PANAM integration and grants no merge, deployment, production write, send or Control Plane authority.
