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
"""Incident reports, their remediations, and escalations."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import HuntressClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    WRITES_IDEMPOTENT,
    ClientFactory,
    Confirm,
    Limit,
    OrganizationFilter,
    PageToken,
    RecordId,
    compact,
    enum_value,
    list_page,
    not_confirmed,
    run_tool,
    unwrap,
)

IncidentId = Annotated[int, Field(description="Incident report id.", ge=1)]
Status = Literal["sent", "closed", "dismissed", "auto_remediating", "deleting", "partner_dismissed"]
Severity = Literal["low", "high", "critical"]
Platform = Literal["windows", "darwin", "microsoft_365", "google", "linux", "email_security", "other"]
RejectReason = Literal[
    "unspecified",
    "approved_application",
    "manually_remediated",
    "host_reimaged",
    "testing_security_controls",
    "other",
    "approved_user_login_location_m365",
    "approved_user_email_forwarding_rule_m365",
    "approved_application_m365",
    "manually_remediated_m365",
    "testing_security_controls_m365",
    "approved_vpn_or_proxy_usage_m365",
    "other_m365",
]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_incidents_list(
        limit: Limit = None,
        page_token: PageToken = None,
        status: Annotated[Status | str | None, Field(description="sent = open and awaiting the partner.")] = None,
        severity: Annotated[Severity | str | None, Field(description="Severity.")] = None,
        platform: Annotated[Platform | str | None, Field(description="Platform the incident came from.")] = None,
        organization_id: OrganizationFilter = None,
        agent_id: Annotated[int | None, Field(description="Only incidents of this agent.", ge=1)] = None,
    ) -> str:
        """List incident reports with severity, status, platform, organization, agent and indicators."""

        async def action(client: HuntressClient) -> dict:
            params = {
                "status": enum_value(status, Status),
                "severity": enum_value(severity, Severity),
                "platform": enum_value(platform, Platform),
                "organization_id": organization_id,
                "agent_id": agent_id,
            }
            return await list_page(client, "incident_reports", "incident_reports", params, limit, page_token)

        return await run_tool("huntress_incidents_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_incidents_get(id: IncidentId) -> str:
        """Get one incident report with the SOC write-up (body), indicators and affected entities."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"incident_reports/{id}"), "incident_report")

        return await run_tool("huntress_incidents_get", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def huntress_incidents_resolve(id: IncidentId) -> str:
        """Resolve (close) an incident report. Only when the user explicitly asks."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.post(f"incident_reports/{id}/resolution"), "incident_report")

        return await run_tool("huntress_incidents_resolve", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_incidents_remediations(incident_report_id: IncidentId, limit: Limit = None, page_token: PageToken = None) -> str:
        """List the remediations (fixes) proposed for an incident with their type and status."""

        async def action(client: HuntressClient) -> dict:
            return await list_page(client, f"incident_reports/{incident_report_id}/remediations", "remediations", {}, limit, page_token)

        return await run_tool("huntress_incidents_remediations", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_incidents_remediation_get(
        incident_report_id: IncidentId,
        remediation_id: Annotated[int, Field(description="Remediation id.", ge=1)],
    ) -> str:
        """Get one remediation of an incident: what it does, its type and status."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"incident_reports/{incident_report_id}/remediations/{remediation_id}"), "remediation")

        return await run_tool("huntress_incidents_remediation_get", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def huntress_incidents_bulk_approve(
        incident_report_id: IncidentId,
        manual_completion_remediation_ids: Annotated[
            list[int] | None, Field(description="Remediation ids you will do yourself instead of Huntress automating them.")
        ] = None,
        confirm: Confirm = None,
    ) -> str:
        """Approve all pending remediations of an incident; Huntress then runs them on the endpoints.

        Changes machines (kills processes, removes files, isolates, ...).
        Only when the user explicitly asks; needs confirm: true.
        """

        async def action(client: HuntressClient) -> Any:
            if confirm is not True:
                return not_confirmed(f"Approve and run all pending remediations of incident {incident_report_id}")
            body = compact({"manual_completion_remediation_ids": manual_completion_remediation_ids})
            await client.post(f"incident_reports/{incident_report_id}/remediations/bulk_approval", body)
            return {"done": True, "incident_report_id": incident_report_id, "approved": "all pending remediations"}

        return await run_tool("huntress_incidents_bulk_approve", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def huntress_incidents_bulk_reject(
        incident_report_id: IncidentId,
        comment: Annotated[str, Field(description="Why the remediations are rejected (sent to the SOC).", min_length=1)],
        useful: Annotated[bool | None, Field(description="Whether the report was useful (default false).")] = None,
        name: Annotated[str | None, Field(description="Contact name for SOC follow-up.")] = None,
        phone_number: Annotated[str | None, Field(description="Contact phone.")] = None,
        email: Annotated[str | None, Field(description="Contact email.")] = None,
        reason: Annotated[RejectReason | None, Field(description="Rejection reason code.")] = None,
    ) -> str:
        """Reject all pending remediations of an incident with feedback to the SOC. Only when explicitly asked."""

        async def action(client: HuntressClient) -> Any:
            body = compact(
                {
                    "comment": comment,
                    "useful": useful is True,
                    "name": name,
                    "phone_number": phone_number,
                    "email": email,
                    "reason": reason,
                }
            )
            await client.post(f"incident_reports/{incident_report_id}/remediations/bulk_rejection", body)
            return {"done": True, "incident_report_id": incident_report_id, "rejected": "all pending remediations"}

        return await run_tool("huntress_incidents_bulk_reject", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_escalations_list(limit: Limit = None, page_token: PageToken = None) -> str:
        """List escalations: SOC findings that need a partner decision (e.g. unusual 365 logins)."""

        async def action(client: HuntressClient) -> dict:
            return await list_page(client, "escalations", "escalations", {}, limit, page_token)

        return await run_tool("huntress_escalations_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_escalations_get(id: RecordId) -> str:
        """Get one escalation with its entities (identities, IPs, locations) and what needs deciding."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"escalations/{id}"), "escalation")

        return await run_tool("huntress_escalations_get", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def huntress_escalations_resolve(
        id: RecordId,
        determination: Annotated[
            Literal["expected", "unauthorized"] | None, Field(description="expected = legitimate activity; unauthorized = malicious.")
        ] = None,
        scope: Annotated[
            Literal["account", "organization", "identity"] | None, Field(description="How widely to apply an expected determination.")
        ] = None,
    ) -> str:
        """Resolve an escalation as expected or unauthorized activity. Only when the user explicitly asks."""

        async def action(client: HuntressClient) -> Any:
            body = compact({"determination": determination, "scope": scope})
            return await client.post(f"escalations/{id}/resolution", body)

        return await run_tool("huntress_escalations_resolve", client_factory, action)
