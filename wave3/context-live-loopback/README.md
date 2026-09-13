# Wave 3 — authenticated loopback MCP and live-console proofs

This public-only wave validates generic, synthetic local transport and operator-view boundaries for a read-only context service.

It intentionally contains no private PANAM source, fixtures, repository history, topology, credentials, user data, production logs, or private tool semantics.

## What the MCP proof proves

- a real HTTP listener binds only to `127.0.0.1` on an ephemeral port;
- Bearer authentication rejects a missing token with `401`;
- Bearer authentication rejects an invalid token with `401`;
- a valid caller without `mcp:read` is rejected with `403`;
- a runtime-generated bearer credential with `mcp:read` can connect through the official MCP TypeScript SDK v2;
- the negotiated protocol era is modern (`2026-07-28`);
- the exposed synthetic tools are explicitly read-only and non-destructive;
- the listener and MCP handler are closed after the probe.

## What the live-console proof proves

- the console is available only on the same `127.0.0.1` loopback listener;
- the console uses the same Bearer `mcp:read` boundary and rejects missing/invalid/no-scope callers with `401/401/403`;
- console data is obtained through an authenticated MCP client, not through direct source access;
- the console performs no durable snapshot storage and returns `Cache-Control: no-store`;
- ETag and cookies are absent;
- the response sets a deny-by-default Content Security Policy, `nosniff`, `no-referrer`, and same-origin resource policy;
- the HTML is inert: no JavaScript, forms, buttons, links, or action endpoint;
- `/console` is GET-only; POST is rejected;
- runtime bearer tokens are not emitted in the HTML or proof log;
- the MCP client, handler, and listener are closed after the probe.

The runtime credentials are generated in-memory by the tests and are never committed or printed.

## Reviewed upstream surface

The probes follow the official MCP TypeScript SDK v2 serving/auth patterns reviewed from upstream commit `b65426158ed9f29aea8ef3dc09ca22d7d9d6f970` and use exact package pins at `2.0.0` with `zod@4.2.0`.

## Non-goals

This wave does not validate private integration, production deployment, PANAM Memory, databases, keyrings, Control Plane authority, write tools, user authentication, internet exposure, TLS termination, an authorization server, browser session management, or persistent console history.

Public evidence is supporting transport/UI evidence only. Any private integration/promotion gate remains separate.
