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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import re
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from ._arguments import EnvelopeFastMCP
from .api_client import HuntressClient, HuntressCredentials
from .config import Settings

HEADER_API_KEY = "X-Huntress-Api-Key"
HEADER_API_SECRET = "X-Huntress-Api-Secret"
REQUIRED_HEADERS = [HEADER_API_KEY, HEADER_API_SECRET]

_PLACEHOLDER = re.compile(r"^\$\{.*\}$")

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[HuntressCredentials | None] = contextvars.ContextVar(
    "huntress_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("huntress_request_id", default="-")

INSTRUCTIONS = (
    "Huntress is a managed security (EDR / ITDR / SIEM) platform: its SOC "
    "watches the MSP's organizations (clients) and their agents (protected "
    "endpoints) and 365 identities, and reports threats as incident reports "
    "with remediations to approve, escalations that need a partner decision, "
    "and signals (investigated detections).\n"
    "Usage:\n"
    "- Triage: huntress_incidents_list(status='sent', severity='critical') -> "
    "huntress_incidents_get -> huntress_incidents_remediations.\n"
    "- Escalations awaiting a decision: huntress_escalations_list -> "
    "huntress_escalations_get.\n"
    "- Organizations give organization_id for every filter; agents carry "
    "hostname, platform and versions.\n"
    "- Lists page with limit (max 500) and page_token (next_page_token of the "
    "previous page).\n"
    "Resolving incidents or escalations, rejecting remediations and creating "
    "or changing organizations and users act on the live account: call them "
    "only when the user explicitly asks. Approving remediations (they run on "
    "endpoints), changing user permissions and deletes also need confirm: "
    "true after the user approved that exact action. The API allows about 60 "
    "requests per minute."
)


def get_client_from_context() -> HuntressClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return HuntressClient(credentials)


def _clean(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text or _PLACEHOLDER.match(text):
        return None
    return text


class GatewayCredentialsMiddleware:
    """Reads the Huntress key pair on /mcp requests into the request context; 401 when missing."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        api_key = _clean(request.headers.get(HEADER_API_KEY))
        api_secret = _clean(request.headers.get(HEADER_API_SECRET))
        if not (api_key and api_secret):
            missing = [h for h, v in ((HEADER_API_KEY, api_key), (HEADER_API_SECRET, api_secret)) if not v]
            await JSONResponse(
                {"error": "Missing credentials", "message": f"Missing header(s): {', '.join(missing)}", "required_headers": REQUIRED_HEADERS},
                status_code=401,
            )(scope, receive, send)
            return

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(HuntressCredentials(api_key, api_secret))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = EnvelopeFastMCP(
        name="huntress-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], HuntressClient | None] = get_client_from_context

    from .tools import accounts, agents, billing, incidents, navigation, organizations, signals, users

    for module in (navigation, accounts, agents, incidents, organizations, signals, users, billing):
        module.register(mcp, client_factory)

    return mcp
