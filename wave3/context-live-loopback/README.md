# Wave 3 — authenticated loopback MCP proof

This public-only wave validates a generic, synthetic transport boundary for a read-only context service.

It intentionally contains no private PANAM source, fixtures, repository history, topology, credentials, user data, production logs, or private tool semantics.

## What it proves

- a real HTTP listener binds only to `127.0.0.1` on an ephemeral port;
- Bearer authentication rejects a missing token with `401`;
- Bearer authentication rejects an invalid token with `401`;
- a valid caller without `mcp:read` is rejected with `403`;
- a runtime-generated bearer credential with `mcp:read` can connect through the official MCP TypeScript SDK v2;
- the negotiated protocol era is modern (`2026-07-28`);
- the exposed synthetic tools are explicitly read-only and non-destructive;
- the listener and MCP handler are closed after the probe.

The runtime credentials are generated in-memory by the test and are never committed or printed.

## Reviewed upstream surface

The probe follows the official MCP TypeScript SDK v2 serving/auth patterns reviewed from upstream commit `b65426158ed9f29aea8ef3dc09ca22d7d9d6f970` and uses exact package pins at `2.0.0` with `zod@4.2.0`.

## Non-goals

This wave does not validate private integration, production deployment, PANAM Memory, databases, keyrings, Control Plane authority, write tools, user authentication, internet exposure, TLS termination, or an authorization server.

Public evidence is supporting transport evidence only. Any private integration/promotion gate remains separate.
