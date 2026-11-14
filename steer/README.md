# Steer public-source native smoke (research only)

Goal: compile and execute the upstream project's documented `make test` checks on a **disposable GitHub-hosted runner**, without using PANAM production servers, private repositories, credentials, or configuration.

- Source: `splify2/steer` at exact commit `70d11ebb6ab7b618508e1bbb593a3d28a9cf4d08` (VERSION `2.1.4`).
- Scope: public upstream source only; rootless native build and test. The test suite is *intended* to be offline according to upstream documentation, but this CI job does not enforce an OS-level deny-all network policy.
- CI: `.github/workflows/steer-pinned-offline.yml`, PR-scoped and GitHub-hosted, no self-hosted runners, with `contents: read` and nonpersistent checkout credentials.
- Evidence: upstream commit check, build/test job status, raw logs (seven-day retention), explicit skip classification in the job summary.
- Important: some upstream tests, including `tests/applynft.sh`, report `exit 0` when root, nft or network namespaces are unavailable. **A green CI status is not proof of live nftables, isolation, DNS leak prevention or fail-closed behavior.**

Follow-up remains a separate, owner-admitted disposable OpenWrt VM test with actual kernel network namespaces, no routes to PANAM, packet capture, intentional tunnel loss, IPv4/IPv6 and DNS checks, and cleanup/readback receipts. This change does not install Steer, run SSH commands, modify Cloud.ru or GCP, deploy services, or change PANAM Security Gate.
