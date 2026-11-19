"""Real RSA credentials exercise verification; no issuer or tenant data is fabricated as live."""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import FrozenInstanceError, dataclass
from time import time
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from insightrag.security import auth
from insightrag.security.auth import (
    AuthenticationError,
    AuthenticationUnavailable,
    OIDCVerifier,
    Principal,
)

ISSUER = "https://issuer.example.test/tenant"
AUDIENCE = "insightrag-api"
JWKS_URL = "https://keys.example.test/registered-jwks"


@dataclass
class SigningKey:
    private: rsa.RSAPrivateKey
    jwk: dict[str, Any]


def make_key(kid: str, size: int = 2048) -> SigningKey:
    private = rsa.generate_private_key(public_exponent=65537, key_size=size)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid=kid, alg="RS256", use="sig", key_ops=["verify"])
    return SigningKey(private, jwk)


@pytest.fixture(scope="module")
def key() -> SigningKey:
    return make_key("key-1")


@pytest.fixture(scope="module")
def other_key() -> SigningKey:
    return make_key("key-2")


def payload(**changes: Any) -> dict[str, Any]:
    now = int(time())
    return {
        "iss": ISSUER,
        "sub": "synthetic-subject",
        "aud": AUDIENCE,
        "iat": now,
        "nbf": now - 1,
        "exp": now + 600,
        **changes,
    }


def credential(
    key: SigningKey,
    *,
    claims: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
    omit: tuple[str, ...] = (),
) -> str:
    values = payload(**(claims or {}))
    for name in omit:
        values.pop(name, None)
    return jwt.encode(
        values,
        key.private,
        algorithm="RS256",
        headers={"kid": key.jwk["kid"], "typ": "at+jwt", **(headers or {})},
    )


def verifier(key: SigningKey, **kwargs: Any) -> OIDCVerifier:
    return OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, jwks={"keys": [key.jwk]}, **kwargs)


async def test_valid_rsa_principal_ignores_token_tenant_roles_and_freezes_identity(key: SigningKey):
    issued_at = int(time())
    token = credential(
        key, claims={"iat": issued_at, "tenant_id": "other-organization", "roles": ["owner"]}
    )
    principal = await verifier(key).verify(token)
    assert principal == Principal(ISSUER, "synthetic-subject", issued_at, False)
    assert not hasattr(principal, "tenant_id")
    assert not hasattr(principal, "roles")
    with pytest.raises(FrozenInstanceError):
        principal.subject = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "change",
    [
        {"iss": ISSUER + "/other"},
        {"iss": "https://issuer.example.test"},
        {"aud": "another-api"},
        {"aud": ["another-api"]},
        {"aud": []},
        {"aud": [AUDIENCE, 5]},
        {"sub": ""},
        {"sub": "subject\x00suffix"},
        {"sub": "subject\ud800suffix"},
        {"sub": "s" * 256},
        {"exp": int(time()) - 90},
        {"iat": int(time()) + 120},
        {"nbf": int(time()) + 120},
        {"exp": int(time()) + 7200},
        {"exp": -1},
        {"iat": True},
        {"nbf": False},
        {"exp": str(int(time()) + 600)},
        {"amr": "mfa"},
        {"amr": ["mfa", 10]},
        {"amr": ["pwd"] * 21},
        {"auth_time": True},
        {"auth_time": None},
        {"auth_time": int(time()) + 120},
        {"auth_time": -1},
    ],
)
async def test_invalid_verified_claims_are_denied(key: SigningKey, change: dict[str, Any]):
    with pytest.raises(AuthenticationError, match="Invalid access token"):
        await verifier(key).verify(credential(key, claims=change))


@pytest.mark.parametrize("name", ["iss", "sub", "aud", "exp", "iat", "nbf"])
async def test_required_claim_cannot_be_omitted(key: SigningKey, name: str):
    with pytest.raises(AuthenticationError):
        await verifier(key).verify(credential(key, omit=(name,)))


async def test_signature_wrong_key_is_denied(key: SigningKey, other_key: SigningKey):
    forged = credential(other_key, headers={"kid": key.jwk["kid"]})
    with pytest.raises(AuthenticationError):
        await verifier(key).verify(forged)


@pytest.mark.parametrize(
    "headers",
    [
        {"typ": "JWT"},
        {"typ": "application/at+jwt"},
        {"kid": "k" * 129},
        {"kid": ""},
        {"kid": "control\nvalue"},
        {"jku": "http://169.254.169.254/latest/meta-data"},
        {"x5u": "https://attacker.example.test/key"},
        {"jwk": {"kty": "RSA"}},
        {"x5c": ["untrusted"]},
        {"crit": ["unrecognized"]},
        {"b64": False},
    ],
)
async def test_unsupported_headers_are_rejected_before_network(
    key: SigningKey, headers: dict[str, Any]
):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"keys": [key.jwk]})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=True
    ) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        with pytest.raises(AuthenticationError):
            await instance.verify(credential(key, headers=headers))
    assert calls == []


