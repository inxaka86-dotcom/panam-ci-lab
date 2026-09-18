# Wave 4 — OpenResearch developer-plane adapter V1

Wave 4 tests the pure translation boundary proposed after the successful Wave 3
OpenResearch isolated pilot.

The adapter accepts a deliberately tiny JSON export and emits a deterministic
PANAM projection. It does not read OpenResearch SQLite, invoke `orx`, access a
network, launch agents, use compute, or create PANAM authority.

## Security / authority invariants

- exact upstream pin only: `alphaXiv/OpenResearch@69768ff1b0537a4656e69f550fc444ac35b945d2`;
- unknown fields fail closed;
- secret-like keys/values fail closed;
- invalid/missing parents and cycles fail closed;
- result claims require evidence pointers but remain `UNVERIFIED_EXTERNAL`;
- source status never becomes PANAM Task/Job State;
- output hard-codes `source_of_truth=false`, `projection_only=true`,
  `execution_authorized=false`, `owner_approval_satisfied=false`;
- authoritative PANAM job binding is always absent.

A green Wave 4 result is code-level developer-adapter evidence only.
