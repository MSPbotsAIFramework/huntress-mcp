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
"""tools/list snapshot and error-envelope mapping. No network access."""

import asyncio
import json

import pytest

from huntress_mcp.api_client import HuntressError
from huntress_mcp.server import INSTRUCTIONS, create_mcp_server
from huntress_mcp.tools.navigation import DOMAINS

ID = {"id"}
INCIDENT = {"incident_report_id"}

# Tool names are a public contract: existing agents and tenant connections
# depend on them. Changing this snapshot is a breaking change.
EXPECTED_TOOLS: dict[str, set[str]] = {
    "huntress_navigate": {"domain"},
    "huntress_status": set(),
    "huntress_accounts_get": set(),
    "huntress_accounts_actor": set(),
    "huntress_agents_list": set(),
    "huntress_agents_get": ID,
    "huntress_incidents_list": set(),
    "huntress_incidents_get": ID,
    "huntress_incidents_resolve": ID,
    "huntress_incidents_remediations": INCIDENT,
    "huntress_incidents_remediation_get": INCIDENT | {"remediation_id"},
    "huntress_incidents_bulk_approve": INCIDENT,
    "huntress_incidents_bulk_reject": INCIDENT | {"comment"},
    "huntress_escalations_list": set(),
    "huntress_escalations_get": ID,
    "huntress_escalations_resolve": ID,
    "huntress_organizations_list": set(),
    "huntress_organizations_get": ID,
    "huntress_organizations_create": {"name", "key"},
    "huntress_organizations_update": ID,
    "huntress_organizations_delete": ID,
    "huntress_signals_list": set(),
    "huntress_signals_get": ID,
    "huntress_users_list": set(),
    "huntress_users_get": ID,
    "huntress_users_create": {"email", "first_name", "last_name", "permissions"},
    "huntress_users_update": ID | {"permissions"},
    "huntress_users_delete": ID,
    "huntress_billing_reports_list": set(),
    "huntress_billing_reports_get": ID,
    "huntress_summary_reports_list": set(),
    "huntress_summary_reports_get": ID,
}
READ_TOOLS = {
    n
    for n in EXPECTED_TOOLS
    if n.endswith(("_list", "_get", "_actor", "_remediations", "_remediation_get")) or n in {"huntress_navigate", "huntress_status"}
}
CONFIRM_TOOLS = {"huntress_incidents_bulk_approve", "huntress_organizations_delete", "huntress_users_update", "huntress_users_delete"}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_tool_names_are_stable(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_description_budget(tools, name):
    description = (tools[name].description or "").strip()
    assert description, f"{name} has no description"
    assert len(description) <= 500
    assert len(description.splitlines()[0]) <= 100


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations_match_side_effects(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    assert annotations.readOnlyHint is (name in READ_TOOLS)
    assert bool(annotations.destructiveHint) is (name in CONFIRM_TOOLS)


@pytest.mark.parametrize("name", sorted(set(EXPECTED_TOOLS) - READ_TOOLS))
def test_write_tools_say_when_to_use_them(tools, name):
    assert "explicitly ask" in tools[name].description


@pytest.mark.parametrize("name", sorted(CONFIRM_TOOLS))
def test_destructive_tools_take_confirm(tools, name):
    assert "confirm" in tools[name].inputSchema["properties"]


def test_navigate_lists_every_tool():
    listed = {tool for _, names in DOMAINS.values() for tool in names}
    assert listed | {"huntress_navigate", "huntress_status"} == set(EXPECTED_TOOLS)


def test_instructions_budget():
    assert len(INSTRUCTIONS) <= 1500


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (0, "upstream_error", True),
    ],
)
def test_error_envelope(status, code, retryable):
    envelope = json.loads(HuntressError(status, "boom").to_envelope())
    assert envelope == {"error": {"code": code, "message": "boom", "retryable": retryable}}


def test_tool_without_credentials_returns_not_configured():
    content, _ = asyncio.run(create_mcp_server().call_tool("huntress_agents_list", {}))
    assert json.loads(content[0].text)["error"]["code"] == "not_configured"
