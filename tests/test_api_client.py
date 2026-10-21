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
"""Request shapes, retries and tool behaviour against a mocked Huntress API."""

import base64
import json

import httpx
import pytest

from huntress_mcp import api_client
from huntress_mcp.api_client import HuntressClient, HuntressCredentials, HuntressError
from huntress_mcp.server import _credentials_var, create_mcp_server

CREDS = HuntressCredentials("key-123", "secret-456")


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


class Recorder:
    """Mock transport: replies by method + path below /v1/."""

    def __init__(self, routes=None, default=None):
        self.requests: list[httpx.Request] = []
        self.routes = routes or {}
        self.default = default if default is not None else {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v1/")
        reply = self.routes.get(f"{request.method} {path}", self.routes.get(path, self.default))
        if callable(reply):
            return reply(request)
        return httpx.Response(200, json=reply)

    def calls(self, path: str, method: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == f"/v1/{path}" and (method is None or r.method == method)]


def body(request: httpx.Request):
    return json.loads(request.content) if request.content else None


async def _call(monkeypatch, recorder: Recorder, tool: str, args: dict):
    http = httpx.AsyncClient(transport=httpx.MockTransport(recorder))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    ctx = _credentials_var.set(CREDS)
    try:
        content, _ = await create_mcp_server().call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


def _client(recorder: Recorder) -> HuntressClient:
    return HuntressClient(CREDS, httpx.AsyncClient(transport=httpx.MockTransport(recorder)))


# ---- client ----------------------------------------------------------------


async def test_basic_auth_and_base_url():
    rec = Recorder({"agents": {"agents": []}})
    await _client(rec).get("agents", {"platform": "windows"})
    request = rec.requests[0]
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"key-123:secret-456").decode()
    assert str(request.url) == "https://api.huntress.io/v1/agents?platform=windows"


async def test_get_retries_5xx_but_writes_do_not():
    replies = iter([httpx.Response(502), httpx.Response(200, json={"agents": []})])
    rec = Recorder({"GET agents": lambda r: next(replies), "POST organizations": lambda r: httpx.Response(500, json={})})
    client = _client(rec)
    await client.get("agents")
    with pytest.raises(HuntressError):
        await client.post("organizations", {})
    assert len(rec.calls("agents", "GET")) == 2 and len(rec.calls("organizations", "POST")) == 1


async def test_429_is_retried_for_writes():
    replies = iter([httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(201, json={"organization": {"id": 1}})])
    rec = Recorder({"POST organizations": lambda r: next(replies)})
    assert await _client(rec).post("organizations", {"name": "A", "key": "a"}) == {"organization": {"id": 1}}
    assert len(rec.requests) == 2


async def test_errors_are_readable(monkeypatch):
    rec = Recorder({"POST organizations": lambda r: httpx.Response(422, json={"error": "key has already been taken"})})
    result = await _call(monkeypatch, rec, "huntress_organizations_create", {"name": "Example", "key": "example"})
    assert result["error"]["code"] == "invalid_argument"
    assert "key has already been taken" in result["error"]["message"]


async def test_unauthorized_maps_to_envelope(monkeypatch):
    rec = Recorder({"account": lambda r: httpx.Response(401, json={"error": "Unauthorized"})})
    result = await _call(monkeypatch, rec, "huntress_status", {})
    assert result["error"]["code"] == "unauthorized" and result["error"]["retryable"] is False


async def test_html_error_pages_are_not_echoed(monkeypatch):
    rec = Recorder({"agents/1": lambda r: httpx.Response(404, text="<html><body>Not Found</body></html>")})
    result = await _call(monkeypatch, rec, "huntress_agents_get", {"id": 1})
    assert result["error"]["message"] == "Huntress returned HTTP 404 for agents/1"


# ---- lists -----------------------------------------------------------------


async def test_list_paging_and_filters(monkeypatch):
    payload = {"incident_reports": [{"id": i} for i in range(3)], "pagination": {"next_page_token": "tok2"}}
    rec = Recorder({"incident_reports": payload})
    args = {"limit": 3, "status": "sent", "severity": "critical", "organization_id": 9}
    result = await _call(monkeypatch, rec, "huntress_incidents_list", args)
    params = rec.requests[0].url.params
    assert (params["limit"], params["status"], params["severity"], params["organization_id"]) == ("3", "sent", "critical", "9")
    assert (result["count"], result["has_more"], result["next_page_token"]) == (3, True, "tok2")


