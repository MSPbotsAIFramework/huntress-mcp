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
"""Organizations: the MSP's clients in Huntress."""

from typing import Annotated, Any

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
    PageToken,
    RecordId,
    compact,
    list_page,
    not_confirmed,
    run_tool,
    unwrap,
)

Key = Annotated[str, Field(description="Organization key used when deploying agents (letters, digits, dashes).", min_length=1)]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_organizations_list(limit: Limit = None, page_token: PageToken = None) -> str:
        """List organizations (clients) with key, agent / identity counts and creation date."""

        async def action(client: HuntressClient) -> dict:
            return await list_page(client, "organizations", "organizations", {}, limit, page_token)

        return await run_tool("huntress_organizations_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_organizations_get(id: RecordId) -> str:
        """Get one organization with its report recipients and counts."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"organizations/{id}"), "organization")

        return await run_tool("huntress_organizations_get", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def huntress_organizations_create(
        name: Annotated[str, Field(description="Organization name.", min_length=1)],
        key: Key,
    ) -> str:
        """Create an organization (client) to deploy agents into. Only when the user explicitly asks."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.post("organizations", {"name": name, "key": key}), "organization")

        return await run_tool("huntress_organizations_create", client_factory, action)

    @mcp.tool(annotations=WRITES_IDEMPOTENT)
    async def huntress_organizations_update(
        id: RecordId,
        name: Annotated[str | None, Field(description="New name.")] = None,
        key: Annotated[str | None, Field(description="New organization key (agents deployed with the old key keep working).")] = None,
        report_recipients: Annotated[list[str] | None, Field(description="Emails that receive reports (replaces the list).")] = None,
    ) -> str:
        """Change an organization's name, key or report recipients. Only when the user explicitly asks."""

        async def action(client: HuntressClient) -> Any:
            body = compact({"name": name, "key": key, "report_recipients": report_recipients})
            if not body:
                raise ValueError("Nothing to update: pass at least one field to change.")
            return unwrap(await client.patch(f"organizations/{id}", body), "organization")

        return await run_tool("huntress_organizations_update", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def huntress_organizations_delete(
        id: RecordId,
        revoke_key: Annotated[bool | None, Field(description="Also revoke the organization key, breaking deployment scripts that use it.")] = None,
        confirm: Confirm = None,
    ) -> str:
        """Delete an organization and stop protecting its endpoints. Irreversible; needs confirm: true.

        Only when the user explicitly asks for that organization.
        """

        async def action(client: HuntressClient) -> Any:
            if confirm is not True:
                return not_confirmed(f"Delete organization {id}{' and revoke its key' if revoke_key else ''}")
            await client.delete(f"organizations/{id}", {"revoke_key": True if revoke_key else None})
            return {"done": True, "deleted_organization_id": id}

        return await run_tool("huntress_organizations_delete", client_factory, action)
