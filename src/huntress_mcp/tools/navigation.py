# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tool discovery (kept for compatibility) and the connection check."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .._json import compact as to_json
from ..api_client import HuntressClient
from ._common import LOCAL, READ_ONLY, ClientFactory, run_tool, unwrap

DOMAINS: dict[str, tuple[str, list[str]]] = {
    "accounts": ("The API key's account and actor.", ["huntress_accounts_get", "huntress_accounts_actor"]),
    "agents": ("Protected endpoints (agents).", ["huntress_agents_list", "huntress_agents_get"]),
    "incidents": (
        "Incident reports, remediations and escalations.",
        [
            "huntress_incidents_list",
            "huntress_incidents_get",
            "huntress_incidents_resolve",
            "huntress_incidents_remediations",
            "huntress_incidents_remediation_get",
            "huntress_incidents_bulk_approve",
            "huntress_incidents_bulk_reject",
            "huntress_escalations_list",
            "huntress_escalations_get",
            "huntress_escalations_resolve",
        ],
    ),
    "organizations": (
        "Organizations (clients): list, get, create, update, delete.",
        [
            "huntress_organizations_list",
            "huntress_organizations_get",
            "huntress_organizations_create",
            "huntress_organizations_update",
            "huntress_organizations_delete",
        ],
    ),
    "signals": ("Signals investigated by the SOC.", ["huntress_signals_list", "huntress_signals_get"]),
    "users": (
        "Users (account memberships): list, get, create, update, delete.",
        ["huntress_users_list", "huntress_users_get", "huntress_users_create", "huntress_users_update", "huntress_users_delete"],
    ),
    "billing": (
        "Invoices and summary reports.",
        ["huntress_billing_reports_list", "huntress_billing_reports_get", "huntress_summary_reports_list", "huntress_summary_reports_get"],
    ),
}

Domain = Literal["accounts", "agents", "incidents", "organizations", "signals", "users", "billing"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=LOCAL)
    async def huntress_navigate(domain: Annotated[Domain, Field(description="Area to describe.")]) -> str:
        """Describe the tools of one Huntress area. All tools are already callable; this changes nothing."""
        summary, tools = DOMAINS[domain]
        return to_json({"domain": domain, "summary": summary, "tools": tools})

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_status() -> str:
        """Check the Huntress connection: the account the API key belongs to."""

        async def action(client: HuntressClient) -> dict:
            account = unwrap(await client.get("account"), "account")
            name = account.get("name") if isinstance(account, dict) else None
            return {"connected": True, "account": name, "account_id": account.get("id") if isinstance(account, dict) else None, "domains": list(DOMAINS)}

        return await run_tool("huntress_status", client_factory, action)
