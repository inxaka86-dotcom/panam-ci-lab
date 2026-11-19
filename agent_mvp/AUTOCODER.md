# PANAM AutoCoder — simple autonomous coding agent

**Status:** working experimental Python workspace agent using **AI Dostup** and model `gpt-6.2-sol`. Two real end-to-end tests passed; not production-ready and not a general-purpose server operator.

## Send one command

1. Open **GitHub → inxaka86-dotcom/panam-ci-lab → Actions → PANAM AutoCoder - one task, one isolated branch**.
2. Choose **Run workflow**, enter one coding task in the **task** field, keep default model and run.
3. The agent reads the allowed project, writes code and runs unit tests. GitHub Actions independently repeats those tests in a no-network Docker container.
4. On success, the workflow pushes a new branch `agent/task-<run-id>-<attempt>` and shows a **Create PR comparison** link in the run summary. GitHub Actions cannot currently create a PR because the repository's security policy blocks that; ask ChatGPT to open a draft PR using its connected GitHub integration, or use the comparison link manually.

No additional key setup is required if the GitHub Actions secret `AIDOSTUP_API_KEY` is still configured. The secret is not committed. The external provider can see the user's task and portions of test/source text.

## Current permission boundary

- Only this repository's `agent_mvp/agent_workspace/src/*.py` can be created or edited.
- The agent may *read* the Python tests in `agent_mvp/agent_workspace/tests`, but cannot edit them.
- No arbitrary shell tool, production/Cloud.ru/GCP access, private repositories, merge privileges, or automatic PR approvals.
- Unit tests run in Docker with `--network none`, read-only workspace mount, no provider key and reduced capabilities.
- The workflow limits agent turns to 14 and job runtime to 12 minutes. These are **not** direct spending controls.
- The agent can make mistakes. Passing existing tests does not prove that a newly requested behavior is correct if tests do not cover it.
- **This is a public test repository**. Do not submit confidential source, credentials, non-public PANAM materials, personal data or legal case files to this workflow.
- A valid pull request is subject to human review. No automatic merge.

## Confirmed evidence

- Multi-file bug repair (7/7 tests): https://github.com/inxaka86-dotcom/panam-ci-lab/actions/runs/44511266830
- New module generated from a text task (10/10 tests): https://github.com/inxaka86-dotcom/panam-ci-lab/actions/runs/44511752526

## Next expansion

After human review of this experiment, add access to a separate **non-production** development repository/worktree and stronger task-specific acceptance tests. Do not bypass the existing PANAM Security Gate to obtain production access.
