# TesterArmy e2e public synthetic pilot

This checks only a locally served, fictional HTML fixture. It does **not** test the PANAM website, infrastructure or clients.

## Requirements and run

- Node.js 24.8 or newer (CI uses 26).
- Run in this directory: `npm install --no-audit --no-fund --ignore-scripts`.
- Install Chromium: `npx --no-install e2e-web install chromium --with-deps`.
- Run tests: `E2E_TELEMETRY_DISABLED=1 npm run test:e2e`.

Two Chromium viewports (1280x800 and 390x844) verify headings, navigation and logo bounds. The fixture is bound to loopback address 127.0.0.1 only. No model, API credentials, production endpoints, external sites or private assets are used.

CI uses a GitHub-hosted runner with read-only permissions, disabled e2e telemetry, and a public-only publication gate. The JUnit/JSON report and optional failure artifacts are uploaded for seven days. Passing tests are evidence for the synthetic fixture only, never deployment authorization.

Direct dependencies are pinned to e2e 0.21.2 and @e2e-dev/web 0.15.2. No transitive lockfile is committed in this exploratory PR: the resolution is not fully reproducible. Before widening adoption, review dependencies and generate a committed package-lock.json on a clean environment, then use npm ci.

## Hard boundary

Do not fetch or mirror private PANAM repositories, real client data, secrets, production endpoints or access tokens into this public repo. Real PANAM site tests belong in an explicitly reviewed private isolated test lane.
