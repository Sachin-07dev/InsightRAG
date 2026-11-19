"""Fixed-provider OAuth access-token verification; JWT claims never grant tenant access."""

from __future__ import annotations

import asyncio
import base64
import json
import re
from dataclasses import dataclass
from time import monotonic, time
from typing import Any, TypeGuard
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

MAX_TOKEN_BYTES = 8192
MAX_KID_CHARACTERS = 128
MAX_JWKS_BYTES = 128 * 1024
MAX_JWKS_KEYS = 20
JWKS_TTL_SECONDS = 300
JWKS_REFRESH_INTERVAL_SECONDS = 5
JWKS_TIMEOUT_SECONDS = 2.0
MAX_TOKEN_LIFETIME_SECONDS = 3600
MAX_MFA_AGE_SECONDS = 300


class AuthenticationError(Exception):
    """The supplied credential does not establish an authenticated principal (HTTP 401)."""


class AuthenticationUnavailable(Exception):
    """The configured provider cannot currently establish identity (HTTP 503)."""


@dataclass(frozen=True, slots=True)
class Principal:
    issuer: str
    subject: str
    authenticated_at: int
    mfa: bool


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON member")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _json_object(value: bytes) -> dict[str, Any]:
    parsed: Any = json.loads(
        value.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_reject_constant
    )
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object")
    return parsed


def _valid_kid(value: Any) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_KID_CHARACTERS
        and value.isascii()
        and all(33 <= ord(character) <= 126 for character in value)
    )


def _registered_https_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return bool(
            value
            and len(value) <= 2048
            and all(ord(character) > 32 for character in value)
            and parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            and not parsed.fragment
            and not parsed.query
            and parsed.port != 0
        )
    except ValueError:
        return False


def _header(token: str) -> dict[str, Any]:
    if not isinstance(token, str) or not token.isascii() or len(token) > MAX_TOKEN_BYTES:
        raise AuthenticationError("Invalid access token")
    segments = token.split(".")
    if len(segments) != 3 or any(not re.fullmatch(r"[A-Za-z0-9_-]+", part) for part in segments):
        raise AuthenticationError("Invalid access token")
    try:
        # Inspect only bounded syntax before verification; no unverified claim is authority.
        objects = [
            _json_object(
                base64.b64decode(part + "=" * (-len(part) % 4), altchars=b"-_", validate=True)
            )
            for part in segments[:2]
        ]
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise AuthenticationError("Invalid access token") from exc
    header = objects[0]
    if (
        header.get("alg") != "RS256"
        or header.get("typ") != "at+jwt"
        or not _valid_kid(header.get("kid"))
        or any(name in header for name in ("jku", "x5u", "jwk", "x5c", "crit", "b64"))
    ):
        raise AuthenticationError("Invalid access token")
    return header


def _public_keys(document: dict[str, Any]) -> dict[str, RSAPublicKey]:
    entries = document.get("keys")
    if not isinstance(entries, list) or not 0 < len(entries) <= MAX_JWKS_KEYS:
        raise AuthenticationUnavailable("Authentication provider unavailable")
    keys: dict[str, RSAPublicKey] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise AuthenticationUnavailable("Authentication provider unavailable")
        if any(name in entry for name in ("d", "p", "q", "dp", "dq", "qi", "oth")):
            raise AuthenticationUnavailable("Authentication provider unavailable")
        if entry.get("kty") != "RSA" or entry.get("alg", "RS256") != "RS256":
            continue
        if entry.get("use", "sig") != "sig":
            continue
        operations = entry.get("key_ops", ["verify"])
        if operations != ["verify"]:
            continue
        kid = entry.get("kid")
        if not _valid_kid(kid) or kid in keys:
            raise AuthenticationUnavailable("Authentication provider unavailable")
        if "x5u" in entry:
            raise AuthenticationUnavailable("Authentication provider unavailable")
        if (
            not isinstance(entry.get("n"), str)
            or len(entry["n"]) > 1368
            or not isinstance(entry.get("e"), str)
            or len(entry["e"]) > 8
        ):
            raise AuthenticationUnavailable("Authentication provider unavailable")
        try:
            key = jwt.PyJWK.from_dict(entry, algorithm="RS256").key
        except (jwt.PyJWTError, ValueError, TypeError) as exc:
            raise AuthenticationUnavailable("Authentication provider unavailable") from exc
        if not isinstance(key, RSAPublicKey) or not 2048 <= key.key_size <= 4096:
            raise AuthenticationUnavailable("Authentication provider unavailable")
        keys[kid] = key
    if not keys:
        raise AuthenticationUnavailable("Authentication provider unavailable")
    return keys


