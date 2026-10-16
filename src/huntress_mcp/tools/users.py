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
"""Users: people with access to the Huntress account (memberships)."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import HuntressClient
from ._common import (
    DESTRUCTIVE,
    READ_ONLY,
    WRITES,
    ClientFactory,
    Confirm,
    Limit,
    OrganizationFilter,
    PageToken,
    RecordId,
    compact,
    list_page,
    not_confirmed,
    run_tool,
    unwrap,
)

Permission = Literal["Admin", "Security Engineer", "User", "Read-only", "Finance", "Marketing", "Provisioner"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_users_list(limit: Limit = None, page_token: PageToken = None, organization_id: OrganizationFilter = None) -> str:
        """List users with access (memberships): name, email, permission level and organization scope."""

        async def action(client: HuntressClient) -> dict:
            return await list_page(client, "memberships", "memberships", {"organization_id": organization_id}, limit, page_token)

        return await run_tool("huntress_users_list", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_users_get(id: RecordId) -> str:
        """Get one user membership."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get(f"memberships/{id}"), "membership")

        return await run_tool("huntress_users_get", client_factory, action)

    @mcp.tool(annotations=WRITES)
    async def huntress_users_create(
        email: Annotated[str, Field(description="User email; Huntress sends an invitation.", min_length=3)],
        first_name: Annotated[str, Field(description="First name.", min_length=1)],
        last_name: Annotated[str, Field(description="Last name.", min_length=1)],
        permissions: Annotated[Permission, Field(description="Permission level.")],
        organization_id: Annotated[int | None, Field(description="Limit the user to this organization; omit for the whole account.", ge=1)] = None,
    ) -> str:
        """Invite a user, account-wide or to one organization. Only when the user explicitly asks."""

        async def action(client: HuntressClient) -> Any:
            body = compact(
                {"email": email, "first_name": first_name, "last_name": last_name, "permissions": permissions, "organization_id": organization_id}
            )
            return unwrap(await client.post("memberships", body), "membership")

        return await run_tool("huntress_users_create", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def huntress_users_update(
        id: RecordId,
        permissions: Annotated[Permission, Field(description="New permission level.")],
        confirm: Confirm = None,
    ) -> str:
        """Change a user's permission level (e.g. to Admin). Only when explicitly asked; needs confirm: true."""

        async def action(client: HuntressClient) -> Any:
            if confirm is not True:
                return not_confirmed(f"Change user {id} to {permissions}")
            return unwrap(await client.patch(f"memberships/{id}", {"permissions": permissions}), "membership")

        return await run_tool("huntress_users_update", client_factory, action)

    @mcp.tool(annotations=DESTRUCTIVE)
    async def huntress_users_delete(id: RecordId, confirm: Confirm = None) -> str:
        """Remove a user's access to the account. Needs confirm: true. Only when the user explicitly asks."""

        async def action(client: HuntressClient) -> Any:
            if confirm is not True:
                return not_confirmed(f"Remove user membership {id}")
            await client.delete(f"memberships/{id}")
            return {"done": True, "deleted_membership_id": id}

        return await run_tool("huntress_users_delete", client_factory, action)
