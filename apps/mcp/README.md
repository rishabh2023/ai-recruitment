# AI Recruitment — MCP server

Exposes the recruitment platform as **MCP tools** so it can be driven conversationally from
Claude Code, ChatGPT (developer mode / custom connectors), or any MCP client. Every tool is a
thin wrapper over the FastAPI backend — the same API the web app uses — so all business rules,
gates, auth, and audit still apply. The assistant works in product concepts (jobs, candidates,
sourcing, outreach), never Hunar/telephony internals.

## Tools (27)

- **Context:** `whoami`, `dashboard_summary`, `recent_activity`
- **Jobs & workflow:** `list_jobs`, `get_job`, `create_job`, `add_job_description`,
  `confirm_job_version`, `draft_workflow`, `get_job_workflow`, `approve_workflow`,
  `activate_job`, `get_calling_policy`, `set_calling_policy`
- **Candidates & pipeline:** `list_candidates`, `import_candidate`, `candidate_timeline`,
  `decide_candidate`, `launch_stage`, `sync_call`
- **Sourcing (Flow B):** `list_people_search_providers`, `suggested_search_query`,
  `people_search`, `add_sourced_candidates`, `enrich_candidate`
- **Settings (admin):** `get_settings`, `update_settings`

Human-approval and safety gates are preserved: e.g. a job only activates after JD-confirm +
workflow-approve, `decide_candidate` needs a stage awaiting review, live calls fire only when
enabled, and provider search returns honest errors (never fabricated data).

## Setup

```bash
cd apps/mcp
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

The backend must be running (default `http://localhost:8000`). Configure via env:

| Env | Default | Purpose |
| --- | --- | --- |
| `RECRUIT_API_URL` | `http://localhost:8000` | Backend base URL |
| `RECRUIT_EMAIL` | `recruiter@demo.test` | Login (recruiter for most tools; **admin** for `update_settings`) |
| `RECRUIT_PASSWORD` | `demo-password` | Login password |
| `MCP_TRANSPORT` | `stdio` | `stdio` (Claude Code) or `streamable-http` (network) |
| `MCP_HOST` / `MCP_PORT` | `127.0.0.1` / `8765` | Bind for `streamable-http` |

The server signs in once and reuses the session cookie, re-authenticating automatically on 401.

## Connect from Claude Code

This repo ships a project-scoped [`.mcp.json`](../../.mcp.json) — open Claude Code in the repo
root and approve the `ai-recruitment` server when prompted. Or add it explicitly:

```bash
claude mcp add ai-recruitment -- /abs/path/apps/mcp/.venv/bin/python /abs/path/apps/mcp/server.py
```

Then just ask: *"Search PDL for backend engineers in Bengaluru for the FDE role and add the top 3."*

## Connect from ChatGPT (developer mode / custom connector)

Run the server over HTTP:

```bash
cd apps/mcp && . .venv/bin/activate
MCP_TRANSPORT=streamable-http MCP_PORT=8765 python server.py
# MCP endpoint: http://127.0.0.1:8765/mcp
```

In ChatGPT → Settings → Connectors → add a custom MCP connector pointing at that URL. ChatGPT
must be able to reach it, so for a local server expose it with a tunnel
(`cloudflared tunnel --url http://localhost:8765`) and use the resulting HTTPS `/mcp` URL.

## Notes

- Secrets stay server-side: provider API keys are set via `update_settings` / the Settings
  screen and are never returned by any tool.
- For a non-demo deployment, point `RECRUIT_API_URL` at the deployed API and use a real
  account's credentials (admin only where settings changes are needed).
