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
"""Shared argument types, list / record helpers, confirmation and the error-handling wrapper."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import HuntressClient, HuntressError
from ..config import DEFAULT_LIMIT, MAX_LIMIT

logger = logging.getLogger("huntress_mcp.tools")

ClientFactory = Callable[[], HuntressClient | None]

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
LOCAL = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
WRITES_IDEMPOTENT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured", "Huntress credentials are missing for this request (X-Huntress-Api-Key, X-Huntress-Api-Secret).", False
)

RecordId = Annotated[int, Field(description="Numeric Huntress id.", ge=1)]
OrganizationFilter = Annotated[int | None, Field(description="Only this organization id.", ge=1)]
Limit = Annotated[int | None, Field(description=f"Records per page (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).", ge=1, le=MAX_LIMIT)]
PageToken = Annotated[str | None, Field(description="next_page_token from the previous page.")]
Confirm = Annotated[bool | None, Field(description="Must be true, set only after the user approved this exact action.")]


def compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def unwrap(payload: Any, key: str) -> Any:
    """Huntress wraps single records as {"agent": {...}}; return the record itself."""
    if isinstance(payload, dict) and key in payload and len(payload) == 1:
        return payload[key]
    return payload


async def list_page(client: HuntressClient, path: str, key: str, params: dict[str, Any], limit: int | None, page_token: str | None) -> dict:
    """GET a list endpoint and return {<key>, count, has_more, next_page_token}."""
    payload = await client.get(path, compact(params) | compact({"limit": limit or DEFAULT_LIMIT, "page_token": page_token}))
    items = payload.get(key) if isinstance(payload, dict) else payload
    items = items if isinstance(items, list) else []
    paging = payload.get("pagination") if isinstance(payload, dict) else None
    token = paging.get("next_page_token") if isinstance(paging, dict) else None
    return compact({key: items, "count": len(items), "has_more": bool(token), "next_page_token": token or None})


def not_confirmed(action: str) -> dict:
    return {
        "done": False,
        "action": action,
        "message": "Not done. Describe this action to the user and call again with confirm: true only after they approve it.",
    }


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[HuntressClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    started = time.monotonic()
    try:
        result = await action(client)
    except HuntressError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    if result is None:
        result = {"done": True}
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