class OIDCVerifier:
    """Async resource-server verifier for one operator-registered HTTPS issuer/audience.

    Inline JWKS is a pinned offline/test source. An injected client remains caller-owned and
    must disable environment trust. Application use should let this class own its HTTP client.
    """

    def __init__(
        self,
        issuer: str,
        audience: str,
        jwks_url: str,
        *,
        jwks: dict[str, Any] | None = None,
        client: httpx.AsyncClient | None = None,
        clock_skew_seconds: int = 30,
    ) -> None:
        if type(clock_skew_seconds) is not int or not 0 <= clock_skew_seconds <= 60:
            raise ValueError("OIDC clock skew must be between zero and sixty seconds")
        if client is not None and client.trust_env:
            raise ValueError("Injected OIDC client must disable environment trust")
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self.clock_skew_seconds = clock_skew_seconds
        self._configured = (
            _registered_https_url(issuer)
            and _registered_https_url(jwks_url)
            and isinstance(audience, str)
            and bool(audience)
            and len(audience) <= 2048
            and all(ord(character) > 32 for character in audience)
        )
        self._static = jwks is not None
        self._keys = _public_keys(jwks) if jwks is not None else {}
        self._loaded_at = monotonic() if jwks is not None else float("-inf")
        self._last_attempt = float("-inf")
        self._refresh_failed = False
        self._lock = asyncio.Lock()
        self._client = client
        self._owns_client = client is None
        self._closed = False

    async def close(self) -> None:
        self._closed = True
        self._keys.clear()
        if self._owns_client and self._client is not None:
            await self._client.aclose()

    async def _fetch(self) -> dict[str, RSAPublicKey]:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=JWKS_TIMEOUT_SECONDS,
                follow_redirects=False,
                trust_env=False,
                limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            )
        try:
            # HTTPX timeouts are per operation; this additionally bounds total wall time.
            async with asyncio.timeout(JWKS_TIMEOUT_SECONDS):
                async with self._client.stream(
                    "GET",
                    self.jwks_url,
                    headers={"Accept": "application/json", "Accept-Encoding": "identity"},
                    timeout=JWKS_TIMEOUT_SECONDS,
                    follow_redirects=False,
                ) as response:
                    if response.status_code != 200:
                        raise AuthenticationUnavailable("Authentication provider unavailable")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise AuthenticationUnavailable("Authentication provider unavailable")
                    length = response.headers.get("content-length")
                    if length is not None and not 0 <= int(length) <= MAX_JWKS_BYTES:
                        raise AuthenticationUnavailable("Authentication provider unavailable")
                    content = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16_384):
                        content.extend(chunk)
                        if len(content) > MAX_JWKS_BYTES:
                            raise AuthenticationUnavailable("Authentication provider unavailable")
                    return _public_keys(_json_object(bytes(content)))
        except AuthenticationUnavailable:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, UnicodeError, RecursionError) as exc:
            raise AuthenticationUnavailable("Authentication provider unavailable") from exc

    async def _key(self, kid: str) -> RSAPublicKey:
        if self._static:
            if kid not in self._keys:
                raise AuthenticationError("Invalid access token")
            return self._keys[kid]
        now = monotonic()
        if now - self._loaded_at < JWKS_TTL_SECONDS and kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            now = monotonic()
            if now - self._loaded_at < JWKS_TTL_SECONDS and kid in self._keys:
                return self._keys[kid]
            if now - self._last_attempt < JWKS_REFRESH_INTERVAL_SECONDS:
                if self._refresh_failed or now - self._loaded_at >= JWKS_TTL_SECONDS:
                    raise AuthenticationUnavailable("Authentication provider unavailable")
                raise AuthenticationError("Invalid access token")
            # Reserve the attempt before I/O; distinct unknown kids share this same throttle.
            self._last_attempt = now
            try:
                keys = await self._fetch()
            except AuthenticationUnavailable:
                self._refresh_failed = True
                raise
            self._keys = keys
            self._loaded_at = monotonic()
            self._refresh_failed = False
            if kid not in self._keys:
                raise AuthenticationError("Invalid access token")
            return self._keys[kid]

    async def verify(self, token: str) -> Principal:
        if not self._configured or self._closed:
            raise AuthenticationUnavailable("Authentication provider unavailable")
        header = _header(token)
        try:
            # Bound lock contention as well as the provider request. Do not serve expired keys.
            async with asyncio.timeout(JWKS_TIMEOUT_SECONDS):
                key = await self._key(header["kid"])
        except TimeoutError as exc:
            raise AuthenticationUnavailable("Authentication provider unavailable") from exc
        if self._closed:
            raise AuthenticationUnavailable("Authentication provider unavailable")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.audience,
                leeway=self.clock_skew_seconds,
                options={"require": ["iss", "sub", "aud", "exp", "iat", "nbf"]},
            )
            return self._principal(claims)
        except (jwt.PyJWTError, ValueError, TypeError, OverflowError) as exc:
            raise AuthenticationError("Invalid access token") from exc

    def _principal(self, claims: dict[str, Any]) -> Principal:
        now = int(time())
        subject = claims.get("sub")
        if (
            claims.get("iss") != self.issuer
            or not isinstance(subject, str)
            or not 0 < len(subject) <= 255
            or any(
                ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF for character in subject
            )
        ):
            raise AuthenticationError("Invalid access token")
        audience = claims.get("aud")
        audiences = [audience] if isinstance(audience, str) else audience
        if (
            not isinstance(audiences, list)
            or not 1 <= len(audiences) <= 10
            or any(not isinstance(value, str) or not 0 < len(value) <= 2048 for value in audiences)
            or self.audience not in audiences
        ):
            raise AuthenticationError("Invalid access token")
        if any(
            type(claims.get(name)) is not int or claims[name] < 0 for name in ("exp", "iat", "nbf")
        ):
            raise AuthenticationError("Invalid access token")
        issued_at, expires_at, not_before = claims["iat"], claims["exp"], claims["nbf"]
        if (
            not 0 < expires_at - issued_at <= MAX_TOKEN_LIFETIME_SECONDS
            or not_before > expires_at
            or issued_at > now + self.clock_skew_seconds
            or not_before > now + self.clock_skew_seconds
        ):
            raise AuthenticationError("Invalid access token")
        methods = claims.get("amr", [])
        if (
            not isinstance(methods, list)
            or len(methods) > 20
            or any(not isinstance(method, str) or not 0 < len(method) <= 64 for method in methods)
        ):
            raise AuthenticationError("Invalid access token")
        authentication_time = claims.get("auth_time")
        if "auth_time" in claims and (
            type(authentication_time) is not int
            or authentication_time < 0
            or authentication_time > issued_at + self.clock_skew_seconds
            or authentication_time > now + self.clock_skew_seconds
        ):
            raise AuthenticationError("Invalid access token")
        fresh_mfa = (
            "mfa" in methods
            and authentication_time is not None
            and max(0, now - authentication_time) <= MAX_MFA_AGE_SECONDS
        )
        return Principal(
            issuer=self.issuer,
            subject=subject,
            authenticated_at=authentication_time if authentication_time is not None else issued_at,
            mfa=fresh_mfa,
        )
