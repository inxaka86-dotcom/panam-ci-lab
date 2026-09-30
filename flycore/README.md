# FlyCore public evidence

This directory contains public-safe tooling for verifying the published MaleCNS
v1.0 connection-graph artifact used by the PANAM FlyCore research workstream.

Boundary:

- public MaleCNS data only;
- no PANAM private repository access;
- no credentials;
- no production identifiers or topology;
- no external actions other than fetching the fixed official public dataset URL;
- output is research evidence only and grants no PANAM production authority.

The metadata workflow computes the exact file size and SHA-256 and reads the
actual Arrow/Feather schema directly from the official downloaded artifact.
