# Wave 9: public synthetic Python ↔ Node runtime IPC

Wave 9 validates one bounded process boundary:

`Python client -> one JSON stdin command -> Node worker using real public Wave 8 adapters -> one JSON stdout response -> Python client`

## Contract

- argv execution only; no shell command string;
- one schema-versioned request and one JSON response line;
- finite subprocess timeout;
- bounded stdout size;
- invalid/multiple JSON output fails closed;
- nonzero exit fails closed even if stdout looks successful;
- worker errors are bounded and common secret-like forms are redacted;
- Python does not echo raw worker stderr;
- generated/stored text exists only as ephemeral IPC payload;
- the synthetic Node fixture composes the actual public Wave 8 generation and idempotent writer adapters.

No private repository, credential, real Drive, external model service, network listener, background daemon, sending or deployment authority is used in this public validation.