async def test_none_and_hmac_algorithm_confusion_are_denied(key: SigningKey):
    for algorithm in ("none", "HS256"):
        token = jwt.encode(
            payload(),
            "synthetic-hmac-secret-for-negative-testing-only" if algorithm == "HS256" else "",
            algorithm=algorithm,
            headers={"typ": "at+jwt", "kid": key.jwk["kid"]},
        )
        with pytest.raises(AuthenticationError):
            await verifier(key).verify(token)


@pytest.mark.parametrize("token", ["", "x" * 8193, "a.b.c.d", "onepart", "é.a.b"])
async def test_malformed_or_oversized_token_is_denied(key: SigningKey, token: str):
    with pytest.raises(AuthenticationError):
        await verifier(key).verify(token)


async def test_duplicate_json_member_and_nonfinite_number_are_denied(key: SigningKey):
    def encoded(value: str) -> str:
        return base64.urlsafe_b64encode(value.encode()).rstrip(b"=").decode()

    for raw in ('{"sub":"one","sub":"two"}', '{"number":NaN}'):
        token = ".".join(
            (encoded('{"alg":"RS256","typ":"at+jwt","kid":"key-1"}'), encoded(raw), "x")
        )
        with pytest.raises(AuthenticationError):
            await verifier(key).verify(token)


async def test_fresh_mfa_requires_verified_auth_time_not_refreshed_iat(key: SigningKey):
    now = int(time())
    fresh = await verifier(key).verify(
        credential(key, claims={"amr": ["pwd", "mfa"], "auth_time": now - 30})
    )
    assert fresh.mfa is True
    assert fresh.authenticated_at == now - 30
    old = await verifier(key).verify(
        credential(key, claims={"amr": ["mfa"], "auth_time": now - 1000, "iat": now})
    )
    assert old.mfa is False
    assert old.authenticated_at == now - 1000
    missing = await verifier(key).verify(credential(key, claims={"amr": ["mfa"]}))
    assert missing.mfa is False
    no_method = await verifier(key).verify(credential(key, claims={"auth_time": now - 10}))
    assert no_method.mfa is False


async def test_multiple_audiences_include_registered_api(key: SigningKey):
    principal = await verifier(key).verify(
        credential(key, claims={"aud": [AUDIENCE, "another-api"]})
    )
    assert principal.subject == "synthetic-subject"


@pytest.mark.parametrize(("age", "expected"), [(300, True), (301, False)])
async def test_mfa_freshness_boundary_is_explicit(
    key: SigningKey, monkeypatch: pytest.MonkeyPatch, age: int, expected: bool
):
    now = int(time())
    monkeypatch.setattr(auth, "time", lambda: now)
    principal = await verifier(key).verify(
        credential(key, claims={"amr": ["mfa"], "auth_time": now - age})
    )
    assert principal.mfa is expected


async def test_live_jwks_is_fixed_cached_and_injected_client_remains_owned_by_caller(
    key: SigningKey,
):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert str(request.url) == JWKS_URL
        assert "authorization" not in request.headers
        assert request.headers["accept-encoding"] == "identity"
        return httpx.Response(200, json={"keys": [key.jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        for _ in range(3):
            assert (await instance.verify(credential(key))).issuer == ISSUER
        await instance.close()
        assert not client.is_closed
        with pytest.raises(AuthenticationUnavailable):
            await instance.verify(credential(key))
    assert len(calls) == 1


async def test_owned_http_client_is_closed(key: SigningKey, monkeypatch: pytest.MonkeyPatch):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [key.jwk]}))
    owned_client = httpx.AsyncClient(transport=transport, trust_env=False)
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kwargs: owned_client)
    instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL)
    await instance.verify(credential(key))
    await instance.close()
    assert owned_client.is_closed