async def test_last_page_has_no_token(monkeypatch):
    rec = Recorder({"agents": {"agents": [{"id": 1}], "pagination": {"next_page_token": None}}})
    result = await _call(monkeypatch, rec, "huntress_agents_list", {"page_token": "tok2"})
    assert rec.requests[0].url.params["page_token"] == "tok2"
    assert rec.requests[0].url.params["limit"] == "10"
    assert result == {"agents": [{"id": 1}], "count": 1, "has_more": False}


@pytest.mark.parametrize(
    "tool,args,path,key",
    [
        ("huntress_billing_reports_list", {"status": "paid"}, "invoices", "invoices"),
        ("huntress_summary_reports_list", {"type": "monthly_summary"}, "reports", "reports"),
        ("huntress_users_list", {}, "memberships", "memberships"),
        ("huntress_organizations_list", {}, "organizations", "organizations"),
        ("huntress_signals_list", {"statuses": "reported"}, "signals", "signals"),
        ("huntress_escalations_list", {}, "escalations", "escalations"),
        ("huntress_incidents_remediations", {"incident_report_id": 5}, "incident_reports/5/remediations", "remediations"),
    ],
)
async def test_list_paths(monkeypatch, tool, args, path, key):
    rec = Recorder({path: {key: [{"id": 1}]}})
    result = await _call(monkeypatch, rec, tool, args)
    assert rec.calls(path, "GET")
    assert result[key] == [{"id": 1}]


# ---- records ---------------------------------------------------------------


@pytest.mark.parametrize(
    "tool,args,path,key",
    [
        ("huntress_accounts_get", {}, "account", "account"),
        ("huntress_agents_get", {"id": 4}, "agents/4", "agent"),
        ("huntress_incidents_get", {"id": 5}, "incident_reports/5", "incident_report"),
        ("huntress_incidents_remediation_get", {"incident_report_id": 5, "remediation_id": 6}, "incident_reports/5/remediations/6", "remediation"),
        ("huntress_escalations_get", {"id": 7}, "escalations/7", "escalation"),
        ("huntress_organizations_get", {"id": 8}, "organizations/8", "organization"),
        ("huntress_signals_get", {"id": 9}, "signals/9", "signal"),
        ("huntress_users_get", {"id": 10}, "memberships/10", "membership"),
        ("huntress_billing_reports_get", {"id": 11}, "invoices/11", "invoice"),
        ("huntress_summary_reports_get", {"id": 12}, "reports/12", "report"),
    ],
)
async def test_get_unwraps_record(monkeypatch, tool, args, path, key):
    rec = Recorder({path: {key: {"id": 1, "name": "x"}}})
    assert await _call(monkeypatch, rec, tool, args) == {"id": 1, "name": "x"}


async def test_organization_create_and_update(monkeypatch):
    rec = Recorder({"POST organizations": {"organization": {"id": 3}}, "PATCH organizations/3": {"organization": {"id": 3}}})
    await _call(monkeypatch, rec, "huntress_organizations_create", {"name": "Example", "key": "example"})
    assert body(rec.calls("organizations", "POST")[0]) == {"name": "Example", "key": "example"}
    await _call(monkeypatch, rec, "huntress_organizations_update", {"id": 3, "report_recipients": ["it@example.com"]})
    assert body(rec.calls("organizations/3", "PATCH")[0]) == {"report_recipients": ["it@example.com"]}


async def test_update_without_fields_is_rejected(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "huntress_organizations_update", {"id": 3})
    assert result["error"]["code"] == "invalid_argument" and rec.requests == []


async def test_user_create_body(monkeypatch):
    rec = Recorder({"POST memberships": {"membership": {"id": 1}}})
    args = {"email": "a@example.com", "first_name": "A", "last_name": "B", "permissions": "Read-only", "organization_id": 9}
    await _call(monkeypatch, rec, "huntress_users_create", args)
    assert body(rec.requests[0]) == args


