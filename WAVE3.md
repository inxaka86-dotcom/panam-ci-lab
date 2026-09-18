# Wave 3 — OpenResearch isolated pilot

This wave evaluates selected public OpenResearch mechanics in the public PANAM CI laboratory.

Upstream is pinned to:

`alphaXiv/OpenResearch@69768ff1b0537a4656e69f550fc444ac35b945d2` (OpenResearch CLI 0.2.5)

## Boundary

This wave uses only public upstream source and synthetic local state.

It has:

- no PANAM private repository access;
- no PANAM credentials or production data;
- no provider credentials;
- no managed compute;
- no production network endpoint;
- no self-hosted PANAM runner;
- no deployment authority.

A green result is benchmark/test evidence only.

## Measured properties

1. source build remains a development/no-production-telemetry build;
2. local OpenResearch state can be forced into a disposable data/config root;
3. experiment-branch collision does not rewrite existing experiment history;
4. terminal run ownership/result history remains immutable;
5. experiment ownership remains immutable across updates;
6. helper sessions cannot recursively spawn helpers;
7. helper concurrency remains bounded by upstream policy.

The workflow intentionally does not start `orx up`, log in, launch compute, create external instances, or connect an agent provider.
