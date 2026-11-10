# Public Tabularis MCP native canary (v0.32.0)

**Experiment only.** This open-source dependency test is independent of private PANAM source and data. Its only inputs are the public Tabularis release and an invented SQLite file created on an ephemeral GitHub-hosted runner. It uses no secrets, production endpoints, self-hosted runners or private repository access.

The `tabularis-native-smoke.yml` workflow is intentionally PR-scoped and pinned to the published SHA-256 of the official Linux v0.32.0 Debian artifact. It extracts that artifact without installing packages and starts its standalone `--mcp` process with a fresh `TABULARIS_DATA_DIR` and a strictly synthetic connection.

The probe checks JSON-RPC initialization/tool discovery; read-only SQLite SELECT, metadata, and CTE; rejection of INSERT/UPDATE/DELETE/DROP/ATTACH/stacked statements; and data immutability. It separately fails if the subprocess writes SQL requests, a fixture marker or the DB path to stderr. All findings are booleans and status strings — no raw responses, logs, environment or config files are exported as artifacts.

**Interpretation:** A failing CI test is test evidence, not a reason to loosen the privacy gate. Native execution success would remain research-only and does not authorize use of real data, repository merge, application deployment or bypassing the existing PANAM security model.

Sources: https://github.com/TabularisDB/tabularis/releases/tag/v0.32.0 (asset SHA-256 `02156031dd7d46be7ca964a12932497d8e51536bce4682746a4164381f963765`).