async def test_resolve_incident_and_escalation(monkeypatch):
    rec = Recorder()
    await _call(monkeypatch, rec, "huntress_incidents_resolve", {"id": 5})
    await _call(monkeypatch, rec, "huntress_escalations_resolve", {"id": 7, "determination": "expected", "scope": "identity"})
    assert rec.calls("incident_reports/5/resolution", "POST")
    assert body(rec.calls("escalations/7/resolution", "POST")[0]) == {"determination": "expected", "scope": "identity"}


async def test_bulk_reject_defaults_useful_to_false(monkeypatch):
    rec = Recorder()
    result = await _call(monkeypatch, rec, "huntress_incidents_bulk_reject", {"incident_report_id": 5, "comment": "Approved app"})
    assert body(rec.requests[0]) == {"comment": "Approved app", "useful": False}
    assert rec.calls("incident_reports/5/remediations/bulk_rejection", "POST") and result["done"] is True


@pytest.mark.parametrize(
    "tool,args,method,path",
    [
        ("huntress_incidents_bulk_approve", {"incident_report_id": 5}, "POST", "incident_reports/5/remediations/bulk_approval"),
        ("huntress_organizations_delete", {"id": 8}, "DELETE", "organizations/8"),
        ("huntress_users_update", {"id": 10, "permissions": "Admin"}, "PATCH", "memberships/10"),
        ("huntress_users_delete", {"id": 10}, "DELETE", "memberships/10"),
    ],
)
async def test_destructive_tools_need_confirm(monkeypatch, tool, args, method, path):
    rec = Recorder()
    result = await _call(monkeypatch, rec, tool, args)
    assert result["done"] is False and rec.requests == []
    await _call(monkeypatch, rec, tool, args | {"confirm": True})
    assert rec.calls(path, method)


async def test_organization_delete_revoke_key_is_a_query_param(monkeypatch):
    rec = Recorder()
    await _call(monkeypatch, rec, "huntress_organizations_delete", {"id": 8, "revoke_key": True, "confirm": True})
    assert rec.requests[0].url.params["revoke_key"] == "true"


async def test_bulk_approve_manual_ids(monkeypatch):
    rec = Recorder()
    await _call(monkeypatch, rec, "huntress_incidents_bulk_approve", {"incident_report_id": 5, "manual_completion_remediation_ids": [1, 2], "confirm": True})
    assert body(rec.requests[0]) == {"manual_completion_remediation_ids": [1, 2]}


async def test_status_and_navigate(monkeypatch):
    rec = Recorder({"account": {"account": {"id": 1, "name": "Example MSP"}}})
    result = await _call(monkeypatch, rec, "huntress_status", {})
    assert result["connected"] is True and result["account"] == "Example MSP"
    nav = await _call(monkeypatch, Recorder(), "huntress_navigate", {"domain": "billing"})
    assert "huntress_billing_reports_list" in nav["tools"]


async def test_large_limits_are_capped(monkeypatch):
    rec = Recorder({"agents": {"agents": [], "pagination": {"next_page_token": None}}})
    await _call(monkeypatch, rec, "huntress_agents_list", {"limit": 500})
    assert rec.requests[0].url.params["limit"] == "200"


# ---- compatibility: enum params accept any casing (normalized) and unknown values (passed through)


@pytest.mark.parametrize(
    "tool,args,expected",
    [
        ("huntress_summary_reports_list", {"type": "Monthly_Summary"}, {"type": "monthly_summary"}),
        ("huntress_summary_reports_list", {"type": "weekly_summary"}, {"type": "weekly_summary"}),
        (
            "huntress_incidents_list",
            {"status": "CLOSED", "severity": "Critical", "platform": "Microsoft_365"},
            {"status": "closed", "severity": "critical", "platform": "microsoft_365"},
        ),
        (
            "huntress_incidents_list",
            {"status": "investigating", "severity": "medium", "platform": "ios"},
            {"status": "investigating", "severity": "medium", "platform": "ios"},
        ),
        ("huntress_signals_list", {"entity_type": "Mailbox"}, {"entity_type": "mailbox"}),
        ("huntress_signals_list", {"entity_type": "device"}, {"entity_type": "device"}),
    ],
)
async def test_enum_params_normalized_or_passed_through(monkeypatch, tool, args, expected):
    rec = Recorder()
    result = await _call(monkeypatch, rec, tool, args)
    assert "error" not in result
    params = rec.requests[0].url.params
    assert {key: params[key] for key in expected} == expected
