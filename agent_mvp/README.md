# PANAM Agent MVP — AiDostup

Minimal agent with **one manual task input**, an actual iterative model/tool loop, and an output report in GitHub Actions. No PANAM production access and no direct OpenAI API key.

## Setup (once)

Open repository **Settings → Secrets and variables → Actions → New repository secret** and create:

- Name: `AIDOSTUP_API_KEY`
- Value: the secret key from your AiDostup account (never paste it into the repository or GitHub Actions input).

The **only LLM provider** is AiDostup: `https://aidostup.site/v1`, using the official OpenAI Python client in compatibility mode. Model `gpt-6.2-sol` is an example ID documented by the provider. This is a paid external service; verify your balance before running.

## One-command task

In the **Actions** tab select **PANAM Agent MVP (AiDostup)** → **Run workflow** → enter your task → **Run workflow**. The workflow MUST be present on the default branch, and GitHub Actions must be enabled. Read the run log, summary, and the attached `panam-agent-result` artifact. If an action fails, the log and report state the error.

Capabilities are real **only when the external API responds and supports function calling for the selected model**. Four local read-only tools: Bing RSS web search (can fail if blocked), fetch public HTTPS page, search public GitHub repos, calculate numerical expressions. No OpenAI-hosted tools are used, because compatibility with AiDostup has not been established.

## Limits and security

- On-demand only; not running continuously.
- No production servers, Google Drive, private GitHub repositories, write operations or deployment.
- Agent does not see the secret string; the secret is sent only by the authenticated API client to AiDostup.
- Third-party LLM calls route user task text and results through AiDostup; do not send confidential material without separately assessing the provider.
- SDK tracing is disabled; don't assume AiDostup retains no data.
- Limit is 12 agent turns and 20 minutes per run, **not** a guaranteed monetary spending cap.
- The key is required to verify the live end-to-end path; a GitHub merge alone is **not** proof that the agent succeeded.

Official docs:
- https://aidostup.site/connect-python.html
- https://aidostup.site/docs.html
- https://openai.github.io/openai-agents-python/models/
