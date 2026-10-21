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
"""Invoices (billing reports) and summary reports."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import HuntressClient
from ._common import (
    READ_ONLY,
    ClientFactory,
    Limit,
    OrganizationFilter,
    PageToken,
    RecordId,
    enum_value,
    list_page,
    run_tool,
    unwrap,
)

InvoiceStatus = Literal["open", "paid", "failed", "partial_refund", "full_refund", "draft", "voided", "processing"]
ReportType = Literal["monthly_summary", "quarterly_summary", "yearly_summary"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_billing_reports_list(
        limit: Limit = None,
        page_token: PageToken = None,
        status: Annotated[InvoiceStatus | None, Field(description="Invoice status.")] = None,
    ) -> str:
        """List invoices (billing reports) with amount, plan, quantity, status and dates."""

        async def action(client: HuntressClient) -> dict:
            return await list_page(client, "invoices", "invoices", {"status": status}, limit, page_token)

        return await run_tool("huntress_billing_reports_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_billing_reports_get(id: RecordId) -> str:
        """Get one invoice with its line details and receipt."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"invoices/{id}"), "invoice")

        return await run_tool("huntress_billing_reports_get", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_summary_reports_list(
        limit: Limit = None,
        page_token: PageToken = None,
        period_min: Annotated[str | None, Field(description="ISO 8601 date: reports for periods from this date.")] = None,
        period_max: Annotated[str | None, Field(description="ISO 8601 date: reports for periods up to this date.")] = None,
        organization_id: OrganizationFilter = None,
        type: Annotated[ReportType | str | None, Field(description="Report period type.")] = None,
    ) -> str:
        """List summary reports (monthly / quarterly / yearly security summaries per organization)."""

        async def action(client: HuntressClient) -> dict:
            params = {"period_min": period_min, "period_max": period_max, "organization_id": organization_id, "type": enum_value(type, ReportType)}
            return await list_page(client, "reports", "reports", params, limit, page_token)

        return await run_tool("huntress_summary_reports_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_summary_reports_get(id: RecordId) -> str:
        """Get one summary report with its figures and download link."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"reports/{id}"), "report")

        return await run_tool("huntress_summary_reports_get", client_factory, action)
