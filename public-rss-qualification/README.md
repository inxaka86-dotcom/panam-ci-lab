# Public RSS qualification (offline-tested candidate)

Public-only standalone Python standard library + system curl. No private code, credentials, service access or production authority. No workflow is installed by this candidate and network execution is not scheduled.

Offline reproduction: `python3 canary.py --self-test`. Local 22 assertions passed; syntax passed. Live execution: NOT RUN. The code is designed for at most one GET per each of two fixed public RSS paths, stopping immediately on first failure, no redirect follow or retry, HTTPS with validated-address pin and TLS hostname verification, 64 KiB body cap, bounded output and 10 s outer deadline per object. Logs contain only counts, hashes and symbolic outcomes. No downloaded bodies retained. The body cap is an application limit, not a packet-level bandwidth guarantee. DNS and transport behavior, real RSS availability, robots/access policy and live isolation remain unverified.

Do not run live until the existing repository-wide publication gate passes, applicable site access/robots policies have been independently reviewed without extending the two-object request budget, and the exact experiment is reviewed on the approved disposable public runner. The CLI policy flag is an operator assertion, not evidence or authorization; never use it as an admission gate. No automatic live workflow, no repeated run. Offline synthetic address values are never contacted.

Current public main contains two legacy workflow files that violate the existing publication gate; the separate open PR #64 owns their remediation. This candidate does not modify those files or bypass the gate. Publication consists only of this standalone script and note; no source from a private repository is included.
