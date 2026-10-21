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
"""Signals: detections the SOC investigated (whether or not they became incidents)."""

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

EntityType = Literal["user_entity", "source", "mailbox", "service_principal", "agent", "identity"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_signals_list(
        limit: Limit = None,
        page_token: PageToken = None,
        investigated_at_min: Annotated[str | None, Field(description="ISO 8601: investigated on or after.")] = None,
        investigated_at_max: Annotated[str | None, Field(description="ISO 8601: investigated on or before.")] = None,
        entity_type: Annotated[EntityType | str | None, Field(description="Type of entity the signal came from.")] = None,
        entity_id: Annotated[str | None, Field(description="Entity id (with entity_type).")] = None,
        organization_id: OrganizationFilter = None,
        types: Annotated[str | None, Field(description="Comma-separated signal types, e.g. Antivirus, Process Detection.")] = None,
        statuses: Annotated[str | None, Field(description="Comma-separated: reported, closed.")] = None,
    ) -> str:
        """List signals the SOC investigated, by time window, entity, organization, type or status."""

        async def action(client: HuntressClient) -> dict:
            params = {
                "investigated_at_min": investigated_at_min,
                "investigated_at_max": investigated_at_max,
                "entity_type": enum_value(entity_type, EntityType),
                "entity_id": entity_id,
                "organization_id": organization_id,
                "types": types,
                "statuses": statuses,
            }
            return await list_page(client, "signals", "signals", params, limit, page_token)

        return await run_tool("huntress_signals_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_signals_get(id: RecordId) -> str:
        """Get one signal with its details and the entity it concerns."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"signals/{id}"), "signal")

        return await run_tool("huntress_signals_get", client_factory, action)
