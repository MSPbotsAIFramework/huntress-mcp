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
"""Agents: protected endpoints."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import HuntressClient
from ._common import READ_ONLY, ClientFactory, Limit, OrganizationFilter, PageToken, RecordId, list_page, run_tool, unwrap


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_agents_list(
        limit: Limit = None,
        page_token: PageToken = None,
        organization_id: OrganizationFilter = None,
        platform: Annotated[Literal["windows", "darwin", "linux"] | None, Field(description="Operating system family.")] = None,
    ) -> str:
        """List agents (protected endpoints) with hostname, OS, platform, versions, IPs and last check-in."""

        async def action(client: HuntressClient) -> dict:
            params = {"organization_id": organization_id, "platform": platform}
            return await list_page(client, "agents", "agents", params, limit, page_token)

        return await run_tool("huntress_agents_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_agents_get(id: RecordId) -> str:
        """Get one agent's details, including Defender / EDR state and isolation status."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"agents/{id}"), "agent")

        return await run_tool("huntress_agents_get", client_factory, action)