async def test_close_during_lookup_does_not_release_a_principal(key: SigningKey):
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        await release.wait()
        return httpx.Response(200, json={"keys": [key.jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        running = asyncio.create_task(instance.verify(credential(key)))
        await asyncio.wait_for(started.wait(), timeout=1)
        await instance.close()
        release.set()
        with pytest.raises(AuthenticationUnavailable):
            await running


async def test_unknown_kid_flood_is_coalesced_and_rate_limited(
    key: SigningKey, monkeypatch: pytest.MonkeyPatch
):
    calls = 0
    current = [1000.0]
    monkeypatch.setattr(auth, "monotonic", lambda: current[0])

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.01)
        assert str(request.url) == JWKS_URL
        return httpx.Response(200, json={"keys": [key.jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        outcomes = await asyncio.gather(
            *(
                instance.verify(credential(key, headers={"kid": f"unknown-{number}"}))
                for number in range(20)
            ),
            return_exceptions=True,
        )
        assert all(isinstance(outcome, AuthenticationError) for outcome in outcomes)
        assert calls == 1
        assert (await instance.verify(credential(key))).subject == "synthetic-subject"
        current[0] += 5.1
        with pytest.raises(AuthenticationError):
            await instance.verify(credential(key, headers={"kid": "still-unknown"}))
        assert calls == 2


async def test_rotation_refreshes_new_key_after_global_backoff(
    key: SigningKey, other_key: SigningKey, monkeypatch: pytest.MonkeyPatch
):
    current = [1000.0]
    monkeypatch.setattr(auth, "monotonic", lambda: current[0])
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200, json={"keys": [key.jwk, other_key.jwk] if calls > 1 else [key.jwk]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        await instance.verify(credential(key))
        with pytest.raises(AuthenticationError):
            await instance.verify(credential(other_key))
        current[0] += 5.1
        assert (await instance.verify(credential(other_key))).issuer == ISSUER
    assert calls == 2


async def test_expired_cache_fails_closed_and_provider_failure_is_throttled(
    key: SigningKey, monkeypatch: pytest.MonkeyPatch
):
    current = [1000.0]
    monkeypatch.setattr(auth, "monotonic", lambda: current[0])
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise httpx.ConnectError("not logged: provider transport details")
        return httpx.Response(200, json={"keys": [key.jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        await instance.verify(credential(key))
        current[0] += 301
        for _ in range(3):
            with pytest.raises(
                AuthenticationUnavailable, match="^Authentication provider unavailable$"
            ):
                await instance.verify(credential(key))
    assert calls == 2


@pytest.mark.parametrize(
    "response_kind", ["redirect", "failure", "length", "body", "compression", "json"]
)
async def test_bad_or_oversized_jwks_is_unavailable_without_redirect(
    key: SigningKey, response_kind: str
):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if response_kind == "redirect":
            return httpx.Response(302, headers={"Location": "http://169.254.169.254/"})
        if response_kind == "failure":
            return httpx.Response(503)
        if response_kind == "length":
            return httpx.Response(200, content=b"{}", headers={"content-length": "131073"})
        if response_kind == "body":
            return httpx.Response(200, content=b" " * 131073, headers={"content-length": "0"})
        if response_kind == "compression":
            return httpx.Response(200, headers={"content-encoding": "gzip"}, content=b"")
        return httpx.Response(200, content=b'{"keys":[],"keys":[]}')

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), trust_env=False, follow_redirects=True
    ) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        with pytest.raises(AuthenticationUnavailable):
            await instance.verify(credential(key))
    assert calls == [JWKS_URL]


async def test_total_jwks_deadline_is_bounded(key: SigningKey, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(auth, "JWKS_TIMEOUT_SECONDS", 0.03)

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1)
        return httpx.Response(200, json={"keys": [key.jwk]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
        instance = OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)
        with pytest.raises(AuthenticationUnavailable):
            await instance.verify(credential(key))


@pytest.mark.parametrize(
    "document_kind", ["empty", "many", "duplicate", "private", "invalid", "weak"]
)
def test_unsafe_static_key_sets_fail_closed(key: SigningKey, document_kind: str):
    if document_kind == "empty":
        document = {"keys": []}
    elif document_kind == "many":
        document = {"keys": [{**key.jwk, "kid": str(number)} for number in range(21)]}
    elif document_kind == "duplicate":
        document = {"keys": [key.jwk, key.jwk]}
    elif document_kind == "private":
        document = {"keys": [{**key.jwk, "d": "private-material-is-rejected"}]}
    elif document_kind == "weak":
        document = {"keys": [make_key("weak", 1024).jwk]}
    else:
        document = {"keys": [{**key.jwk, "n": "!"}]}
    with pytest.raises(AuthenticationUnavailable):
        OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, jwks=document)


@pytest.mark.parametrize(
    "configuration",
    [
        ("", "", ""),
        (ISSUER, "", JWKS_URL),
        ("http://issuer.example.test", AUDIENCE, JWKS_URL),
        (ISSUER, AUDIENCE, "http://keys.example.test/jwks"),
        (ISSUER, AUDIENCE, "https://user:password@keys.example.test/jwks"),
        (ISSUER + "?issuer=attacker", AUDIENCE, JWKS_URL),
    ],
)
async def test_unconfigured_or_insecure_provider_is_unavailable(
    key: SigningKey, configuration: tuple[str, str, str]
):
    instance = OIDCVerifier(*configuration, jwks={"keys": [key.jwk]})
    with pytest.raises(AuthenticationUnavailable):
        await instance.verify(credential(key))


async def test_injected_client_cannot_trust_environment_proxy():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="disable environment trust"):
            OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, client=client)


@pytest.mark.parametrize("skew", [-1, 61, True])
def test_excessive_clock_skew_is_not_allowed(skew: int):
    with pytest.raises(ValueError):
        OIDCVerifier(ISSUER, AUDIENCE, JWKS_URL, clock_skew_seconds=skew)
