# Huntress MCP Server

An [MCP](https://modelcontextprotocol.io) server for the [Huntress](https://www.huntress.com) API (v1),
the managed security (EDR / ITDR / SIEM) platform MSPs use to protect their clients. It lets an
AI agent read the account, organizations, agents (protected endpoints), incident reports and
their remediations, escalations, signals, users, invoices and summary reports and, on explicit
request, resolve incidents and escalations, approve or reject remediations, and manage
organizations and users.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as HTTP headers and are
  never stored; every tool is listed from the first `tools/list`
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Huntress-Api-Key` | Yes | string | none | - | Huntress API key (public part) | `your-api-key` |
| `X-Huntress-Api-Secret` | Yes | string | none | - | Huntress API secret | `your-api-secret` |

Where to get them: in the Huntress portal open **API Credentials** and generate a key pair.
Keep the secret when it is shown; it is needed together with the key.

How they are sent to Huntress: every call goes to `https://api.huntress.io/v1/...` with HTTP
Basic authentication (`key:secret`).

A request to `/mcp` without both headers gets HTTP 401 naming the missing one.

## Tools

All tools return a JSON string. List tools take `limit` (default 10, max 200; larger values are capped) and `page_token`
and return `{count, has_more, next_page_token}`; pass `next_page_token` back as `page_token`
for the next page. **write** marks tools that change data; **confirm** marks tools that also
need `confirm: true`.

| Area | Tools |
|---|---|
| Overview | `huntress_navigate` (**domain**; describes the tools of one area), `huntress_status` |
| Account | `huntress_accounts_get`, `huntress_accounts_actor` |
| Agents | `huntress_agents_list` (organization_id, platform), `huntress_agents_get` (**id**) |
| Incidents | `huntress_incidents_list` (status, severity, platform, organization_id, agent_id), `huntress_incidents_get` (**id**), `huntress_incidents_remediations` (**incident_report_id**), `huntress_incidents_remediation_get` (**incident_report_id**, **remediation_id**); **write**: `huntress_incidents_resolve` (**id**), `huntress_incidents_bulk_reject` (**incident_report_id**, **comment**); **confirm**: `huntress_incidents_bulk_approve` (**incident_report_id**) |
| Escalations | `huntress_escalations_list`, `huntress_escalations_get` (**id**); **write**: `huntress_escalations_resolve` (**id**, determination, scope) |
| Organizations | `huntress_organizations_list`, `huntress_organizations_get` (**id**); **write**: `huntress_organizations_create` (**name**, **key**), `huntress_organizations_update` (**id**); **confirm**: `huntress_organizations_delete` (**id**, revoke_key) |
| Signals | `huntress_signals_list` (investigated_at_min/max, entity_type, entity_id, organization_id, types, statuses), `huntress_signals_get` (**id**) |
| Users | `huntress_users_list` (organization_id), `huntress_users_get` (**id**); **write**: `huntress_users_create` (**email**, **first_name**, **last_name**, **permissions**); **confirm**: `huntress_users_update` (**id**, **permissions**), `huntress_users_delete` (**id**) |
| Billing | `huntress_billing_reports_list` (status), `huntress_billing_reports_get` (**id**), `huntress_summary_reports_list` (period_min, period_max, organization_id, type), `huntress_summary_reports_get` (**id**) |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "unauthorized", "message": "Huntress returned HTTP 401 for agents: Unauthorized", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`. Reads are retried with backoff on 429, 5xx and network
errors; writes only on 429. Huntress allows about 60 API requests per minute.

## Run locally

```bash
uv sync
uv run python -m huntress_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t huntress-mcp:dev .
docker run --rm -p 8080:8080 huntress-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read
from the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Huntress-Api-Key: your-api-key" \
  -H "X-Huntress-Api-Secret: your-api-secret" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# open critical incidents
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Huntress-Api-Key: your-api-key" \
  -H "X-Huntress-Api-Secret: your-api-secret" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"huntress_incidents_list","arguments":{"status":"sent","severity":"critical"}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **Tool count (32).** Kept as is because the tool names are an existing contract.
- **Billing reports are invoices.** The Huntress API has no `/billing_reports` endpoint; older
  versions called it, so both billing tools failed. `huntress_billing_reports_list` / `_get`
  now read `/invoices`, keeping their names.
- **Confirmation for high-impact actions.** Approving remediations (they run on endpoints),
  changing a user's permission level and deleting organizations or users take `confirm: true`
  and otherwise return a "not done" result.
- **Rejecting remediations** sends `useful` (required by the API, default `false`) and accepts
  the optional `reason` code; approving accepts `manual_completion_remediation_ids`.
- **Updates use PATCH** with only the fields given; an update with no fields is rejected
  locally.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
