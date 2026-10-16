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
"""The account the API key belongs to, and the calling actor."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..api_client import HuntressClient
from ._common import READ_ONLY, ClientFactory, run_tool, unwrap


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def huntress_accounts_get() -> str:
        """Get the Huntress account of the API key: name, subdomain, status, addresses and settings."""

        async def action(client: HuntressClient) -> Any:
            return unwrap(await client.get("account"), "account")

        return await run_tool("huntress_accounts_get", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def huntress_accounts_actor() -> str:
        """Get who is calling: the account, user and (for resellers) reseller behind the API key."""

        async def action(client: HuntressClient) -> Any:
            return await client.get("actor")

        return await run_tool("huntress_accounts_actor", client_factory, action)
