# Local execution evidence

Author: Work coding agent. Data class: PUBLIC_SYNTHETIC.

`red.*` records unchanged behavioral tests run against `inert_stub.txt` in a
separate temporary package. This is an intentionally failing synthetic negative
control, not a failed implementation attempt and not evidence of model repair.
`green.*` runs the same test bytes against the implemented utility. `root.*`,
`smoke.*` and `gate.*` record repository-wide checks.

Each receipt records the actual child command, exit code, monotonic duration,
UTC start, interpreter version, Git HEAD before the run and SHA-256 hashes of
inputs and exact stdout/stderr bytes. The recorded HEAD can precede staged or
uncommitted content: file hashes identify the code actually checked. Receipt
files do not hash themselves. Empty stdout files are intentional. The recorder
prints a short metadata line outside the saved child stdout/stderr streams.

`red-initial/` preserves the first control run (26 methods, 194 assertion
failures and one IndexError). The independence test indexed an empty stub result
before asserting its expected value. Its exact initial test bytes are retained
as `test_dependencies.py.txt`; an explicit expected-result assertion was added
before mutation. The second RED run has assertion failures only. Tests were
then frozen before implementation. This test-side correction is not a repair
to a model-generated implementation. Genuine implementation failures: zero at
the time of the first GREEN run; later outcomes are recorded in the logs.

To reproduce without replacing these original records:

```bash
python3 -B work_agent_pilot/evidence/record_run.py red --output-dir /tmp/work-agent-red
# Expected nonzero status: the synthetic negative control intentionally fails.
python3 -B work_agent_pilot/evidence/record_run.py green --output-dir /tmp/work-agent-green
python3 -B work_agent_pilot/evidence/record_run.py root --output-dir /tmp/work-agent-root
python3 -B work_agent_pilot/evidence/record_run.py smoke --output-dir /tmp/work-agent-smoke
python3 -B work_agent_pilot/evidence/record_run.py gate --output-dir /tmp/work-agent-gate
```

Commands can produce different timings, temporary paths and interpreter details
on another machine. Expected behavior and test input hashes remain checkable.
No hosted CI outcome is asserted by these local receipts.
