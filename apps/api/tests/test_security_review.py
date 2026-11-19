"""Independent review regressions for authentication and configuration boundaries."""

from uuid import uuid4

import pytest
from insightrag.core.config import Settings
from insightrag.security.context import AccessContext, SecurityError
from insightrag.security.dependencies import prepare_policy_write, record_own_policy_change
from insightrag.security.routes import check_upload_content_length
from insightrag.security.uploads import MAX_FILE_BYTES
from pydantic import ValidationError
from starlette.requests import Request


def test_configured_upload_limit_cannot_exceed_validator_capacity():
    # A too-large setting otherwise makes every upload fail with an unhandled
    # ValueError; reject invalid deployment configuration before serving traffic.
    with pytest.raises(ValidationError):
        Settings(_env_file=None, upload_max_bytes=MAX_FILE_BYTES + 1)


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("GET", "/me", None),
        ("GET", "/workspaces", None),
        ("GET", "/directory/memberships", None),
        ("GET", "/directory/groups", None),
        ("GET", "/directory/roles", None),
        ("POST", "/workspaces/{id}/resources", {"kind": "document", "title": "synthetic"}),
        ("GET", "/resources/{id}", None),
        ("GET", "/datasets/{id}/rows", None),
        ("GET", "/documents/{id}/evidence", None),
        ("POST", "/resources/{id}/grants", {"user_id": str(uuid4()), "action": "read"}),
        ("DELETE", "/resources/{id}/grants/{other}", None),
        ("DELETE", "/resources/{id}", None),
        ("GET", "/jobs/{id}", None),
        ("GET", "/audit-events", None),
        ("POST", "/resources/{id}/validate-upload", None),
    ],
)
def test_each_enterprise_route_requires_authentication_before_data_access(
    client, method, path, payload
):
    actual_path = "/api/v1" + path.format(id=uuid4(), other=uuid4())
    response = client.request(
        method,
        actual_path,
        json=payload,
        headers={"X-Organization-ID": str(uuid4()), "X-Filename": "synthetic.txt"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("value", [None, "0", "00012", "100"])
def test_content_length_accepts_bounded_ascii_decimal(value):
    check_upload_content_length(value, 100)


@pytest.mark.parametrize("value", ["", "-1", "1e9", "9" * 5000, "²", "101"])
def test_content_length_rejects_malformed_or_oversized_values(value):
    with pytest.raises(SecurityError) as error:
        check_upload_content_length(value, 100)
    assert error.value.status == 413


class RevisionSession:
    def __init__(self, *revisions):
        self.revisions = list(revisions)

    async def scalar(self, query, parameters):
        return self.revisions.pop(0)


def write_context():
    return AccessContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        role="steward",
        clearance=1,
        mfa=False,
        policy_revision=7,
        request_id=str(uuid4()),
    )


@pytest.mark.asyncio
async def test_policy_mutation_rejects_revision_changed_before_lock():
    request = Request({"type": "http", "state": {}})
    with pytest.raises(SecurityError) as error:
        await prepare_policy_write(request, RevisionSession(8), write_context())
    assert error.value.status == 409
    assert not getattr(request.state, "policy_write_locked", False)


@pytest.mark.asyncio
async def test_policy_mutation_records_own_change_only_after_preflight():
    request = Request({"type": "http", "state": {}})
    context = write_context()
    session = RevisionSession(7, 8)
    await prepare_policy_write(request, session, context)
    assert request.state.expected_policy_revision == 7
    assert await record_own_policy_change(request, session, context) == 8
    assert request.state.expected_policy_revision == 8


@pytest.mark.asyncio
async def test_policy_mutation_cannot_adopt_revision_without_lock():
    request = Request({"type": "http", "state": {}})
    with pytest.raises(SecurityError) as error:
        await record_own_policy_change(request, RevisionSession(), write_context())
    assert error.value.code == "security_invariant_error"
