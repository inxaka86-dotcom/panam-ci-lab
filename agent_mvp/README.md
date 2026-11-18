# PANAM Agent MVP

An intentionally small, isolated, on-demand autonomous agent using the official OpenAI Agents SDK, hosted web search and sandboxed code interpreter. It **does not** access PANAM production servers, private repositories or Google Drive. It **does not** modify any external systems.

## One-time configuration

Set repository Actions secret `OPENAI_API_KEY` in GitHub Settings > Secrets and variables > Actions, with an active OpenAI API billing account. Never commit the key. ChatGPT subscription does not automatically grant API credits. Model defaults to `gpt-6-luna` (can be changed in workflow input).

## Run

Open the repository's Actions tab, select **PANAM Agent MVP (manual)**, press **Run workflow**, enter a task in Russian, and run. The agent independently decides when to use its web-search or sandboxed Python tools; its final report appears in the Actions run summary and as an artifact. Any missing credentials or tool failures are explicitly shown as failed execution. The GitHub Actions workflow must exist on the repository's default branch to be manually dispatchable.

## Known limitations

- Not always-on; runs on demand only.
- No private repository, PANAM Control Plane, Gmail, or production permissions.
- Actual live end-to-end work requires a valid API key and billing; adding code alone does not provide an API credential.
- Agent output may be imperfect and must be reviewed; its final status means a response was produced, not that every user objective was met.
- API model usage, web search and code interpreter incur charges; the GitHub Actions job has a 20-minute timeout and the SDK has a 12-turn limit, but these are not a hard money budget.

Official docs: https://openai.github.io/openai-agents-python/ and https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
